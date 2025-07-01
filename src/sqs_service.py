"""
SQS service management for Perplexity Validator.

This module provides functions for creating SQS queues, sending messages with priorities,
and handling the message processing workflow.
"""

import boto3
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Initialize SQS client - avoid resource client which can have issues in Lambda
try:
    sqs = boto3.client('sqs', region_name='us-east-1')
except Exception as e:
    logger.error(f"Failed to initialize SQS client: {e}")
    # Create a dummy client that will fail gracefully
    sqs = None

class SQSConfig:
    """Configuration for SQS queues."""
    
    # Queue names
    PREVIEW_QUEUE_NAME = "perplexity-validator-preview-queue.fifo"
    STANDARD_QUEUE_NAME = "perplexity-validator-standard-queue"
    DLQ_PREVIEW_NAME = "perplexity-validator-preview-dlq.fifo"
    DLQ_STANDARD_NAME = "perplexity-validator-standard-dlq"
    
    # Message group IDs for FIFO queues
    PREVIEW_MESSAGE_GROUP = "preview-group"
    
    @classmethod
    def get_preview_queue_attributes(cls) -> Dict[str, str]:
        """Get attributes for the preview FIFO queue."""
        return {
            'FifoQueue': 'true',
            'ContentBasedDeduplication': 'true',
            'VisibilityTimeoutSeconds': '300',  # 5 minutes
            'MessageRetentionPeriod': '1209600',  # 14 days
            'RedrivePolicy': json.dumps({
                'deadLetterTargetArn': f'arn:aws:sqs:us-east-1:400232868802:queue/{cls.DLQ_PREVIEW_NAME}',
                'maxReceiveCount': 3
            })
        }
    
    @classmethod
    def get_standard_queue_attributes(cls) -> Dict[str, str]:
        """Get attributes for the standard queue."""
        return {
            'VisibilityTimeoutSeconds': '600',  # 10 minutes for longer processing
            'MessageRetentionPeriod': '1209600',  # 14 days
            'RedrivePolicy': json.dumps({
                'deadLetterTargetArn': f'arn:aws:sqs:us-east-1:400232868802:queue/{cls.DLQ_STANDARD_NAME}',
                'maxReceiveCount': 3
            })
        }
    
    @classmethod
    def get_dlq_attributes(cls, is_fifo: bool = False) -> Dict[str, str]:
        """Get attributes for dead letter queues."""
        attributes = {
            'MessageRetentionPeriod': '1209600',  # 14 days
        }
        
        if is_fifo:
            attributes['FifoQueue'] = 'true'
            attributes['ContentBasedDeduplication'] = 'true'
        
        return attributes

class ValidationMessage:
    """Helper class for creating validation messages."""
    
    def __init__(self, session_id: str, request_type: str, excel_s3_key: str, 
                 config_s3_key: str, email: str, reference_pin: str):
        self.session_id = session_id
        self.request_type = request_type  # 'preview' or 'full'
        self.excel_s3_key = excel_s3_key
        self.config_s3_key = config_s3_key
        self.email = email
        self.reference_pin = reference_pin
        self.created_at = datetime.now(timezone.utc).isoformat()
        
    def to_sqs_message(self, **kwargs) -> Dict[str, Any]:
        """Convert to SQS message format."""
        message_body = {
            'session_id': self.session_id,
            'request_type': self.request_type,
            'excel_s3_key': self.excel_s3_key,
            'config_s3_key': self.config_s3_key,
            'email': self.email,
            'reference_pin': self.reference_pin,
            'created_at': self.created_at,
            'max_rows': kwargs.get('max_rows', 1000),
            'batch_size': kwargs.get('batch_size', 10),
            'preview_max_rows': kwargs.get('preview_max_rows', 5),
            'sequential_call': kwargs.get('sequential_call'),
            'email_folder': kwargs.get('email_folder', ''),
            'results_key': kwargs.get('results_key', ''),
            'async_mode': kwargs.get('async_mode', False)
        }
        
        return {
            'message_body': json.dumps(message_body),
            'deduplication_id': f"{self.session_id}_{self.created_at}",
            'message_group_id': SQSConfig.PREVIEW_MESSAGE_GROUP if self.request_type == 'preview' else None
        }

