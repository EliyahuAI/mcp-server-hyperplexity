"""
DynamoDB table schemas for Perplexity Validator SQS Architecture.

This module defines the table structures and provides helper functions for
creating and managing DynamoDB tables for the perplexity validator service.
"""

import boto3
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from botocore.exceptions import ClientError
from decimal import Decimal
import logging
import time

logger = logging.getLogger(__name__)

# Initialize DynamoDB client - avoid resource client which can have issues in Lambda
try:
    dynamodb_client = boto3.client('dynamodb', region_name='us-east-1')
    # Create resource client lazily when needed
    _dynamodb_resource = None
except Exception as e:
    logger.error(f"Failed to initialize DynamoDB client: {e}")
    dynamodb_client = None
    _dynamodb_resource = None

dynamodb = boto3.resource('dynamodb')

def convert_floats_to_decimal(obj):
    """Convert float values to Decimal for DynamoDB compatibility."""
    if isinstance(obj, dict):
        return {key: convert_floats_to_decimal(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    elif isinstance(obj, float):
        return Decimal(str(obj))
    else:
        return obj

class DynamoDBSchemas:
    """DynamoDB table schemas and operations for perplexity validator."""
    
    # Table names
    CALL_TRACKING_TABLE = "perplexity-validator-call-tracking"
    TOKEN_USAGE_TABLE = "perplexity-validator-token-usage"
    COST_TRACKING_TABLE = "perplexity-validator-cost-tracking"
    USER_VALIDATION_TABLE = "perplexity-validator-user-validation"
    USER_TRACKING_TABLE = "perplexity-validator-user-tracking"
    
    @classmethod
    def get_call_tracking_schema(cls) -> Dict[str, Any]:
        """Schema for the main call tracking table."""
        return {
            'TableName': cls.CALL_TRACKING_TABLE,
            'KeySchema': [
                {
                    'AttributeName': 'session_id',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            'AttributeDefinitions': [
                {
                    'AttributeName': 'session_id',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'created_at',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'email_domain',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'status',
                    'AttributeType': 'S'
                }
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'EmailDomainIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'email_domain',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'created_at',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                },
                {
                    'IndexName': 'StatusIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'status',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'created_at',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                }
            ],
            'BillingMode': 'PAY_PER_REQUEST'
        }
    
    @classmethod
    def get_token_usage_schema(cls) -> Dict[str, Any]:
        """Schema for detailed token usage tracking."""
        return {
            'TableName': cls.TOKEN_USAGE_TABLE,
            'KeySchema': [
                {
                    'AttributeName': 'session_id',
                    'KeyType': 'HASH'  # Partition key
                },
                {
                    'AttributeName': 'timestamp',
                    'KeyType': 'RANGE'  # Sort key
                }
            ],
            'AttributeDefinitions': [
                {
                    'AttributeName': 'session_id',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'timestamp',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'api_provider',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'model',
                    'AttributeType': 'S'
                }
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'ApiProviderIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'api_provider',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'timestamp',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                },
                {
                    'IndexName': 'ModelIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'model',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'timestamp',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                }
            ],
            'BillingMode': 'PAY_PER_REQUEST'
        }
    
    @classmethod
    def get_user_validation_schema(cls) -> Dict[str, Any]:
        """Schema for user email validation table."""
        return {
            'TableName': cls.USER_VALIDATION_TABLE,
            'KeySchema': [
                {
                    'AttributeName': 'email',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            'AttributeDefinitions': [
                {
                    'AttributeName': 'email',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'validation_code',
                    'AttributeType': 'S'
                }
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'ValidationCodeIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'validation_code',
                            'KeyType': 'HASH'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                }
            ],
            'BillingMode': 'PAY_PER_REQUEST'
        }
    
    @classmethod
    def get_user_tracking_schema(cls) -> Dict[str, Any]:
        """Schema for user usage tracking table."""
        return {
            'TableName': cls.USER_TRACKING_TABLE,
            'KeySchema': [
                {
                    'AttributeName': 'email',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            'AttributeDefinitions': [
                {
                    'AttributeName': 'email',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'email_domain',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'last_access',
                    'AttributeType': 'S'
                }
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'EmailDomainIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'email_domain',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'last_access',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                }
            ],
            'BillingMode': 'PAY_PER_REQUEST'
        }

class CallTrackingRecord:
    """Enhanced helper class for comprehensive call tracking records."""
    
    def __init__(self, session_id: str, email: str, reference_pin: str, request_type: str):
        self.session_id = session_id
        self.email = email.lower().strip()  # Normalize email to lowercase
        self.reference_pin = reference_pin
        self.request_type = request_type  # 'preview' or 'full'
        self.email_domain = self.email.split('@')[-1] if '@' in self.email else 'unknown'
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.status = 'queued'
        self._data = self.to_dynamodb_item()
    
    def update_status(self, status: str, **kwargs):
        """Update status and other fields."""
        self.status = status
        self._data['status'] = status
        self._data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        # Update any additional fields passed as kwargs
        for key, value in kwargs.items():
            if key in self._data:
                self._data[key] = value
    
    def set_processing_started(self, lambda_request_id: str = '', api_gateway_request_id: str = ''):
        """Mark processing as started."""
        timestamp = datetime.now(timezone.utc).isoformat()
        self.update_status('processing', 
                          started_processing_at=timestamp,
                          lambda_request_id=lambda_request_id,
                          api_gateway_request_id=api_gateway_request_id)
    
    def set_processing_completed(self, success: bool = True):
        """Mark processing as completed."""
        timestamp = datetime.now(timezone.utc).isoformat()
        status = 'completed' if success else 'failed'
        self.update_status(status, completed_processing_at=timestamp)
    
    def add_api_usage(self, provider: str, calls: int, tokens: int, cost: float, model: str = '', cached_calls: int = 0):
        """Add API usage data."""
        if provider.lower() == 'perplexity':
            self._data['perplexity_api_calls'] += calls
            self._data['perplexity_cached_calls'] += cached_calls
            self._data['perplexity_total_tokens'] += tokens
            self._data['perplexity_cost_usd'] += cost
            if model and model not in self._data['perplexity_models_used']:
                self._data['perplexity_models_used'].append(model)
        elif provider.lower() == 'anthropic':
            self._data['anthropic_api_calls'] += calls
            self._data['anthropic_cached_calls'] += cached_calls
            self._data['anthropic_total_tokens'] += tokens
            self._data['anthropic_cost_usd'] += cost
            if model and model not in self._data['anthropic_models_used']:
                self._data['anthropic_models_used'].append(model)
        
        # Update totals
        self._data['total_api_calls'] = self._data['perplexity_api_calls'] + self._data['anthropic_api_calls']
        self._data['total_cached_calls'] = self._data['perplexity_cached_calls'] + self._data['anthropic_cached_calls']
        self._data['total_tokens'] = self._data['perplexity_total_tokens'] + self._data['anthropic_total_tokens']
        self._data['total_cost_usd'] = self._data['perplexity_cost_usd'] + self._data['anthropic_cost_usd']
    
    def add_error(self, error_message: str):
        """Add an error message."""
        self._data['error_count'] += 1
        self._data['error_messages'].append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'message': error_message
        })
    
    def add_warning(self, warning_message: str):
        """Add a warning message."""
        self._data['warnings'].append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'message': warning_message
        })
    
    def set_preview_estimates(self, per_row_cost: float, per_row_tokens: int, per_row_time: float, 
                             per_row_time_without_cache: float, total_rows: int):
        """Set preview estimates with both cached and non-cached time estimates."""
        self._data['preview_per_row_cost_usd'] = per_row_cost
        self._data['preview_per_row_tokens'] = per_row_tokens
        self._data['preview_per_row_time_seconds'] = per_row_time
        self._data['preview_per_row_time_without_cache_seconds'] = per_row_time_without_cache
        self._data['preview_estimated_total_cost_usd'] = per_row_cost * total_rows
        self._data['preview_estimated_total_tokens'] = per_row_tokens * total_rows
        self._data['preview_estimated_total_time_hours'] = (per_row_time * total_rows) / 3600
        self._data['preview_estimated_total_time_without_cache_hours'] = (per_row_time_without_cache * total_rows) / 3600
    
    def set_batch_timing_estimates(self, time_per_batch: float, total_batches: int):
        """Set batch-level timing estimates (costs and tokens remain per-row)."""
        self._data['time_per_batch_seconds'] = time_per_batch
        self._data['estimated_total_batches'] = total_batches
        
        # Update preview time estimates using batch calculations
        if total_batches > 0:
            self._data['preview_estimated_total_time_hours'] = (time_per_batch * total_batches) / 3600
    
    def set_validation_metrics(self, validated_columns: int, search_groups: int, 
                              high_context_groups: int, claude_groups: int):
        """Set validation structure metrics."""
        self._data['validated_columns_count'] = validated_columns
        self._data['search_groups_count'] = search_groups
        self._data['high_context_search_groups_count'] = high_context_groups
        self._data['claude_search_groups_count'] = claude_groups
    
    def set_file_info(self, excel_s3_key: str = '', config_s3_key: str = '', results_s3_key: str = '', 
                     excel_size: int = 0, config_size: int = 0, results_size: int = 0, 
                     excel_filename: str = '', config_filename: str = '', results_filename: str = ''):
        """Set file information with separate filenames for each file type."""
        if excel_s3_key:
            self._data['excel_s3_key'] = excel_s3_key
        if config_s3_key:
            self._data['config_s3_key'] = config_s3_key
        if results_s3_key:
            self._data['results_s3_key'] = results_s3_key
        if excel_size:
            self._data['excel_file_size_bytes'] = excel_size
        if config_size:
            self._data['config_file_size_bytes'] = config_size
        if results_size:
            self._data['results_file_size_bytes'] = results_size
        if excel_filename:
            self._data['original_excel_filename'] = excel_filename
        if config_filename:
            self._data['original_config_filename'] = config_filename
        if results_filename:
            self._data['original_results_filename'] = results_filename
    
    def calculate_performance_metrics(self):
        """Calculate performance metrics based on current data."""
        if self._data['processed_rows'] > 0:
            self._data['avg_time_per_row_seconds'] = self._data['processing_time_seconds'] / self._data['processed_rows']
            self._data['avg_cost_per_row_usd'] = self._data['total_cost_usd'] / self._data['processed_rows']
            self._data['avg_tokens_per_row'] = self._data['total_tokens'] / self._data['processed_rows']
    
    def get_data(self) -> Dict[str, Any]:
        """Get the current data dictionary."""
        return self._data.copy()
        
    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to comprehensive DynamoDB item format."""
        if hasattr(self, '_data'):
            return self._data.copy()
        
        return {
            # Basic identification
            'session_id': self.session_id,
            'email': self.email,
            'email_domain': self.email_domain,
            'reference_pin': self.reference_pin,
            'request_type': self.request_type,
            'status': self.status,
            
            # Timestamps
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'started_processing_at': '',
            'completed_processing_at': '',
            'response_sent_at': '',
            
            # Trigger information
            'trigger_source': 'api_gateway',  # 'api_gateway', 'sqs', 'direct'
            'trigger_method': 'json_action',  # 'json_action', 'multipart', 'sqs_message'
            'client_ip': '',
            'user_agent': '',
            'api_gateway_request_id': '',
            'lambda_request_id': '',
            
            # File information
            'excel_s3_key': '',
            'config_s3_key': '',
            'results_s3_key': '',
            'excel_file_size_bytes': 0,
            'config_file_size_bytes': 0,
            'results_file_size_bytes': 0,
            'original_excel_filename': '',
            'original_config_filename': '',
            'original_results_filename': '',
            
            # Processing parameters
            'max_rows': 0,
            'batch_size': 0,
            'preview_max_rows': 0,
            'async_mode': False,
            'sequential_call': 0,
            
            # Row processing
            'total_rows': 0,
            'processed_rows': 0,
            'cached_rows': 0,
            'new_rows_processed': 0,
            'validation_targets_count': 0,
            
            # API usage - Perplexity
            'perplexity_api_calls': 0,
            'perplexity_cached_calls': 0,
            'perplexity_prompt_tokens': 0,
            'perplexity_completion_tokens': 0,
            'perplexity_total_tokens': 0,
            'perplexity_cost_usd': 0.0,
            'perplexity_models_used': [],
            
            # API usage - Anthropic
            'anthropic_api_calls': 0,
            'anthropic_cached_calls': 0,
            'anthropic_input_tokens': 0,
            'anthropic_output_tokens': 0,
            'anthropic_cache_tokens': 0,
            'anthropic_total_tokens': 0,
            'anthropic_cost_usd': 0.0,
            'anthropic_models_used': [],
            
            # Total costs and tokens
            'total_api_calls': 0,
            'total_cached_calls': 0,
            'total_tokens': 0,
            'total_cost_usd': 0.0,
            
            # Preview estimates (for preview mode)
            'preview_per_row_cost_usd': 0.0,
            'preview_per_row_tokens': 0,
            'preview_per_row_time_seconds': 0.0,
            'preview_per_row_time_without_cache_seconds': 0.0,
            'preview_estimated_total_cost_usd': 0.0,
            'preview_estimated_total_tokens': 0,
            'preview_estimated_total_time_hours': 0.0,
            'preview_estimated_total_time_without_cache_hours': 0.0,
            
            # Timing (all in seconds)
            'processing_time_seconds': 0.0,
            'queue_wait_time_seconds': 0.0,
            'validation_time_seconds': 0.0,
            'file_upload_time_seconds': 0.0,
            'result_creation_time_seconds': 0.0,
            'email_send_time_seconds': 0.0,
            
            # Performance metrics
            'avg_time_per_row_seconds': 0.0,
            'avg_cost_per_row_usd': 0.0,
            'avg_tokens_per_row': 0.0,
            
            # Batch timing metrics (timing only - costs/tokens are per-row)
            'estimated_total_batches': 0,
            'time_per_batch_seconds': 0.0,
            
            # Validation structure metrics
            'validated_columns_count': 0,
            'search_groups_count': 0,
            'high_context_search_groups_count': 0,
            'claude_search_groups_count': 0,
            
            # Quality metrics
            'high_confidence_count': 0,
            'medium_confidence_count': 0,
            'low_confidence_count': 0,
            'validation_accuracy_score': 0.0,
            
            # Infrastructure
            'sqs_message_id': '',
            'lambda_memory_used': 0,
            'lambda_duration': 0.0,
            'lambda_billed_duration': 0.0,
            
            # Error handling
            'error_count': 0,
            'error_messages': [],
            'warnings': [],
            'retry_count': 0,
            
            # Email delivery
            'email_sent': False,
            'email_delivery_status': '',
            'email_message_id': '',
            'email_bounce_reason': '',
            
            # Results metadata
            'result_format': '',  # 'excel', 'json', 'csv'
            'download_count': 0,
            'last_downloaded_at': '',
            'expires_at': '',
            
            # Search context usage
            'search_context_usage': {},  # {'low': 5, 'medium': 3, 'high': 2}
            'search_group_counts': {},   # Details about search groups
            
            # Custom fields
            'notes': '',
            'tags': [],
            'priority': 'normal',
            'version': '1.0'
        }

def create_call_tracking_table():
    """Create the call tracking table."""
    schemas = DynamoDBSchemas()
    try:
        dynamodb_client.create_table(**schemas.get_call_tracking_schema())
        logger.info(f"Created {schemas.CALL_TRACKING_TABLE} table")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            logger.info(f"Table {schemas.CALL_TRACKING_TABLE} already exists")
            return True
        else:
            logger.error(f"Error creating call tracking table: {e}")
            return False

def create_token_usage_table():
    """Create the token usage table."""
    schemas = DynamoDBSchemas()
    try:
        dynamodb_client.create_table(**schemas.get_token_usage_schema())
        logger.info(f"Created {schemas.TOKEN_USAGE_TABLE} table")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            logger.info(f"Table {schemas.TOKEN_USAGE_TABLE} already exists")
            return True
        else:
            logger.error(f"Error creating token usage table: {e}")
            return False

def track_validation_call(session_id: str, email: str, reference_pin: str, 
                         request_type: str, **kwargs) -> bool:
    """Track a validation call in DynamoDB."""
    try:
        schemas = DynamoDBSchemas()
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table(schemas.CALL_TRACKING_TABLE)
        
        # Email normalization is handled in CallTrackingRecord.__init__
        record = CallTrackingRecord(session_id, email, reference_pin, request_type)
        item = record.to_dynamodb_item()
        
        # Update any additional fields
        for key, value in kwargs.items():
            item[key] = value
        
        # Convert floats to Decimal for DynamoDB
        item = convert_floats_to_decimal(item)
        
        table.put_item(Item=item)
        return True
    except Exception as e:
        logger.error(f"Error tracking validation call: {e}")
        return False

def update_call_status(session_id: str, status: str, **kwargs) -> bool:
    """Update call status in DynamoDB."""
    try:
        schemas = DynamoDBSchemas()
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table(schemas.CALL_TRACKING_TABLE)
        
        updates = {
            'status': status,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        updates.update(kwargs)
        
        # Build update expression with attribute names for reserved keywords
        update_expression = "SET "
        expression_attribute_values = {}
        expression_attribute_names = {}
        
        for key, value in updates.items():
            if key == 'status':
                # Handle reserved keyword
                update_expression += f"#status = :status, "
                expression_attribute_names['#status'] = 'status'
                expression_attribute_values[':status'] = value
            else:
                update_expression += f"{key} = :{key}, "
                expression_attribute_values[f":{key}"] = value
        
        # Remove trailing comma and space
        update_expression = update_expression.rstrip(", ")
        
        # Convert floats to Decimal for DynamoDB
        expression_attribute_values = convert_floats_to_decimal(expression_attribute_values)
        
        update_kwargs = {
            'Key': {'session_id': session_id},
            'UpdateExpression': update_expression,
            'ExpressionAttributeValues': expression_attribute_values
        }
        
        if expression_attribute_names:
            update_kwargs['ExpressionAttributeNames'] = expression_attribute_names
        
        table.update_item(**update_kwargs)
        return True
    except Exception as e:
        logger.error(f"Error updating call status: {e}")
        return False

def get_call_record(session_id: str) -> Optional[Dict[str, Any]]:
    """Get call tracking record by session ID."""
    try:
        schemas = DynamoDBSchemas()
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table(schemas.CALL_TRACKING_TABLE)
        response = table.get_item(Key={'session_id': session_id})
        return response.get('Item')
    except Exception as e:
        logger.error(f"Error getting call record: {e}")
        return None

def track_token_usage(session_id: str, api_provider: str, model: str,
                     input_tokens: int, output_tokens: int, total_cost: float,
                     search_context_size: str = None) -> bool:
    """Track token usage in DynamoDB."""
    try:
        schemas = DynamoDBSchemas()
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table(schemas.TOKEN_USAGE_TABLE)
        
        item = {
            'session_id': session_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'api_provider': api_provider,
            'model': model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
            'total_cost': total_cost,
            'search_context_size': search_context_size or 'unknown'
        }
        
        # Convert floats to Decimal for DynamoDB
        item = convert_floats_to_decimal(item)
        
        table.put_item(Item=item)
        return True
    except Exception as e:
        logger.error(f"Error tracking token usage: {e}")
        return False


def update_processing_metrics(session_id: str, metrics: Dict[str, Any]) -> bool:
    """Update processing metrics for a call."""
    try:
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.CALL_TRACKING_TABLE)
        
        # Build update expression dynamically
        update_parts = []
        expression_values = {}
        expression_names = {}
        
        for key, value in metrics.items():
            if key not in ['session_id']:
                placeholder = f':val_{len(expression_values)}'
                if key in ['status', 'search_context_usage', 'search_group_counts']:
                    # These might be reserved words or complex structures
                    name_placeholder = f'#attr_{len(expression_names)}'
                    expression_names[name_placeholder] = key
                    update_parts.append(f"{name_placeholder} = {placeholder}")
                else:
                    update_parts.append(f"{key} = {placeholder}")
                expression_values[placeholder] = value
        
        # Always update timestamp
        update_parts.append("updated_at = :updated_at")
        expression_values[':updated_at'] = datetime.now(timezone.utc).isoformat()
        
        update_expression = "SET " + ", ".join(update_parts)
        
        # Convert floats to Decimal for DynamoDB
        expression_values = convert_floats_to_decimal(expression_values)
        
        kwargs = {
            'Key': {'session_id': session_id},
            'UpdateExpression': update_expression,
            'ExpressionAttributeValues': expression_values
        }
        
        if expression_names:
            kwargs['ExpressionAttributeNames'] = expression_names
        
        table.update_item(**kwargs)
        return True
    except Exception as e:
        logger.error(f"Error updating processing metrics: {e}")
        return False


def track_api_usage_detailed(session_id: str, provider: str, usage_data: Dict[str, Any]) -> bool:
    """Track detailed API usage for a specific provider."""
    try:
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.CALL_TRACKING_TABLE)
        
        # Get current record to calculate new totals
        response = table.get_item(Key={'session_id': session_id})
        if 'Item' not in response:
            logger.error(f"Session {session_id} not found for API usage tracking")
            return False
        
        current_data = response['Item']
        
        # Helper function to convert to number for arithmetic
        def to_num(val):
            if isinstance(val, Decimal):
                return float(val)
            return val
        
        # Calculate updates based on provider
        updates = {}
        if provider.lower() == 'perplexity':
            updates['perplexity_api_calls'] = to_num(current_data.get('perplexity_api_calls', 0)) + usage_data.get('api_calls', 0)
            updates['perplexity_cached_calls'] = to_num(current_data.get('perplexity_cached_calls', 0)) + usage_data.get('cached_calls', 0)
            updates['perplexity_prompt_tokens'] = to_num(current_data.get('perplexity_prompt_tokens', 0)) + usage_data.get('prompt_tokens', 0)
            updates['perplexity_completion_tokens'] = to_num(current_data.get('perplexity_completion_tokens', 0)) + usage_data.get('completion_tokens', 0)
            updates['perplexity_total_tokens'] = to_num(current_data.get('perplexity_total_tokens', 0)) + usage_data.get('total_tokens', 0)
            updates['perplexity_cost_usd'] = to_num(current_data.get('perplexity_cost_usd', 0)) + usage_data.get('cost', 0)
            
            # Handle models list
            current_models = current_data.get('perplexity_models_used', [])
            new_model = usage_data.get('model', '')
            if new_model and new_model not in current_models:
                current_models.append(new_model)
            updates['perplexity_models_used'] = current_models
            
        elif provider.lower() == 'anthropic':
            updates['anthropic_api_calls'] = to_num(current_data.get('anthropic_api_calls', 0)) + usage_data.get('api_calls', 0)
            updates['anthropic_cached_calls'] = to_num(current_data.get('anthropic_cached_calls', 0)) + usage_data.get('cached_calls', 0)
            updates['anthropic_input_tokens'] = to_num(current_data.get('anthropic_input_tokens', 0)) + usage_data.get('input_tokens', 0)
            updates['anthropic_output_tokens'] = to_num(current_data.get('anthropic_output_tokens', 0)) + usage_data.get('output_tokens', 0)
            updates['anthropic_cache_tokens'] = to_num(current_data.get('anthropic_cache_tokens', 0)) + usage_data.get('cache_tokens', 0)
            updates['anthropic_total_tokens'] = to_num(current_data.get('anthropic_total_tokens', 0)) + usage_data.get('total_tokens', 0)
            updates['anthropic_cost_usd'] = to_num(current_data.get('anthropic_cost_usd', 0)) + usage_data.get('cost', 0)
            
            # Handle models list
            current_models = current_data.get('anthropic_models_used', [])
            new_model = usage_data.get('model', '')
            if new_model and new_model not in current_models:
                current_models.append(new_model)
            updates['anthropic_models_used'] = current_models
        
        # Calculate new totals
        updates['total_api_calls'] = updates.get('perplexity_api_calls', to_num(current_data.get('perplexity_api_calls', 0))) + updates.get('anthropic_api_calls', to_num(current_data.get('anthropic_api_calls', 0)))
        updates['total_cached_calls'] = updates.get('perplexity_cached_calls', to_num(current_data.get('perplexity_cached_calls', 0))) + updates.get('anthropic_cached_calls', to_num(current_data.get('anthropic_cached_calls', 0)))
        updates['total_tokens'] = updates.get('perplexity_total_tokens', to_num(current_data.get('perplexity_total_tokens', 0))) + updates.get('anthropic_total_tokens', to_num(current_data.get('anthropic_total_tokens', 0)))
        updates['total_cost_usd'] = updates.get('perplexity_cost_usd', to_num(current_data.get('perplexity_cost_usd', 0))) + updates.get('anthropic_cost_usd', to_num(current_data.get('anthropic_cost_usd', 0)))
        
        # Calculate performance metrics if we have processed rows
        processed_rows = to_num(current_data.get('processed_rows', 0))
        if processed_rows > 0:
            updates['avg_cost_per_row_usd'] = updates['total_cost_usd'] / processed_rows
            updates['avg_tokens_per_row'] = updates['total_tokens'] / processed_rows
        
        return update_processing_metrics(session_id, updates)
        
    except Exception as e:
        logger.error(f"Error tracking detailed API usage: {e}")
        return False


def track_email_delivery(session_id: str, email_sent: bool, delivery_status: str = '', 
                        message_id: str = '', bounce_reason: str = '') -> bool:
    """Track email delivery status."""
    try:
        updates = {
            'email_sent': email_sent,
            'email_delivery_status': delivery_status,
            'email_message_id': message_id,
            'email_bounce_reason': bounce_reason,
            'response_sent_at': datetime.now(timezone.utc).isoformat()
        }
        return update_processing_metrics(session_id, updates)
    except Exception as e:
        logger.error(f"Error tracking email delivery: {e}")
        return False


def track_lambda_performance(session_id: str, memory_used: int, duration: float, 
                           billed_duration: float) -> bool:
    """Track Lambda performance metrics."""
    try:
        updates = {
            'lambda_memory_used': memory_used,
            'lambda_duration': duration,
            'lambda_billed_duration': billed_duration
        }
        return update_processing_metrics(session_id, updates)
    except Exception as e:
        logger.error(f"Error tracking Lambda performance: {e}")
        return False


def get_call_analytics(session_id: str = None, email: str = None, date_range: tuple = None) -> Dict[str, Any]:
    """Get comprehensive analytics for calls."""
    try:
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.CALL_TRACKING_TABLE)
        
        if session_id:
            # Get specific session
            response = table.get_item(Key={'session_id': session_id})
            if 'Item' in response:
                return {'sessions': [response['Item']], 'count': 1}
        
        # Scan for multiple records
        scan_kwargs = {}
        
        if email:
            scan_kwargs['FilterExpression'] = 'email = :email'
            scan_kwargs['ExpressionAttributeValues'] = {':email': email}
        
        response = table.scan(**scan_kwargs)
        items = response.get('Items', [])
        
        # Filter by date range if provided
        if date_range and len(date_range) == 2:
            start_date, end_date = date_range
            filtered_items = []
            for item in items:
                created_at = item.get('created_at', '')
                if start_date <= created_at <= end_date:
                    filtered_items.append(item)
            items = filtered_items
        
        # Helper function to convert Decimal to float
        def to_num(val):
            if isinstance(val, Decimal):
                return float(val)
            return val
        
        # Calculate summary statistics
        total_cost = sum(to_num(item.get('total_cost_usd', 0)) for item in items)
        total_tokens = sum(to_num(item.get('total_tokens', 0)) for item in items)
        total_api_calls = sum(to_num(item.get('total_api_calls', 0)) for item in items)
        total_cached_calls = sum(to_num(item.get('total_cached_calls', 0)) for item in items)
        total_rows_processed = sum(to_num(item.get('processed_rows', 0)) for item in items)
        
        # Remove cache hit rate calculation as requested
        
        return {
            'sessions': items,
            'count': len(items),
            'summary': {
                'total_cost': total_cost,
                'total_tokens': total_tokens,
                'total_api_calls': total_api_calls,
                'total_cached_calls': total_cached_calls,
                'total_rows_processed': total_rows_processed,

                'avg_cost_per_session': total_cost / len(items) if items else 0,
                'avg_tokens_per_session': total_tokens / len(items) if items else 0
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting call analytics: {e}")
        return {'sessions': [], 'count': 0, 'summary': {}}


def create_user_validation_table():
    """Create the user validation table."""
    schemas = DynamoDBSchemas()
    try:
        dynamodb_client.create_table(**schemas.get_user_validation_schema())
        logger.info(f"Created {schemas.USER_VALIDATION_TABLE} table")
        
        # Enable TTL after table creation
        try:
            # Wait a moment for table to be ready
            import time
            time.sleep(2)
            
            dynamodb_client.update_time_to_live(
                TableName=schemas.USER_VALIDATION_TABLE,
                TimeToLiveSpecification={
                    'AttributeName': 'ttl',
                    'Enabled': True
                }
            )
            logger.info(f"TTL enabled for {schemas.USER_VALIDATION_TABLE}")
        except Exception as ttl_error:
            logger.warning(f"Failed to enable TTL (may already be enabled): {ttl_error}")
        
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            logger.info(f"Table {schemas.USER_VALIDATION_TABLE} already exists")
            
            # Try to enable TTL if table exists
            try:
                dynamodb_client.update_time_to_live(
                    TableName=schemas.USER_VALIDATION_TABLE,
                    TimeToLiveSpecification={
                        'AttributeName': 'ttl',
                        'Enabled': True
                    }
                )
                logger.info(f"TTL enabled for existing {schemas.USER_VALIDATION_TABLE}")
            except Exception as ttl_error:
                logger.warning(f"Failed to enable TTL (may already be enabled): {ttl_error}")
            
            return True
        else:
            logger.error(f"Error creating user validation table: {e}")
            return False


def create_user_tracking_table():
    """Create the user tracking table."""
    schemas = DynamoDBSchemas()
    try:
        dynamodb_client.create_table(**schemas.get_user_tracking_schema())
        logger.info(f"Created {schemas.USER_TRACKING_TABLE} table")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            logger.info(f"Table {schemas.USER_TRACKING_TABLE} already exists")
            return True
        else:
            logger.error(f"Error creating user tracking table: {e}")
            return False


def generate_validation_code() -> str:
    """Generate a 6-digit numerical validation code."""
    import random
    return f"{random.randint(100000, 999999)}"


def send_validation_email(email: str, validation_code: str) -> bool:
    """Send validation email with 6-digit code."""
    try:
        from email_sender import send_validation_code_email
        result = send_validation_code_email(email, validation_code)
        return result.get('success', False)
    except ImportError:
        logger.error("Email sender module not available")
        return False
    except Exception as e:
        logger.error(f"Error sending validation email: {e}")
        return False


def create_email_validation_request(email: str) -> Dict[str, Any]:
    """
    Create email validation request and send validation code.
    Returns validation data or error info.
    """
    try:
        import re
        from datetime import timedelta
        
        # Normalize email to lowercase
        email = email.lower().strip()
        
        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return {
                'success': False,
                'validated': False,
                'error': 'invalid_email',
                'message': 'Invalid email address format'
            }
        
        # Generate validation code and expiry
        validation_code = generate_validation_code()
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(minutes=10)
        ttl = int(expires_at.timestamp())  # TTL for DynamoDB
        
        # Store validation request in DynamoDB
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.USER_VALIDATION_TABLE)
        
        validation_item = {
            'email': email,
            'validation_code': validation_code,
            'created_at': created_at.isoformat(),
            'expires_at': expires_at.isoformat(),
            'ttl': ttl,
            'attempts': 0,
            'validated': False,
            'validation_requested_at': created_at.isoformat()
        }
        
        table.put_item(Item=validation_item)
        
        # Send validation email
        email_sent = send_validation_email(email, validation_code)
        
        if not email_sent:
            # Clean up the validation record if email failed
            table.delete_item(Key={'email': email})
            return {
                'success': False,
                'validated': False,
                'error': 'email_send_failed',
                'message': 'Failed to send validation email'
            }
        
        # Track that validation was requested (first time or repeat)
        track_validation_request(email, created_at.isoformat())
        
        return {
            'success': True,
            'message': 'Validation code sent to email',
            'expires_at': expires_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error creating email validation request: {e}")
        return {
            'success': False,
            'validated': False,
            'error': 'internal_error',
            'message': f'Internal error: {str(e)}'
        }


def validate_email_code(email: str, code: str) -> Dict[str, Any]:
    """
    Validate email with provided code.
    Returns validation result.
    """
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.USER_VALIDATION_TABLE)
        
        # Get validation record
        response = table.get_item(Key={'email': email})
        
        if 'Item' not in response:
            return {
                'success': False,
                'validated': False,
                'error': 'no_validation_request',
                'message': 'No validation request found for this email'
            }
        
        validation_record = response['Item']
        
        # Check if already validated
        if validation_record.get('validated', False):
            return {
                'success': True,
                'validated': True,
                'message': 'Email already validated'
            }
        
        # Check expiry
        expires_at = datetime.fromisoformat(validation_record['expires_at'].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_at:
            # Clean up expired record
            table.delete_item(Key={'email': email})
            return {
                'success': False,
                'validated': False,
                'error': 'code_expired',
                'message': 'Validation code has expired'
            }
        
        # Check attempts limit
        attempts = validation_record.get('attempts', 0)
        if attempts >= 3:
            # Clean up after too many attempts
            table.delete_item(Key={'email': email})
            return {
                'success': False,
                'validated': False,
                'error': 'too_many_attempts',
                'message': 'Too many validation attempts'
            }
        
        # Check code
        if validation_record['validation_code'] != code:
            # Increment attempts
            table.update_item(
                Key={'email': email},
                UpdateExpression="SET attempts = attempts + :inc",
                ExpressionAttributeValues={':inc': 1}
            )
            return {
                'success': False,
                'validated': False,
                'error': 'invalid_code',
                'message': 'Invalid validation code'
            }
        
        # Code is correct - mark as validated and remove TTL
        validated_at = datetime.now(timezone.utc).isoformat()
        table.update_item(
            Key={'email': email},
            UpdateExpression="SET validated = :val, validated_at = :timestamp REMOVE #ttl",
            ExpressionAttributeNames={
                '#ttl': 'ttl'
            },
            ExpressionAttributeValues={
                ':val': True,
                ':timestamp': validated_at
            }
        )
        
        # Initialize/update user tracking record with validation date
        initialize_user_tracking(email, validated_at)
        
        return {
            'success': True,
            'validated': True,
            'message': 'Email validated successfully'
        }
        
    except Exception as e:
        logger.error(f"Error validating email code: {e}")
        return {
            'success': False,
            'validated': False,
            'error': 'internal_error',
            'message': f'Internal error: {str(e)}'
        }


def is_email_validated(email: str) -> bool:
    """Check if email is validated."""
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.USER_VALIDATION_TABLE)
        response = table.get_item(Key={'email': email})
        
        if 'Item' not in response:
            return False
        
        validation_record = response['Item']
        
        # Check if validated - no need to check expiry for validated emails
        # since we remove TTL on successful validation
        if validation_record.get('validated', False):
            return True
        
        # For unvalidated records, check if expired
        if 'expires_at' in validation_record:
            expires_at = datetime.fromisoformat(validation_record['expires_at'].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expires_at:
                # Clean up expired unvalidated record
                table.delete_item(Key={'email': email})
                return False
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking email validation: {e}")
        return False


def initialize_user_tracking(email: str, validated_at: str = None) -> bool:
    """Initialize user tracking record for a newly validated email."""
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        email_domain = email.split('@')[-1] if '@' in email else 'unknown'
        current_time = validated_at or datetime.now(timezone.utc).isoformat()
        
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.USER_TRACKING_TABLE)
        
        # Check if user tracking already exists
        response = table.get_item(Key={'email': email})
        
        if 'Item' in response:
            # User already exists, update last access and validation dates
            current_data = response['Item']
            update_expr = "SET last_access = :timestamp"
            expr_values = {':timestamp': current_time}
            
            # If this is a new validation (validated_at provided), update validation dates
            if validated_at:
                # Check if this is the first validation for this user
                if 'first_email_validation' not in current_data:
                    # First validation - set both first and most recent
                    update_expr += ", first_email_validation = :validation_date, most_recent_email_validation = :validation_date"
                    expr_values[':validation_date'] = validated_at
                else:
                    # Subsequent validation - only update most recent
                    update_expr += ", most_recent_email_validation = :validation_date"
                    expr_values[':validation_date'] = validated_at
            
            table.update_item(
                Key={'email': email},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values
            )
            return True
        
        # Create new user tracking record
        user_record = {
            'email': email,
            'email_domain': email_domain,
            'created_at': current_time,
            'last_access': current_time,
            'total_preview_requests': 0,
            'total_full_requests': 0,
            'total_tokens_used': 0,
            'total_cost_usd': Decimal('0.0'),
            'perplexity_tokens': 0,
            'perplexity_cost': Decimal('0.0'),
            'anthropic_tokens': 0,
            'anthropic_cost': Decimal('0.0')
        }
        
        # Add validation dates if this is a validation event
        if validated_at:
            user_record['first_email_validation'] = validated_at
            user_record['most_recent_email_validation'] = validated_at
        
        table.put_item(Item=user_record)
        logger.info(f"Initialized user tracking for {email}")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing user tracking: {e}")
        return False


def track_user_request(email: str, request_type: str, tokens_used: int = 0, 
                      cost_usd: float = 0.0, provider: str = '', 
                      perplexity_tokens: int = 0, perplexity_cost: float = 0.0,
                      anthropic_tokens: int = 0, anthropic_cost: float = 0.0) -> bool:
    """Track user request and update usage statistics."""
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.USER_TRACKING_TABLE)
        
        # Get current user record
        response = table.get_item(Key={'email': email})
        
        if 'Item' not in response:
            # Initialize if doesn't exist
            initialize_user_tracking(email)
            response = table.get_item(Key={'email': email})
        
        current_data = response['Item']
        
        # Helper function to convert to number for arithmetic
        def to_num(val):
            if isinstance(val, Decimal):
                return float(val)
            return val
        
        # Calculate updates
        updates = {
            'last_access': datetime.now(timezone.utc).isoformat(),
            'total_tokens_used': to_num(current_data.get('total_tokens_used', 0)) + tokens_used,
            'total_cost_usd': to_num(current_data.get('total_cost_usd', 0)) + cost_usd,
            'perplexity_tokens': to_num(current_data.get('perplexity_tokens', 0)) + perplexity_tokens,
            'perplexity_cost': to_num(current_data.get('perplexity_cost', 0)) + perplexity_cost,
            'anthropic_tokens': to_num(current_data.get('anthropic_tokens', 0)) + anthropic_tokens,
            'anthropic_cost': to_num(current_data.get('anthropic_cost', 0)) + anthropic_cost
        }
        
        # Update request type count
        if request_type == 'preview':
            updates['total_preview_requests'] = to_num(current_data.get('total_preview_requests', 0)) + 1
        elif request_type == 'full':
            updates['total_full_requests'] = to_num(current_data.get('total_full_requests', 0)) + 1
        
        # Build update expression
        update_parts = []
        expression_values = {}
        
        for key, value in updates.items():
            placeholder = f":{key}"
            update_parts.append(f"{key} = {placeholder}")
            expression_values[placeholder] = value
        
        update_expression = "SET " + ", ".join(update_parts)
        
        # Convert floats to Decimal for DynamoDB
        expression_values = convert_floats_to_decimal(expression_values)
        
        table.update_item(
            Key={'email': email},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error tracking user request: {e}")
        return False


def track_validation_request(email: str, requested_at: str) -> bool:
    """Track when an email validation was requested."""
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        
        # Initialize/update user tracking with request date if user doesn't exist
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.USER_TRACKING_TABLE)
        response = table.get_item(Key={'email': email})
        
        if 'Item' not in response:
            # First time user - create record with first validation request date
            initialize_user_tracking(email)
            table.update_item(
                Key={'email': email},
                UpdateExpression="SET first_email_validation_request = :req_date, most_recent_email_validation_request = :req_date",
                ExpressionAttributeValues={
                    ':req_date': requested_at
                }
            )
        else:
            # Existing user - update most recent request date
            # Only set first request date if it doesn't exist
            current_data = response['Item']
            if 'first_email_validation_request' not in current_data:
                table.update_item(
                    Key={'email': email},
                    UpdateExpression="SET first_email_validation_request = :req_date, most_recent_email_validation_request = :req_date",
                    ExpressionAttributeValues={
                        ':req_date': requested_at
                    }
                )
            else:
                table.update_item(
                    Key={'email': email},
                    UpdateExpression="SET most_recent_email_validation_request = :req_date",
                    ExpressionAttributeValues={
                        ':req_date': requested_at
                    }
                )
        
        logger.info(f"Tracked validation request for {email} at {requested_at}")
        return True
        
    except Exception as e:
        logger.error(f"Error tracking validation request: {e}")
        return False


def get_user_stats(email: str) -> Dict[str, Any]:
    """Get user usage statistics."""
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.USER_TRACKING_TABLE)
        response = table.get_item(Key={'email': email})
        
        if 'Item' not in response:
            return {'exists': False}
        
        # Convert Decimals to floats for JSON serialization
        user_data = response['Item']
        for key, value in user_data.items():
            if isinstance(value, Decimal):
                user_data[key] = float(value)
        
        user_data['exists'] = True
        return user_data
        
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {'exists': False, 'error': str(e)}


def check_or_send_validation(email: str) -> Dict[str, Any]:
    """
    Single function to check if email is validated or send validation code.
    
    Returns:
        - If validated: {'success': True, 'validated': True, 'message': 'Email is already validated'}
        - If not validated: Sends code and returns {'success': True, 'validated': False, 'message': 'Validation code sent to email', 'expires_at': '...'}
        - On error: {'success': False, 'error': '...', 'message': '...'}
    """
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        
        # First check if email is already validated
        if is_email_validated(email):
            return {
                'success': True,
                'validated': True,
                'message': 'Email is already validated'
            }
        
        # Email not validated, send validation code
        result = create_email_validation_request(email)
        
        # Add validated flag to response
        if result.get('success'):
            result['validated'] = False
        
        return result
        
    except Exception as e:
        logger.error(f"Error in check_or_send_validation: {e}")
        return {
            'success': False,
            'validated': False,
            'error': 'internal_error',
            'message': f'Internal error: {str(e)}'
        } 

# --- Validation Run Tracking ---

VALIDATION_RUNS_TABLE_NAME = "perplexity-validator-runs"

def create_validation_runs_table():
    """Creates the DynamoDB table for tracking validation runs."""
    try:
        # Use the client for operations like waiting
        dynamodb_client = boto3.client('dynamodb')
        
        # Use the resource for higher-level table operations
        dynamodb_resource = boto3.resource('dynamodb')
        
        dynamodb_resource.create_table(
            TableName=VALIDATION_RUNS_TABLE_NAME,
            KeySchema=[{'AttributeName': 'session_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'session_id', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        waiter = dynamodb_client.get_waiter('table_exists')
        waiter.wait(TableName=VALIDATION_RUNS_TABLE_NAME)
        logger.info(f"Table {VALIDATION_RUNS_TABLE_NAME} created successfully.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            logger.info(f"Table {VALIDATION_RUNS_TABLE_NAME} already exists.")
        else:
            raise

def create_run_record(session_id: str, email: str, total_rows: int):
    """Creates an initial record for a new validation run."""
    try:
        table = dynamodb.Table(VALIDATION_RUNS_TABLE_NAME)
        table.put_item(
            Item={
                'session_id': session_id,
                'email': email,
                'status': 'PENDING',
                'total_rows': total_rows,
                'processed_rows': 0,
                'start_time': datetime.now(timezone.utc).isoformat(),
                'last_update': datetime.now(timezone.utc).isoformat()
            }
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.warning(f"Table {VALIDATION_RUNS_TABLE_NAME} not found. Attempting to create it now.")
            create_validation_runs_table()
            # Retry the operation once after creating the table
            table.put_item(
                Item={
                    'session_id': session_id,
                    'email': email,
                    'status': 'PENDING',
                    'total_rows': total_rows,
                    'processed_rows': 0,
                    'start_time': datetime.now(timezone.utc).isoformat(),
                    'last_update': datetime.now(timezone.utc).isoformat()
                }
            )
        else:
            raise

def update_run_status(session_id: str, status: str, processed_rows: int = None, error_message: str = None, results_s3_key: str = None, verbose_status: str = None, percent_complete: int = None, email_status: str = None, preview_data: dict = None):
    """Updates the status and progress of a validation run."""
    table = dynamodb.Table(VALIDATION_RUNS_TABLE_NAME)
    
    now = datetime.now(timezone.utc).isoformat()
    update_expression = "SET #st = :status, last_update = :now"
    expression_attribute_values = {':status': status, ':now': now}
    expression_attribute_names = {'#st': 'status'}

    if processed_rows is not None:
        update_expression += ", processed_rows = :pr"
        expression_attribute_values[':pr'] = processed_rows
    if verbose_status:
        update_expression += ", verbose_status = :vs"
        expression_attribute_values[':vs'] = verbose_status
    if percent_complete is not None:
        update_expression += ", percent_complete = :pc"
        expression_attribute_values[':pc'] = percent_complete
    if email_status:
        update_expression += ", email_status = :es"
        expression_attribute_values[':es'] = email_status
    if error_message:
        update_expression += ", error_message = :err"
        expression_attribute_values[':err'] = error_message
    if results_s3_key:
        update_expression += ", results_s3_key = :s3"
        expression_attribute_values[':s3'] = results_s3_key
    if preview_data:
        update_expression += ", preview_data = :pd"
        expression_attribute_values[':pd'] = convert_floats_to_decimal(preview_data)
    if status in ['COMPLETED', 'FAILED']:
        update_expression += ", end_time = :et"
        expression_attribute_values[':et'] = now

    table.update_item(
        Key={'session_id': session_id},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_attribute_values,
        ExpressionAttributeNames=expression_attribute_names
    )

def get_run_status(session_id: str) -> Optional[Dict]:
    """Retrieves the status of a validation run."""
    table = dynamodb.Table(VALIDATION_RUNS_TABLE_NAME)
    try:
        response = table.get_item(Key={'session_id': session_id})
        return response.get('Item')
    except ClientError as e:
        logger.error(f"Error getting run status for {session_id}: {e}")
        return None 

# --- WebSocket Connection Tracking ---

WEBSOCKET_CONNECTIONS_TABLE_NAME = "perplexity-validator-ws-connections"

def create_websocket_connections_table():
    """Creates the DynamoDB table for tracking WebSocket connections."""
    try:
        dynamodb.create_table(
            TableName=WEBSOCKET_CONNECTIONS_TABLE_NAME,
            KeySchema=[{'AttributeName': 'connectionId', 'KeyType': 'HASH'}],
            AttributeDefinitions=[
                {'AttributeName': 'connectionId', 'AttributeType': 'S'},
                {'AttributeName': 'sessionId', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[{
                'IndexName': 'SessionIdIndex',
                'KeySchema': [{'AttributeName': 'sessionId', 'KeyType': 'HASH'}],
                'Projection': {'ProjectionType': 'ALL'}
            }],
            BillingMode='PAY_PER_REQUEST'
        )
        waiter = boto3.client('dynamodb').get_waiter('table_exists')
        waiter.wait(TableName=WEBSOCKET_CONNECTIONS_TABLE_NAME)
        logger.info(f"Table {WEBSOCKET_CONNECTIONS_TABLE_NAME} created successfully with GSI.")
        
        # Enable TTL after table creation
        try:
            dynamodb_client.update_time_to_live(
                TableName=WEBSOCKET_CONNECTIONS_TABLE_NAME,
                TimeToLiveSpecification={'AttributeName': 'ttl', 'Enabled': True}
            )
            logger.info(f"TTL enabled for {WEBSOCKET_CONNECTIONS_TABLE_NAME}")
        except Exception as ttl_error:
            logger.warning(f"Failed to enable TTL for {WEBSOCKET_CONNECTIONS_TABLE_NAME}: {ttl_error}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            logger.info(f"Table {WEBSOCKET_CONNECTIONS_TABLE_NAME} already exists.")
        else:
            raise

def add_websocket_connection(connection_id: str):
    """Adds a new WebSocket connection to the table."""
    table = dynamodb.Table(WEBSOCKET_CONNECTIONS_TABLE_NAME)
    ttl = int(time.time()) + (2 * 60 * 60) # 2-hour TTL
    table.put_item(Item={'connectionId': connection_id, 'ttl': ttl})

def remove_websocket_connection(connection_id: str):
    """Removes a WebSocket connection from the table."""
    table = dynamodb.Table(WEBSOCKET_CONNECTIONS_TABLE_NAME)
    table.delete_item(Key={'connectionId': connection_id})

def associate_session_with_connection(connection_id: str, session_id: str):
    """Associates a session_id with a connection_id, removing old connections for the same session."""
    table = dynamodb.Table(WEBSOCKET_CONNECTIONS_TABLE_NAME)
    
    # First, find and remove any existing connections for this session
    try:
        existing_connections = get_connections_for_session(session_id)
        for old_connection_id in existing_connections:
            if old_connection_id != connection_id:
                logger.info(f"Removing old connection {old_connection_id} for session {session_id}")
                try:
                    table.delete_item(Key={'connectionId': old_connection_id})
                except Exception as e:
                    logger.warning(f"Failed to remove old connection {old_connection_id}: {e}")
    except Exception as e:
        logger.warning(f"Error checking for existing connections: {e}")
    
    # Now associate the new connection
    table.update_item(
        Key={'connectionId': connection_id},
        UpdateExpression="SET sessionId = :sid",
        ExpressionAttributeValues={':sid': session_id}
    )

def get_connection_by_session(session_id: str) -> Optional[str]:
    """Finds a connectionId associated with a session_id using the GSI."""
    table = dynamodb.Table(WEBSOCKET_CONNECTIONS_TABLE_NAME)
    try:
        response = table.query(
            IndexName='SessionIdIndex',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('sessionId').eq(session_id)
        )
        items = response.get('Items', [])
        if items:
            return items[0]['connectionId']
        return None
    except ClientError as e:
        logger.error(f"Error querying for connection by session {session_id}: {e}")
        return None

def get_connections_for_session(session_id: str) -> List[str]:
    """Finds all connectionIds associated with a session_id using the GSI."""
    table = dynamodb.Table(WEBSOCKET_CONNECTIONS_TABLE_NAME)
    try:
        response = table.query(
            IndexName='SessionIdIndex',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('sessionId').eq(session_id)
        )
        items = response.get('Items', [])
        return [item['connectionId'] for item in items]
    except ClientError as e:
        logger.error(f"Error querying for connections by session {session_id}: {e}")
        return [] 