#!/usr/bin/env python3
"""
Batch Size Audit Logger for DynamoDB

This module provides audit logging for batch size changes to track
system behavior and performance tuning over time.
"""

import boto3
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# Table name
BATCH_AUDIT_TABLE = "perplexity-validator-batch-audit"


class BatchAuditLogger:
    """Handles audit logging of batch size changes to DynamoDB."""
    
    def __init__(self, table_name: str = BATCH_AUDIT_TABLE):
        """
        Initialize the audit logger.
        
        Args:
            table_name: Name of the DynamoDB table for audit logs
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
        
    def log_batch_size_change(self, 
                            model: str,
                            old_batch_size: int,
                            new_batch_size: int,
                            change_reason: str,
                            session_id: Optional[str] = None,
                            additional_context: Optional[Dict] = None) -> str:
        """
        Log a batch size change event.
        
        Args:
            model: The model name that had its batch size changed
            old_batch_size: Previous batch size
            new_batch_size: New batch size
            change_reason: Reason for the change (e.g., 'rate_limit', 'success_streak', 'initialization')
            session_id: Optional session ID if this change was during a specific session
            additional_context: Additional context information
            
        Returns:
            str: The audit log entry ID
        """
        try:
            audit_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            
            # Calculate change metrics
            change_amount = new_batch_size - old_batch_size
            change_percent = ((new_batch_size - old_batch_size) / old_batch_size * 100) if old_batch_size > 0 else 0
            
            item = {
                'audit_id': audit_id,
                'timestamp': timestamp,
                'model': model,
                'old_batch_size': old_batch_size,
                'new_batch_size': new_batch_size,
                'change_amount': change_amount,
                'change_percent': Decimal(str(round(change_percent, 2))),
                'change_reason': change_reason,
                'session_id': session_id or 'none',
                'additional_context': json.dumps(additional_context) if additional_context else '{}',
                
                # TTL: Keep audit logs for 90 days
                'ttl': int((datetime.now(timezone.utc).timestamp() + (90 * 24 * 60 * 60)))
            }
            
            self.table.put_item(Item=item)
            
            logger.info(f"[BATCH AUDIT] {model}: {old_batch_size} → {new_batch_size} "
                       f"({change_amount:+d}, {change_percent:+.1f}%) - {change_reason}")
            
            return audit_id
            
        except Exception as e:
            logger.error(f"Failed to log batch size change: {e}")
            return ""
    
    def log_model_registration(self, 
                             model: str,
                             initial_config: Dict,
                             session_id: Optional[str] = None) -> str:
        """
        Log when a new model is registered.
        
        Args:
            model: The model name being registered
            initial_config: The initial configuration applied
            session_id: Optional session ID
            
        Returns:
            str: The audit log entry ID
        """
        return self.log_batch_size_change(
            model=model,
            old_batch_size=0,
            new_batch_size=initial_config.get('initial_batch_size', 50),
            change_reason='model_registration',
            session_id=session_id,
            additional_context={
                'config_pattern': initial_config.get('model_pattern', 'unknown'),
                'priority': initial_config.get('priority', 999),
                'min_batch_size': initial_config.get('min_batch_size', 10),
                'max_batch_size': initial_config.get('max_batch_size', 100),
                'weight': initial_config.get('weight', 1.0)
            }
        )
    
    def get_model_history(self, model: str, limit: int = 50) -> List[Dict]:
        """
        Get audit history for a specific model.
        
        Args:
            model: Model name to query
            limit: Maximum number of records to return
            
        Returns:
            List of audit records, newest first
        """
        try:
            response = self.table.query(
                IndexName='ModelTimestampIndex',
                KeyConditionExpression='model = :model',
                ExpressionAttributeValues={':model': model},
                ScanIndexForward=False,  # Newest first
                Limit=limit
            )
            
            return response.get('Items', [])
            
        except Exception as e:
            logger.error(f"Failed to get model history for {model}: {e}")
            return []
    
    def get_recent_changes(self, hours: int = 24, limit: int = 100) -> List[Dict]:
        """
        Get recent batch size changes across all models.
        
        Args:
            hours: How many hours back to look
            limit: Maximum number of records to return
            
        Returns:
            List of recent audit records, newest first
        """
        try:
            # Calculate timestamp for X hours ago
            cutoff_time = datetime.now(timezone.utc).timestamp() - (hours * 3600)
            cutoff_iso = datetime.fromtimestamp(cutoff_time, timezone.utc).isoformat()
            
            response = self.table.query(
                IndexName='TimestampIndex',
                KeyConditionExpression='timestamp >= :cutoff',
                ExpressionAttributeValues={':cutoff': cutoff_iso},
                ScanIndexForward=False,  # Newest first
                Limit=limit
            )
            
            return response.get('Items', [])
            
        except Exception as e:
            logger.error(f"Failed to get recent changes: {e}")
            return []
    
    def get_session_changes(self, session_id: str) -> List[Dict]:
        """
        Get all batch size changes for a specific session.
        
        Args:
            session_id: Session ID to query
            
        Returns:
            List of audit records for the session
        """
        try:
            response = self.table.query(
                IndexName='SessionIndex',
                KeyConditionExpression='session_id = :session_id',
                ExpressionAttributeValues={':session_id': session_id},
                ScanIndexForward=False  # Newest first
            )
            
            return response.get('Items', [])
            
        except Exception as e:
            logger.error(f"Failed to get session changes for {session_id}: {e}")
            return []


def create_batch_audit_table():
    """Create the batch audit table with proper schema and indexes."""
    dynamodb = boto3.resource('dynamodb')
    
    table_config = {
        'TableName': BATCH_AUDIT_TABLE,
        'KeySchema': [
            {
                'AttributeName': 'audit_id',
                'KeyType': 'HASH'  # Partition key
            },
            {
                'AttributeName': 'timestamp',
                'KeyType': 'RANGE'  # Sort key
            }
        ],
        'AttributeDefinitions': [
            {
                'AttributeName': 'audit_id',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'timestamp',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'model',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'session_id',
                'AttributeType': 'S'
            }
        ],
        'GlobalSecondaryIndexes': [
            {
                'IndexName': 'ModelTimestampIndex',
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
            },
            {
                'IndexName': 'TimestampIndex',
                'KeySchema': [
                    {
                        'AttributeName': 'timestamp',
                        'KeyType': 'HASH'
                    }
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                }
            },
            {
                'IndexName': 'SessionIndex',
                'KeySchema': [
                    {
                        'AttributeName': 'session_id',
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
    
    try:
        table = dynamodb.create_table(**table_config)
        print(f"Creating table {BATCH_AUDIT_TABLE}...")
        
        # Wait for table to be created
        table.wait_until_exists()
        print(f"Table {BATCH_AUDIT_TABLE} created successfully!")
        
        return table
        
    except Exception as e:
        print(f"Error creating table: {e}")
        return None


if __name__ == "__main__":
    # Test the audit logger
    logging.basicConfig(level=logging.INFO)
    
    # Note: This will try to connect to AWS
    try:
        # Create table (comment out if it already exists)
        # create_batch_audit_table()
        
        # Test audit logging
        audit_logger = BatchAuditLogger()
        
        # Test model registration
        audit_id = audit_logger.log_model_registration(
            model="claude-3.5-sonnet-test",
            initial_config={
                'model_pattern': 'claude-3.5*',
                'initial_batch_size': 80,
                'min_batch_size': 10,
                'max_batch_size': 150,
                'priority': 2,
                'weight': 1.3
            },
            session_id="test_session_123"
        )
        print(f"Logged model registration with ID: {audit_id}")
        
        # Test batch size changes
        audit_logger.log_batch_size_change(
            model="claude-3.5-sonnet-test",
            old_batch_size=80,
            new_batch_size=60,
            change_reason="rate_limit",
            session_id="test_session_123",
            additional_context={"rate_limit_count": 1}
        )
        
        audit_logger.log_batch_size_change(
            model="claude-3.5-sonnet-test",
            old_batch_size=60,
            new_batch_size=66,
            change_reason="success_streak",
            session_id="test_session_123",
            additional_context={"consecutive_successes": 5}
        )
        
        print("Audit logging test completed!")
        
    except Exception as e:
        print(f"Test failed: {e}")
        print("Note: This test requires AWS credentials and DynamoDB access.")