class SQSManager:
    """Manager class for SQS operations."""
    
    def __init__(self):
        # Initialize SQS client in the constructor to avoid global state issues
        self.sqs = boto3.client('sqs', region_name='us-east-1')
        self.config = SQSConfig()
        
        # Cache queue URLs
        self._preview_queue_url = None
        self._standard_queue_url = None
    
    def create_queues(self) -> bool:
        """Create all required SQS queues."""
        try:
            # Create dead letter queues first
            self._create_dlq(self.config.DLQ_PREVIEW_NAME, is_fifo=True)
            self._create_dlq(self.config.DLQ_STANDARD_NAME, is_fifo=False)
            
            # Create main queues
            self._create_preview_queue()
            self._create_standard_queue()
            
            logger.info("All SQS queues created successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Error creating SQS queues: {e}")
            return False
    
    def _create_dlq(self, queue_name: str, is_fifo: bool) -> str:
        """Create a dead letter queue."""
        try:
            response = self.sqs.create_queue(
                QueueName=queue_name,
                Attributes=self.config.get_dlq_attributes(is_fifo)
            )
            logger.info(f"Created DLQ: {queue_name}")
            return response['QueueUrl']
        except ClientError as e:
            if e.response['Error']['Code'] == 'QueueAlreadyExists':
                logger.info(f"DLQ already exists: {queue_name}")
                return self.sqs.get_queue_url(QueueName=queue_name)['QueueUrl']
            else:
                raise
    
    def _create_preview_queue(self) -> str:
        """Create the high-priority preview queue (FIFO)."""
        try:
            response = self.sqs.create_queue(
                QueueName=self.config.PREVIEW_QUEUE_NAME,
                Attributes=self.config.get_preview_queue_attributes()
            )
            self._preview_queue_url = response['QueueUrl']
            logger.info(f"Created preview queue: {self.config.PREVIEW_QUEUE_NAME}")
            return self._preview_queue_url
        except ClientError as e:
            if e.response['Error']['Code'] == 'QueueAlreadyExists':
                logger.info(f"Preview queue already exists: {self.config.PREVIEW_QUEUE_NAME}")
                self._preview_queue_url = self.sqs.get_queue_url(QueueName=self.config.PREVIEW_QUEUE_NAME)['QueueUrl']
                return self._preview_queue_url
            else:
                raise
    
    def _create_standard_queue(self) -> str:
        """Create the standard priority queue."""
        try:
            response = self.sqs.create_queue(
                QueueName=self.config.STANDARD_QUEUE_NAME,
                Attributes=self.config.get_standard_queue_attributes()
            )
            self._standard_queue_url = response['QueueUrl']
            logger.info(f"Created standard queue: {self.config.STANDARD_QUEUE_NAME}")
            return self._standard_queue_url
        except ClientError as e:
            if e.response['Error']['Code'] == 'QueueAlreadyExists':
                logger.info(f"Standard queue already exists: {self.config.STANDARD_QUEUE_NAME}")
                self._standard_queue_url = self.sqs.get_queue_url(QueueName=self.config.STANDARD_QUEUE_NAME)['QueueUrl']
                return self._standard_queue_url
            else:
                raise
    
    def get_queue_url(self, request_type: str) -> str:
        """Get the appropriate queue URL based on request type."""
        if request_type == 'preview':
            if not self._preview_queue_url:
                self._preview_queue_url = self.sqs.get_queue_url(QueueName=self.config.PREVIEW_QUEUE_NAME)['QueueUrl']
            return self._preview_queue_url
        else:
            if not self._standard_queue_url:
                self._standard_queue_url = self.sqs.get_queue_url(QueueName=self.config.STANDARD_QUEUE_NAME)['QueueUrl']
            return self._standard_queue_url
    
    def send_validation_request(self, message: ValidationMessage, **kwargs) -> Optional[str]:
        """Send a validation request to the appropriate queue."""
        try:
            queue_url = self.get_queue_url(message.request_type)
            sqs_message = message.to_sqs_message(**kwargs)
            
            send_params = {
                'QueueUrl': queue_url,
                'MessageBody': sqs_message['message_body']
            }
            
            # Add FIFO-specific parameters for preview queue
            if message.request_type == 'preview':
                send_params['MessageDeduplicationId'] = sqs_message['deduplication_id']
                send_params['MessageGroupId'] = sqs_message['message_group_id']
            
            response = self.sqs.send_message(**send_params)
            
            logger.info(f"Sent {message.request_type} message to SQS. MessageId: {response['MessageId']}")
            return response['MessageId']
            
        except Exception as e:
            logger.error(f"Error sending message to SQS: {e}")
            return None
    
    def receive_messages(self, request_type: str, max_messages: int = 1) -> List[Dict[str, Any]]:
        """Receive messages from the specified queue."""
        try:
            queue_url = self.get_queue_url(request_type)
            
            response = self.sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=max_messages,
                WaitTimeSeconds=20,  # Long polling
                MessageAttributeNames=['All']
            )
            
            messages = response.get('Messages', [])
            
            # Parse message bodies
            parsed_messages = []
            for message in messages:
                try:
                    body = json.loads(message['Body'])
                    parsed_messages.append({
                        'message_data': body,
                        'receipt_handle': message['ReceiptHandle'],
                        'message_id': message['MessageId']
                    })
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing message body: {e}")
                    continue
            
            return parsed_messages
            
        except Exception as e:
            logger.error(f"Error receiving messages from SQS: {e}")
            return []
    
    def delete_message(self, request_type: str, receipt_handle: str) -> bool:
        """Delete a processed message from the queue."""
        try:
            queue_url = self.get_queue_url(request_type)
            
            self.sqs.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
            
            logger.info(f"Deleted message from {request_type} queue")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting message from SQS: {e}")
            return False
    
    def get_queue_attributes(self, request_type: str) -> Dict[str, Any]:
        """Get queue attributes including message counts."""
        try:
            queue_url = self.get_queue_url(request_type)
            
            response = self.sqs.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=[
                    'ApproximateNumberOfMessages',
                    'ApproximateNumberOfMessagesInFlight',
                    'ApproximateNumberOfMessagesDelayed'
                ]
            )
            
            return response['Attributes']
            
        except Exception as e:
            logger.error(f"Error getting queue attributes: {e}")
            return {}

# Convenience functions for easy integration
def create_all_queues() -> bool:
    """Create all SQS queues."""
    manager = SQSManager()
    return manager.create_queues()

def send_preview_request(session_id: str, excel_s3_key: str, config_s3_key: str,
                        email: str, reference_pin: str, **kwargs) -> Optional[str]:
    """Send a preview validation request."""
    manager = SQSManager()
    message = ValidationMessage(session_id, 'preview', excel_s3_key, config_s3_key, email, reference_pin)
    return manager.send_validation_request(message, **kwargs)

def send_full_request(session_id: str, excel_s3_key: str, config_s3_key: str,
                     email: str, reference_pin: str, **kwargs) -> Optional[str]:
    """Send a full validation request."""
    manager = SQSManager()
    message = ValidationMessage(session_id, 'full', excel_s3_key, config_s3_key, email, reference_pin)
    return manager.send_validation_request(message, **kwargs)

def get_queue_status() -> Dict[str, Dict[str, Any]]:
    """Get status of all queues."""
    manager = SQSManager()
    return {
        'preview': manager.get_queue_attributes('preview'),
        'standard': manager.get_queue_attributes('full')
    } 