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

def validate_cost_fields(eliyahu_cost: float = None, quoted_validation_cost: float = None, 
                        estimated_validation_eliyahu_cost: float = None, operation_type: str = "validation") -> Dict[str, Any]:
    """
    Validate the three-tier cost system fields for consistency and business logic.
    
    Args:
        eliyahu_cost: Actual cost paid (with caching benefits)
        quoted_validation_cost: What user pays (with multiplier, rounding, $2 min)
        estimated_validation_eliyahu_cost: Raw cost estimate without caching benefit
        operation_type: Type of operation (validation, config, preview)
        
    Returns:
        Dictionary with validation results and sanitized values
    """
    validation_result = {
        'is_valid': True,
        'warnings': [],
        'errors': [],
        'sanitized_values': {},
        'audit_info': {
            'validation_timestamp': datetime.now(timezone.utc).isoformat(),
            'operation_type': operation_type
        }
    }
    
    # Sanitize and validate individual cost fields
    costs = {
        'eliyahu_cost': eliyahu_cost,
        'quoted_validation_cost': quoted_validation_cost,
        'estimated_validation_eliyahu_cost': estimated_validation_eliyahu_cost
    }
    
    sanitized_costs = {}
    
    for cost_name, cost_value in costs.items():
        if cost_value is not None:
            try:
                # Convert to float and validate
                cost_float = float(cost_value)
                
                # Validate non-negative
                if cost_float < 0:
                    validation_result['errors'].append(f"{cost_name} cannot be negative: ${cost_float:.6f}")
                    cost_float = 0.0
                    validation_result['is_valid'] = False
                
                # Validate reasonable range (not more than $1000)
                if cost_float > 1000.0:
                    validation_result['warnings'].append(f"{cost_name} is unusually high: ${cost_float:.6f}")
                
                # Convert to Decimal with proper precision
                sanitized_costs[cost_name] = Decimal(str(round(cost_float, 6)))
                
            except (ValueError, TypeError) as e:
                validation_result['errors'].append(f"Invalid {cost_name} value: {cost_value} ({e})")
                sanitized_costs[cost_name] = Decimal('0.0')
                validation_result['is_valid'] = False
    
    # Business logic validation for three-tier cost relationships
    if len(sanitized_costs) >= 2:
        eliyahu = sanitized_costs.get('eliyahu_cost')
        quoted = sanitized_costs.get('quoted_validation_cost') 
        estimated = sanitized_costs.get('estimated_validation_eliyahu_cost')
        
        # Validation Rule 1: Estimated cost (without cache) >= Actual cost (with cache)
        if eliyahu is not None and estimated is not None:
            if estimated < eliyahu:
                validation_result['warnings'].append(
                    f"Estimated cost without cache (${estimated}) < actual cost with cache (${eliyahu}) - unusual but possible"
                )
        
        # Validation Rule 2: For validation operations, quoted cost should be >= $2 (minimum)
        if operation_type in ['validation', 'full_validation'] and quoted is not None:
            if quoted > 0 and quoted < Decimal('2.0'):
                validation_result['warnings'].append(
                    f"Quoted validation cost ${quoted} is below $2 minimum - should be rounded up"
                )
        
        # Validation Rule 3: Config operations should typically have quoted_cost = 0 (free to users)
        if operation_type in ['config', 'config_generation'] and quoted is not None:
            if quoted > 0:
                validation_result['warnings'].append(
                    f"Config operations should be free to users, but quoted_cost = ${quoted}"
                )
        
        # Validation Rule 4: Consistency checks for extreme differences
        if eliyahu is not None and quoted is not None and eliyahu > 0:
            ratio = float(quoted / eliyahu) if eliyahu > 0 else 0
            if ratio > 50:  # More than 50x markup is suspicious
                validation_result['warnings'].append(
                    f"Quoted cost ${quoted} is {ratio:.1f}x higher than internal cost ${eliyahu} - check domain multiplier"
                )
    
    validation_result['sanitized_values'] = sanitized_costs
    
    # Log validation results for audit
    if validation_result['errors']:
        logger.error(f"[COST_VALIDATION] Errors in cost field validation: {validation_result['errors']}")
    if validation_result['warnings']:
        logger.warning(f"[COST_VALIDATION] Warnings in cost field validation: {validation_result['warnings']}")
    
    return validation_result

def create_cost_update_transaction(session_id: str, run_key: str, validation_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create an atomic DynamoDB transaction for cost field updates with audit trail.
    
    Args:
        session_id: Session identifier
        run_key: Run key for the record
        validation_result: Result from validate_cost_fields
        
    Returns:
        List of DynamoDB transaction items
    """
    try:
        transaction_items = []
        sanitized_costs = validation_result.get('sanitized_values', {})
        
        if not sanitized_costs:
            return transaction_items
        
        # Main update to runs table
        update_expression_parts = []
        expression_attribute_values = {}
        expression_attribute_names = {}
        
        # Add validated cost fields
        for cost_name, cost_value in sanitized_costs.items():
            if cost_value is not None:
                attr_name = f"#{cost_name}"
                attr_value = f":{cost_name}"
                update_expression_parts.append(f"{attr_name} = {attr_value}")
                expression_attribute_names[attr_name] = cost_name
                expression_attribute_values[attr_value] = cost_value
        
        # Add validation metadata
        update_expression_parts.append("#cost_validation_info = :cost_validation_info")
        expression_attribute_names["#cost_validation_info"] = "cost_validation_info"
        expression_attribute_values[":cost_validation_info"] = {
            'validation_timestamp': validation_result['audit_info']['validation_timestamp'],
            'is_valid': validation_result['is_valid'],
            'warnings_count': len(validation_result['warnings']),
            'errors_count': len(validation_result['errors']),
            'operation_type': validation_result['audit_info']['operation_type']
        }
        
        update_expression_parts.append("last_cost_update = :last_cost_update")
        expression_attribute_values[":last_cost_update"] = datetime.now(timezone.utc).isoformat()
        
        main_update = {
            'Update': {
                'TableName': VALIDATION_RUNS_TABLE_NAME,
                'Key': {
                    'session_id': {'S': session_id},
                    'run_key': {'S': run_key}
                },
                'UpdateExpression': f"SET {', '.join(update_expression_parts)}",
                'ExpressionAttributeNames': {k: v for k, v in expression_attribute_names.items()},
                'ExpressionAttributeValues': {
                    k: {'N' if isinstance(v, Decimal) else 'S' if isinstance(v, str) else 'M': 
                        str(v) if isinstance(v, Decimal) else v if isinstance(v, str) else convert_floats_to_decimal(v)}
                    for k, v in expression_attribute_values.items()
                },
                'ConditionExpression': 'attribute_exists(session_id) AND attribute_exists(run_key)'
            }
        }
        transaction_items.append(main_update)
        
        # Add audit trail entry if there were warnings or errors
        if validation_result['warnings'] or validation_result['errors']:
            audit_entry = {
                'Put': {
                    'TableName': 'perplexity-validator-cost-audit',  # Audit table
                    'Item': {
                        'audit_id': {'S': f"{session_id}#{run_key}#{int(time.time())}"},
                        'session_id': {'S': session_id},
                        'run_key': {'S': run_key},
                        'timestamp': {'S': validation_result['audit_info']['validation_timestamp']},
                        'operation_type': {'S': validation_result['audit_info']['operation_type']},
                        'warnings': {'S': json.dumps(validation_result['warnings'])},
                        'errors': {'S': json.dumps(validation_result['errors'])},
                        'sanitized_values': {'S': json.dumps({k: str(v) for k, v in sanitized_costs.items()})},
                        'ttl': {'N': str(int(time.time()) + (90 * 24 * 60 * 60))}  # 90 day TTL
                    }
                }
            }
            transaction_items.append(audit_entry)
        
        return transaction_items
        
    except Exception as e:
        logger.error(f"[COST_TRANSACTION] Error creating cost update transaction: {e}")
        return []

class DynamoDBSchemas:
    """DynamoDB table schemas and operations for perplexity validator."""
    
    # Table names
    CALL_TRACKING_TABLE = "perplexity-validator-call-tracking"
    TOKEN_USAGE_TABLE = "perplexity-validator-token-usage"
    USER_VALIDATION_TABLE = "perplexity-validator-user-validation"
    USER_TRACKING_TABLE = "perplexity-validator-user-tracking"
    ACCOUNT_TRANSACTIONS_TABLE = "perplexity-validator-account-transactions"
    DOMAIN_MULTIPLIERS_TABLE = "perplexity-validator-domain-multipliers"
    VALIDATION_RUNS_TABLE = "perplexity-validator-runs"
    
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
    
    @classmethod
    def get_account_transactions_schema(cls) -> Dict[str, Any]:
        """Schema for account transactions table."""
        return {
            'TableName': cls.ACCOUNT_TRANSACTIONS_TABLE,
            'KeySchema': [
                {
                    'AttributeName': 'email',
                    'KeyType': 'HASH'  # Partition key
                },
                {
                    'AttributeName': 'transaction_id',
                    'KeyType': 'RANGE'  # Sort key
                }
            ],
            'AttributeDefinitions': [
                {
                    'AttributeName': 'email',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'transaction_id',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'timestamp',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'session_id',
                    'AttributeType': 'S'
                }
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'TimestampIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'email',
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
                    'IndexName': 'SessionIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'session_id',
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
    def get_domain_multipliers_schema(cls) -> Dict[str, Any]:
        """Schema for domain cost multipliers table."""
        return {
            'TableName': cls.DOMAIN_MULTIPLIERS_TABLE,
            'KeySchema': [
                {
                    'AttributeName': 'domain',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            'AttributeDefinitions': [
                {
                    'AttributeName': 'domain',
                    'AttributeType': 'S'
                }
            ],
            'BillingMode': 'PAY_PER_REQUEST'
        }

    @classmethod  
    def get_validation_runs_schema(cls) -> Dict[str, Any]:
        """Schema for the validation runs table with composite primary key (session_id, run_type, timestamp)."""
        return {
            'TableName': cls.VALIDATION_RUNS_TABLE,
            'KeySchema': [
                {
                    'AttributeName': 'session_id',
                    'KeyType': 'HASH'  # Partition key
                },
                {
                    'AttributeName': 'run_key',  
                    'KeyType': 'RANGE'  # Sort key: combines run_type and timestamp
                }
            ],
            'AttributeDefinitions': [
                {
                    'AttributeName': 'session_id',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'run_key',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'email',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'status',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'start_time',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'last_update',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'run_type',
                    'AttributeType': 'S'
                }
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'EmailStartTimeIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'email',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'start_time',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                },
                {
                    'IndexName': 'StatusLastUpdateIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'status',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'last_update',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                },
                {
                    'IndexName': 'RunTypeStartTimeIndex', 
                    'KeySchema': [
                        {
                            'AttributeName': 'run_type',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'start_time',
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
        self._data['preview_estimated_validation_cost_usd'] = per_row_cost * total_rows
        self._data['preview_estimated_total_tokens'] = per_row_tokens * total_rows
        self._data['preview_estimated_total_time_hours'] = (per_row_time * total_rows) / 3600
        self._data['preview_estimated_total_time_without_cache_hours'] = (per_row_time_without_cache * total_rows) / 3600
    
    def set_batch_timing_estimates(self, time_per_batch: float, total_batches: int):
        """Set batch-level timing estimates (costs and tokens remain per-row)."""
        self._data['time_per_batch_seconds'] = time_per_batch
        self._data['estimated_validation_batches'] = total_batches
        
        # Update preview time estimates using batch calculations
        if total_batches > 0:
            self._data['preview_estimated_total_time_hours'] = (time_per_batch * total_batches) / 3600
    
    def set_validation_metrics(self, validated_columns: int, search_groups: int, 
                              enhanced_context_groups: int, claude_groups: int):
        """Set validation structure metrics."""
        self._data['validated_columns_count'] = validated_columns
        self._data['search_groups_count'] = search_groups
        self._data['enhanced_context_search_groups_count'] = enhanced_context_groups
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
            'preview_estimated_validation_cost_usd': 0.0,
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
            'estimated_validation_batches': 0,
            'time_per_batch_seconds': 0.0,
            
            # Validation structure metrics
            'validated_columns_count': 0,
            'search_groups_count': 0,
            'enhanced_context_search_groups_count': 0,
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

# LEGACY FUNCTION - DISABLED
# This function used the legacy call-tracking table and has been disabled
# in favor of the modern perplexity-validator-runs table tracking.
# def create_call_tracking_table(...):
#     pass
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
        
        # Create new user tracking record with consolidated field structure
        user_record = {
            'email': email,
            'email_domain': email_domain,
            'created_at': current_time,
            'last_access': current_time,
            
            # Request counts by type (using new field names)
            'total_previews': 0,
            'total_validations': 0,
            'total_configurations': 0,
            
            # Enhanced validation metrics
            'total_rows_processed': 0,
            'total_rows_analyzed': 0,
            'total_columns_validated': 0,
            'total_search_groups': 0,
            'total_high_context_search_groups': 0,
            'total_claude_calls': 0,
            
            # Cost tracking with consolidated nomenclature  
            'total_eliyahu_cost': Decimal('0.0'),
            'total_quoted_validation_cost': Decimal('0.0'),
            'total_validation_revenue': Decimal('0.0'),
            'total_config_eliyahu_cost': Decimal('0.0'),
            
            # Request-type specific metrics
            'preview_rows_processed': 0,
            'preview_eliyahu_cost': Decimal('0.0'),
            'validation_rows_processed': 0,
            'validation_revenue': Decimal('0.0'),
            'config_generation_eliyahu_cost': Decimal('0.0'),
            
            # Processing parameters tracking (per-run values)
            'batch_size': 50,  # Default batch size
            'estimated_time': 0.0,
            
            # API call tracking
            'total_api_calls_made': 0,
            'total_cached_calls_made': 0,
            
            # Account balance fields
            'account_balance': Decimal('0.0'),
            'balance_last_updated': current_time,
            'account_created_at': current_time
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
                      anthropic_tokens: int = 0, anthropic_cost: float = 0.0,
                      # NEW: Enhanced tracking metrics
                      rows_processed: int = 0, total_rows: int = 0,
                      columns_validated: int = 0, search_groups: int = 0,
                      high_context_search_groups: int = 0, claude_calls: int = 0,
                      eliyahu_cost: float = 0.0, estimated_cost: float = 0.0,
                      quoted_validation_cost: float = 0.0, charged_cost: float = 0.0,
                      config_cost: float = 0.0, batch_size: int = 0,
                      estimated_time: float = 0.0, total_api_calls: int = 0,
                      total_cached_calls: int = 0) -> bool:
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
        
        # Calculate updates using new consolidated field structure
        updates = {
            'last_access': datetime.now(timezone.utc).isoformat(),
            
            # NEW: Enhanced tracking metrics
            'total_rows_processed': to_num(current_data.get('total_rows_processed', 0)) + rows_processed,
            'total_rows_analyzed': to_num(current_data.get('total_rows_analyzed', 0)) + total_rows,
            'total_columns_validated': to_num(current_data.get('total_columns_validated', 0)) + columns_validated,
            'total_search_groups': to_num(current_data.get('total_search_groups', 0)) + search_groups,
            'total_high_context_search_groups': to_num(current_data.get('total_high_context_search_groups', 0)) + high_context_search_groups,
            'total_claude_calls': to_num(current_data.get('total_claude_calls', 0)) + claude_calls,
            
            # Cost tracking with consolidated nomenclature
            'total_eliyahu_cost': to_num(current_data.get('total_eliyahu_cost', 0)) + eliyahu_cost,
            'total_quoted_validation_cost': to_num(current_data.get('total_quoted_validation_cost', 0)) + quoted_validation_cost,
            'total_validation_revenue': to_num(current_data.get('total_validation_revenue', 0)) + charged_cost,
            'total_config_eliyahu_cost': to_num(current_data.get('total_config_eliyahu_cost', 0)) + config_cost,
            
            # NEW: Processing parameters tracking (per-run values, not cumulative)
            'batch_size': batch_size,
            'estimated_time': estimated_time,
            
            # NEW: API call tracking
            'total_api_calls_made': to_num(current_data.get('total_api_calls_made', 0)) + total_api_calls,
            'total_cached_calls_made': to_num(current_data.get('total_cached_calls_made', 0)) + total_cached_calls
        }
        
        # Update request type count and type-specific metrics (using new field names)
        if request_type == 'preview':
            updates['total_previews'] = to_num(current_data.get('total_previews', 0)) + 1
            updates['preview_rows_processed'] = to_num(current_data.get('preview_rows_processed', 0)) + rows_processed
            updates['preview_eliyahu_cost'] = to_num(current_data.get('preview_eliyahu_cost', 0)) + eliyahu_cost
        elif request_type == 'full':
            updates['total_validations'] = to_num(current_data.get('total_validations', 0)) + 1
            updates['validation_rows_processed'] = to_num(current_data.get('validation_rows_processed', 0)) + rows_processed
            updates['validation_revenue'] = to_num(current_data.get('validation_revenue', 0)) + charged_cost
        elif request_type == 'config':
            updates['total_configurations'] = to_num(current_data.get('total_configurations', 0)) + 1
            updates['config_generation_eliyahu_cost'] = to_num(current_data.get('config_generation_eliyahu_cost', 0)) + config_cost
        
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


def is_new_user(email: str) -> bool:
    """
    Check if a user is new (has no completed validation runs).

    Args:
        email: User's email address

    Returns:
        True if user has no completed validation runs, False otherwise
    """
    try:
        # Normalize email to lowercase
        email = email.lower().strip()

        # Query the validation runs table for any completed runs by this user
        table = dynamodb.Table(VALIDATION_RUNS_TABLE_NAME)

        # Use GSI to query by email (if available) or scan for the email
        # Since the runs table uses session_id as partition key, we need to scan
        response = table.scan(
            FilterExpression='contains(#email, :email) AND #status = :completed_status',
            ExpressionAttributeNames={
                '#email': 'email',
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':email': email,
                ':completed_status': 'completed'
            },
            Limit=1  # We only need to know if any exist
        )

        # If we found any completed runs, user is not new
        has_completed_runs = len(response.get('Items', [])) > 0
        return not has_completed_runs

    except Exception as e:
        logger.error(f"Error checking if user {email} is new: {e}")
        # Default to False (not new) on error to avoid showing demos inappropriately
        return False


# --- Account Balance and Transaction Management ---

def create_account_transactions_table():
    """Create the account transactions table."""
    schemas = DynamoDBSchemas()
    try:
        dynamodb_client.create_table(**schemas.get_account_transactions_schema())
        logger.info(f"Created {schemas.ACCOUNT_TRANSACTIONS_TABLE} table")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            logger.info(f"Table {schemas.ACCOUNT_TRANSACTIONS_TABLE} already exists")
            return True
        else:
            logger.error(f"Error creating account transactions table: {e}")
            return False


def create_domain_multipliers_table():
    """Create the domain multipliers table."""
    schemas = DynamoDBSchemas()
    try:
        dynamodb_client.create_table(**schemas.get_domain_multipliers_schema())
        logger.info(f"Created {schemas.DOMAIN_MULTIPLIERS_TABLE} table")
        
        # Initialize with global multiplier
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(schemas.DOMAIN_MULTIPLIERS_TABLE)
        table.put_item(Item={
            'domain': 'global',
            'multiplier': Decimal('5.0'),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'created_by': 'system',
            'notes': 'Default global multiplier'
        })
        logger.info("Initialized global multiplier to 5.0")
        
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            logger.info(f"Table {schemas.DOMAIN_MULTIPLIERS_TABLE} already exists")
            return True
        else:
            logger.error(f"Error creating domain multipliers table: {e}")
            return False


def initialize_user_account(email: str, initial_balance: Decimal = Decimal('0')) -> bool:
    """Initialize user account with balance fields."""
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.USER_TRACKING_TABLE)
        
        # Update existing user or create if doesn't exist
        current_time = datetime.now(timezone.utc).isoformat()
        
        # Check if user exists
        response = table.get_item(Key={'email': email})
        
        if 'Item' in response and 'account_balance' in response['Item']:
            # Account already initialized
            return True
        
        # Add account fields
        update_expr = "SET account_balance = :balance, balance_last_updated = :updated, account_created_at = :created"
        expr_values = {
            ':balance': initial_balance,
            ':updated': current_time,
            ':created': current_time
        }
        
        # If user doesn't exist, initialize basic fields too
        if 'Item' not in response:
            email_domain = email.split('@')[-1] if '@' in email else 'unknown'
            update_expr += ", email_domain = :domain, created_at = :created, last_access = :created"
            update_expr += ", total_previews = :zero, total_validations = :zero, total_configurations = :zero"
            expr_values.update({
                ':domain': email_domain,
                ':zero': 0,
                ':zero_decimal': Decimal('0')
            })
        
        table.update_item(
            Key={'email': email},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values
        )
        
        logger.info(f"Initialized account for {email} with balance {initial_balance}")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing user account: {e}")
        return False


def check_user_balance(email: str) -> Optional[Decimal]:
    """Check user's current account balance."""
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.USER_TRACKING_TABLE)
        response = table.get_item(Key={'email': email})
        
        if 'Item' not in response:
            return None
        
        # Return balance, defaulting to 0 if not set
        return response['Item'].get('account_balance', Decimal('0'))
        
    except Exception as e:
        logger.error(f"Error checking user balance: {e}")
        return None


def deduct_from_balance(email: str, amount: Decimal, session_id: str, description: str, 
                       raw_cost: Decimal = None, multiplier: Decimal = None) -> bool:
    """Deduct amount from user balance and record transaction."""
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        
        # Get current balance
        current_balance = check_user_balance(email)
        if current_balance is None:
            logger.error(f"User {email} not found")
            return False
        
        if current_balance < amount:
            logger.error(f"Insufficient balance for {email}: {current_balance} < {amount}")
            return False
        
        # Update balance
        new_balance = current_balance - amount
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.USER_TRACKING_TABLE)
        
        table.update_item(
            Key={'email': email},
            UpdateExpression="SET account_balance = :balance, balance_last_updated = :updated",
            ExpressionAttributeValues={
                ':balance': new_balance,
                ':updated': datetime.now(timezone.utc).isoformat()
            }
        )
        
        # Record transaction
        import uuid
        transaction_id = str(uuid.uuid4())
        record_account_transaction(
            email=email,
            transaction_id=transaction_id,
            transaction_type='validation',
            amount=-amount,  # Negative for deduction
            balance_before=current_balance,
            balance_after=new_balance,
            session_id=session_id,
            description=description,
            raw_cost=raw_cost,
            multiplier_applied=multiplier
        )
        
        logger.info(f"Deducted {amount} from {email}, new balance: {new_balance}")
        return True
        
    except Exception as e:
        logger.error(f"Error deducting from balance: {e}")
        return False


def add_to_balance(email: str, amount: Decimal, transaction_type: str, 
                   description: str, payment_id: str = None) -> bool:
    """Add amount to user balance and record transaction."""
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        
        # Initialize account if needed
        current_balance = check_user_balance(email)
        if current_balance is None:
            initialize_user_account(email)
            current_balance = Decimal('0')
        
        # Update balance
        new_balance = current_balance + amount
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.USER_TRACKING_TABLE)
        
        table.update_item(
            Key={'email': email},
            UpdateExpression="SET account_balance = :balance, balance_last_updated = :updated",
            ExpressionAttributeValues={
                ':balance': new_balance,
                ':updated': datetime.now(timezone.utc).isoformat()
            }
        )
        
        # Record transaction
        import uuid
        transaction_id = str(uuid.uuid4())
        record_account_transaction(
            email=email,
            transaction_id=transaction_id,
            transaction_type=transaction_type,
            amount=amount,  # Positive for addition
            balance_before=current_balance,
            balance_after=new_balance,
            description=description,
            payment_id=payment_id
        )
        
        logger.info(f"Added {amount} to {email}, new balance: {new_balance}")
        return True
        
    except Exception as e:
        logger.error(f"Error adding to balance: {e}")
        return False


# ========== STRENGTHENED DOMAIN MULTIPLIER SYSTEM ==========

# In-memory cache for domain multipliers to reduce DynamoDB hits
_domain_multiplier_cache = {}
_cache_last_updated = {}
_cache_ttl_seconds = 300  # 5 minute cache TTL

def validate_domain_format(domain: str) -> Dict[str, Any]:
    """
    Validate email domain format and return normalized domain.
    
    Args:
        domain: Domain to validate
        
    Returns:
        Dictionary with validation results and normalized domain
    """
    validation_result = {
        'is_valid': True,
        'normalized_domain': domain,
        'warnings': [],
        'errors': []
    }
    
    try:
        if not domain or not isinstance(domain, str):
            validation_result['errors'].append(f"Domain must be a non-empty string, got: {type(domain)}")
            validation_result['is_valid'] = False
            validation_result['normalized_domain'] = 'unknown'
            return validation_result
        
        # Normalize domain (lowercase, strip whitespace)
        normalized = domain.lower().strip()
        
        # Validate basic domain format
        if not normalized:
            validation_result['errors'].append("Domain cannot be empty after normalization")
            validation_result['is_valid'] = False
            validation_result['normalized_domain'] = 'unknown'
            return validation_result
        
        # Special case: 'global' is valid
        if normalized == 'global':
            validation_result['normalized_domain'] = normalized
            return validation_result
        
        # Basic domain validation
        import re
        domain_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9\.-]*[a-zA-Z0-9]$'
        if not re.match(domain_pattern, normalized):
            validation_result['warnings'].append(f"Domain '{normalized}' has unusual format")
        
        # Check for suspicious patterns
        if '..' in normalized:
            validation_result['errors'].append(f"Domain '{normalized}' contains consecutive dots")
            validation_result['is_valid'] = False
        
        if normalized.startswith('.') or normalized.endswith('.'):
            validation_result['errors'].append(f"Domain '{normalized}' cannot start or end with dot")
            validation_result['is_valid'] = False
        
        # Warn about very short or very long domains
        if len(normalized) < 3:
            validation_result['warnings'].append(f"Domain '{normalized}' is very short ({len(normalized)} chars)")
        elif len(normalized) > 253:  # RFC limit
            validation_result['errors'].append(f"Domain '{normalized}' exceeds 253 character limit")
            validation_result['is_valid'] = False
        
        validation_result['normalized_domain'] = normalized
        
    except Exception as e:
        validation_result['errors'].append(f"Error validating domain: {e}")
        validation_result['is_valid'] = False
        validation_result['normalized_domain'] = 'error'
    
    return validation_result

def validate_multiplier_value(multiplier: Any) -> Dict[str, Any]:
    """
    Validate domain multiplier value for business logic and security.
    
    Args:
        multiplier: Multiplier value to validate
        
    Returns:
        Dictionary with validation results and sanitized multiplier
    """
    validation_result = {
        'is_valid': True,
        'sanitized_multiplier': Decimal('5.0'),
        'warnings': [],
        'errors': []
    }
    
    try:
        # Convert to Decimal
        if isinstance(multiplier, str):
            multiplier_decimal = Decimal(multiplier)
        elif isinstance(multiplier, (int, float)):
            multiplier_decimal = Decimal(str(multiplier))
        elif isinstance(multiplier, Decimal):
            multiplier_decimal = multiplier
        else:
            validation_result['errors'].append(f"Invalid multiplier type: {type(multiplier)}")
            validation_result['is_valid'] = False
            return validation_result
        
        # Validate range
        if multiplier_decimal <= 0:
            validation_result['errors'].append(f"Multiplier must be positive, got: {multiplier_decimal}")
            validation_result['is_valid'] = False
            multiplier_decimal = Decimal('5.0')  # Safe fallback
        elif multiplier_decimal > 100:
            validation_result['errors'].append(f"Multiplier {multiplier_decimal} exceeds maximum of 100x")
            validation_result['is_valid'] = False
            multiplier_decimal = Decimal('100.0')  # Cap at 100x
        
        # Business logic warnings
        if multiplier_decimal < Decimal('0.1'):
            validation_result['warnings'].append(f"Very low multiplier {multiplier_decimal} - pricing will be heavily discounted")
        elif multiplier_decimal > 20:
            validation_result['warnings'].append(f"High multiplier {multiplier_decimal} - pricing will be significantly marked up")
        
        # Validate precision (max 2 decimal places for pricing)
        if multiplier_decimal.as_tuple().exponent < -2:
            validation_result['warnings'].append(f"Multiplier {multiplier_decimal} has more than 2 decimal places - will be rounded")
            multiplier_decimal = multiplier_decimal.quantize(Decimal('0.01'))
        
        validation_result['sanitized_multiplier'] = multiplier_decimal
        
    except Exception as e:
        validation_result['errors'].append(f"Error validating multiplier: {e}")
        validation_result['is_valid'] = False
        validation_result['sanitized_multiplier'] = Decimal('5.0')
    
    return validation_result

def get_domain_multiplier_with_audit(email_domain: str, session_id: str = None) -> Dict[str, Any]:
    """
    Get cost multiplier for a domain with comprehensive validation, caching, and audit trail.
    
    Args:
        email_domain: Email domain to get multiplier for
        session_id: Optional session ID for audit trail
        
    Returns:
        Dictionary with multiplier value, validation info, and audit data
    """
    start_time = time.time()
    audit_info = {
        'domain_requested': email_domain,
        'session_id': session_id,
        'lookup_timestamp': datetime.now(timezone.utc).isoformat(),
        'cache_hit': False,
        'fallback_used': False,
        'validation_warnings': [],
        'validation_errors': []
    }
    
    try:
        # Validate and normalize domain
        domain_validation = validate_domain_format(email_domain)
        normalized_domain = domain_validation['normalized_domain']
        audit_info['normalized_domain'] = normalized_domain
        audit_info['validation_warnings'].extend(domain_validation['warnings'])
        audit_info['validation_errors'].extend(domain_validation['errors'])
        
        if not domain_validation['is_valid']:
            logger.error(f"[DOMAIN_MULTIPLIER] Invalid domain format: {email_domain}")
            normalized_domain = 'unknown'
        
        # Check cache first
        current_time = time.time()
        cache_key = normalized_domain
        
        if (cache_key in _domain_multiplier_cache and 
            cache_key in _cache_last_updated and 
            current_time - _cache_last_updated[cache_key] < _cache_ttl_seconds):
            
            cached_result = _domain_multiplier_cache[cache_key]
            audit_info['cache_hit'] = True
            audit_info['lookup_duration_ms'] = round((time.time() - start_time) * 1000, 2)
            
            logger.debug(f"[DOMAIN_MULTIPLIER] Cache hit for domain {normalized_domain}: {cached_result['multiplier']}")
            
            return {
                'multiplier': cached_result['multiplier'],
                'source': f"cache_{cached_result['source']}",
                'audit_info': audit_info
            }
        
        # Fetch from DynamoDB with retries
        multiplier = None
        source = 'unknown'
        
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.DOMAIN_MULTIPLIERS_TABLE)
        
        # Try domain-specific multiplier first (with retries)
        for attempt in range(3):
            try:
                response = table.get_item(Key={'domain': normalized_domain})
                if 'Item' in response:
                    multiplier_validation = validate_multiplier_value(response['Item']['multiplier'])
                    multiplier = multiplier_validation['sanitized_multiplier']
                    source = f'domain_specific_{normalized_domain}'
                    audit_info['validation_warnings'].extend(multiplier_validation['warnings'])
                    audit_info['validation_errors'].extend(multiplier_validation['errors'])
                    
                    logger.info(f"[DOMAIN_MULTIPLIER] Found domain-specific multiplier for {normalized_domain}: {multiplier}")
                    break
                    
            except Exception as e:
                logger.warning(f"[DOMAIN_MULTIPLIER] Attempt {attempt + 1} failed for domain {normalized_domain}: {e}")
                if attempt < 2:
                    time.sleep(0.1 * (attempt + 1))  # Brief retry delay
                continue
        
        # Fallback to global multiplier if domain-specific not found
        if multiplier is None:
            for attempt in range(3):
                try:
                    response = table.get_item(Key={'domain': 'global'})
                    if 'Item' in response:
                        multiplier_validation = validate_multiplier_value(response['Item']['multiplier'])
                        multiplier = multiplier_validation['sanitized_multiplier']
                        source = 'global_fallback'
                        audit_info['fallback_used'] = True
                        audit_info['validation_warnings'].extend(multiplier_validation['warnings'])
                        audit_info['validation_errors'].extend(multiplier_validation['errors'])
                        
                        logger.info(f"[DOMAIN_MULTIPLIER] Using global fallback multiplier for {normalized_domain}: {multiplier}")
                        break
                        
                except Exception as e:
                    logger.warning(f"[DOMAIN_MULTIPLIER] Global fallback attempt {attempt + 1} failed: {e}")
                    if attempt < 2:
                        time.sleep(0.1 * (attempt + 1))
                    continue
        
        # Final default fallback
        if multiplier is None:
            multiplier = Decimal('5.0')
            source = 'hardcoded_default'
            audit_info['fallback_used'] = True
            audit_info['validation_warnings'].append("Using hardcoded default multiplier 5.0")
            logger.warning(f"[DOMAIN_MULTIPLIER] Using hardcoded default for {normalized_domain}: {multiplier}")
        
        # Cache the result
        _domain_multiplier_cache[cache_key] = {
            'multiplier': multiplier,
            'source': source,
            'cached_at': current_time
        }
        _cache_last_updated[cache_key] = current_time
        
        audit_info['lookup_duration_ms'] = round((time.time() - start_time) * 1000, 2)
        
        # Log audit info for high multipliers or errors
        if multiplier > 10 or audit_info['validation_errors']:
            logger.warning(f"[DOMAIN_MULTIPLIER_AUDIT] High multiplier or errors for {normalized_domain}: "
                          f"multiplier={multiplier}, errors={audit_info['validation_errors']}")
        
        return {
            'multiplier': multiplier,
            'source': source,
            'audit_info': audit_info
        }
        
    except Exception as e:
        audit_info['lookup_duration_ms'] = round((time.time() - start_time) * 1000, 2)
        audit_info['validation_errors'].append(f"Critical error in domain multiplier lookup: {e}")
        
        logger.error(f"[DOMAIN_MULTIPLIER] Critical error for {email_domain}: {e}")
        
        return {
            'multiplier': Decimal('5.0'),
            'source': 'emergency_fallback',
            'audit_info': audit_info
        }

def get_domain_multiplier(email_domain: str) -> Decimal:
    """
    Get cost multiplier for a domain - backward compatible interface.
    This is a simplified wrapper around get_domain_multiplier_with_audit for existing code.
    """
    result = get_domain_multiplier_with_audit(email_domain)
    return result['multiplier']


def set_domain_multiplier_with_audit(domain: str, multiplier: Any, admin_email: str, 
                                   notes: str = '', session_id: str = None) -> Dict[str, Any]:
    """
    Set cost multiplier for a domain with comprehensive validation and audit trail.
    
    Args:
        domain: Domain to set multiplier for
        multiplier: Multiplier value to set
        admin_email: Email of admin making the change
        notes: Optional notes about the change
        session_id: Optional session ID for audit trail
        
    Returns:
        Dictionary with operation results and audit information
    """
    start_time = time.time()
    operation_result = {
        'success': False,
        'domain': domain,
        'multiplier_set': None,
        'audit_info': {
            'operation': 'set_domain_multiplier',
            'admin_email': admin_email,
            'session_id': session_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'notes': notes,
            'validation_warnings': [],
            'validation_errors': []
        }
    }
    
    try:
        # Validate domain
        domain_validation = validate_domain_format(domain)
        normalized_domain = domain_validation['normalized_domain']
        operation_result['audit_info']['normalized_domain'] = normalized_domain
        operation_result['audit_info']['validation_warnings'].extend(domain_validation['warnings'])
        operation_result['audit_info']['validation_errors'].extend(domain_validation['errors'])
        
        if not domain_validation['is_valid']:
            operation_result['audit_info']['validation_errors'].append("Domain validation failed - cannot set multiplier")
            logger.error(f"[SET_DOMAIN_MULTIPLIER] Cannot set multiplier for invalid domain: {domain}")
            return operation_result
        
        # Validate multiplier
        multiplier_validation = validate_multiplier_value(multiplier)
        sanitized_multiplier = multiplier_validation['sanitized_multiplier']
        operation_result['audit_info']['validation_warnings'].extend(multiplier_validation['warnings'])
        operation_result['audit_info']['validation_errors'].extend(multiplier_validation['errors'])
        
        if not multiplier_validation['is_valid']:
            operation_result['audit_info']['validation_errors'].append("Multiplier validation failed - using sanitized value")
        
        # Check if this is a significant change (audit high-impact changes)
        current_multiplier_info = get_domain_multiplier_with_audit(normalized_domain, session_id)
        current_multiplier = current_multiplier_info['multiplier']
        
        change_ratio = float(sanitized_multiplier / current_multiplier) if current_multiplier > 0 else float('inf')
        if change_ratio > 2.0 or change_ratio < 0.5:
            operation_result['audit_info']['validation_warnings'].append(
                f"Significant multiplier change: {current_multiplier} -> {sanitized_multiplier} ({change_ratio:.1f}x change)"
            )
        
        # Validate admin email
        if not admin_email or '@' not in admin_email:
            operation_result['audit_info']['validation_errors'].append(f"Invalid admin email: {admin_email}")
            logger.error(f"[SET_DOMAIN_MULTIPLIER] Invalid admin email for domain {normalized_domain}: {admin_email}")
            return operation_result
        
        # Get existing item for change tracking
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.DOMAIN_MULTIPLIERS_TABLE)
        
        existing_item = None
        try:
            response = table.get_item(Key={'domain': normalized_domain})
            if 'Item' in response:
                existing_item = response['Item']
        except Exception as e:
            logger.warning(f"[SET_DOMAIN_MULTIPLIER] Could not fetch existing item for {normalized_domain}: {e}")
        
        current_time = datetime.now(timezone.utc).isoformat()
        
        # Prepare new item with full audit trail
        new_item = {
            'domain': normalized_domain,
            'multiplier': sanitized_multiplier,
            'updated_at': current_time,
            'updated_by': admin_email,
            'notes': notes,
            'change_history': []
        }
        
        # Preserve creation info if updating existing item
        if existing_item:
            new_item['created_at'] = existing_item.get('created_at', current_time)
            new_item['created_by'] = existing_item.get('created_by', admin_email)
            
            # Add to change history
            change_record = {
                'timestamp': current_time,
                'admin_email': admin_email,
                'old_multiplier': str(existing_item.get('multiplier', '0.0')),
                'new_multiplier': str(sanitized_multiplier),
                'notes': notes,
                'session_id': session_id
            }
            
            # Preserve existing change history (limit to last 10 changes)
            existing_history = existing_item.get('change_history', [])
            if isinstance(existing_history, list):
                new_item['change_history'] = existing_history[-9:] + [change_record]  # Keep last 9 + new = 10
            else:
                new_item['change_history'] = [change_record]
        else:
            new_item['created_at'] = current_time
            new_item['created_by'] = admin_email
            new_item['change_history'] = [{
                'timestamp': current_time,
                'admin_email': admin_email,
                'old_multiplier': 'none',
                'new_multiplier': str(sanitized_multiplier),
                'notes': f"Initial creation: {notes}",
                'session_id': session_id
            }]
        
        # Add validation metadata
        new_item['validation_info'] = {
            'validation_timestamp': current_time,
            'warnings_count': len(operation_result['audit_info']['validation_warnings']),
            'errors_count': len(operation_result['audit_info']['validation_errors']),
            'sanitized': not multiplier_validation['is_valid']
        }
        
        # Write to DynamoDB with conditional check for concurrent modifications
        try:
            # Use condition to prevent concurrent modifications
            if existing_item:
                condition_expression = 'updated_at = :expected_updated_at'
                expression_attribute_values = {':expected_updated_at': existing_item.get('updated_at')}
            else:
                condition_expression = 'attribute_not_exists(domain)'
                expression_attribute_values = {}
            
            table.put_item(
                Item=new_item,
                ConditionExpression=condition_expression,
                **({'ExpressionAttributeValues': expression_attribute_values} if expression_attribute_values else {})
            )
            
            # Clear cache for this domain
            cache_key = normalized_domain
            if cache_key in _domain_multiplier_cache:
                del _domain_multiplier_cache[cache_key]
            if cache_key in _cache_last_updated:
                del _cache_last_updated[cache_key]
            
            operation_result['success'] = True
            operation_result['multiplier_set'] = sanitized_multiplier
            operation_result['audit_info']['operation_duration_ms'] = round((time.time() - start_time) * 1000, 2)
            
            logger.info(f"[SET_DOMAIN_MULTIPLIER] Successfully set multiplier for {normalized_domain}: "
                       f"{sanitized_multiplier} (admin: {admin_email})")
            
            # Log significant changes for audit
            if operation_result['audit_info']['validation_warnings']:
                logger.warning(f"[SET_DOMAIN_MULTIPLIER_AUDIT] Warnings for {normalized_domain}: "
                              f"{operation_result['audit_info']['validation_warnings']}")
            
            return operation_result
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                operation_result['audit_info']['validation_errors'].append("Concurrent modification detected - please retry")
                logger.error(f"[SET_DOMAIN_MULTIPLIER] Concurrent modification for {normalized_domain}")
            else:
                operation_result['audit_info']['validation_errors'].append(f"DynamoDB error: {e}")
                logger.error(f"[SET_DOMAIN_MULTIPLIER] DynamoDB error for {normalized_domain}: {e}")
            return operation_result
            
    except Exception as e:
        operation_result['audit_info']['operation_duration_ms'] = round((time.time() - start_time) * 1000, 2)
        operation_result['audit_info']['validation_errors'].append(f"Critical error: {e}")
        logger.error(f"[SET_DOMAIN_MULTIPLIER] Critical error for {domain}: {e}")
        return operation_result

def set_domain_multiplier(domain: str, multiplier: Decimal, admin_email: str, notes: str = '') -> bool:
    """
    Set cost multiplier for a domain - backward compatible interface.
    This is a simplified wrapper around set_domain_multiplier_with_audit for existing code.
    """
    result = set_domain_multiplier_with_audit(domain, multiplier, admin_email, notes)
    return result['success']


def record_account_transaction(email: str, transaction_id: str, transaction_type: str,
                              amount: Decimal, balance_before: Decimal, balance_after: Decimal,
                              description: str, session_id: str = None, multiplier_applied: Decimal = None,
                              raw_cost: Decimal = None, payment_method: str = None, 
                              payment_id: str = None, receipt_url: str = None) -> bool:
    """Record a transaction in the account transactions table."""
    try:
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.ACCOUNT_TRANSACTIONS_TABLE)
        
        item = {
            'email': email,
            'transaction_id': transaction_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'transaction_type': transaction_type,
            'amount': amount,
            'balance_before': balance_before,
            'balance_after': balance_after,
            'description': description
        }
        
        # Add optional fields
        if session_id:
            item['session_id'] = session_id
        if multiplier_applied is not None:
            item['multiplier_applied'] = multiplier_applied
        if raw_cost is not None:
            item['raw_cost'] = raw_cost
        if payment_method:
            item['payment_method'] = payment_method
        if payment_id:
            item['payment_id'] = payment_id
        if receipt_url:
            item['receipt_url'] = receipt_url
        
        table.put_item(Item=item)
        return True
        
    except Exception as e:
        logger.error(f"Error recording account transaction: {e}")
        return False


def get_user_transactions(email: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get transaction history for a user."""
    try:
        # Normalize email to lowercase
        email = email.lower().strip()
        
        table = boto3.resource('dynamodb', region_name='us-east-1').Table(DynamoDBSchemas.ACCOUNT_TRANSACTIONS_TABLE)
        
        # Query using the TimestampIndex to get transactions in chronological order
        response = table.query(
            IndexName='TimestampIndex',
            KeyConditionExpression='email = :email',
            ExpressionAttributeValues={':email': email},
            ScanIndexForward=False,  # Most recent first
            Limit=limit
        )
        
        items = response.get('Items', [])
        
        # Convert Decimals to floats for JSON compatibility
        for item in items:
            for key, value in item.items():
                if isinstance(value, Decimal):
                    item[key] = float(value)
        
        return items
        
    except Exception as e:
        logger.error(f"Error getting user transactions: {e}")
        return []


def track_preview_cost(session_id: str, email: str, raw_cost: Decimal, 
                      multiplier: Decimal, tokens_used: int) -> bool:
    """Track preview cost without charging (preview is free)."""
    try:
        # Record in call tracking with raw cost info
        updates = {
            'preview_raw_cost_usd': raw_cost,
            'preview_cost_multiplier': multiplier,
            'preview_display_cost_usd': raw_cost * multiplier,  # What would be charged if not free
            'preview_tokens_used': tokens_used,
            'preview_completed': True
        }
        
        return update_processing_metrics(session_id, updates)
        
    except Exception as e:
        logger.error(f"Error tracking preview cost: {e}")
        return False


def track_abandoned_session(session_id: str) -> bool:
    """Mark a session as abandoned (preview without full validation)."""
    try:
        updates = {
            'session_abandoned': True,
            'abandoned_at': datetime.now(timezone.utc).isoformat()
        }
        
        return update_processing_metrics(session_id, updates)
        
    except Exception as e:
        logger.error(f"Error tracking abandoned session: {e}")
        return False


# --- Validation Run Tracking ---

VALIDATION_RUNS_TABLE_NAME = "perplexity-validator-runs"

def create_validation_runs_table():
    """Creates the DynamoDB table for tracking validation runs with proper schema and indexes."""
    try:
        # Use the client for operations like waiting
        dynamodb_client = boto3.client('dynamodb')
        
        # Get the full schema definition
        schemas = DynamoDBSchemas()
        table_schema = schemas.get_validation_runs_schema()
        
        # Create table using the complete schema
        dynamodb_client.create_table(**table_schema)
        
        waiter = dynamodb_client.get_waiter('table_exists')
        waiter.wait(TableName=VALIDATION_RUNS_TABLE_NAME)
        logger.info(f"Table {VALIDATION_RUNS_TABLE_NAME} created successfully with indexes.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            logger.info(f"Table {VALIDATION_RUNS_TABLE_NAME} already exists.")
        else:
            raise

def create_run_record(session_id: str, email: str, total_rows: int, batch_size: int = None, run_type: str = None):
    """Creates an initial record for a new validation run with composite primary key."""
    from datetime import datetime
    import time
    
    # Create composite sort key: run_type + timestamp
    current_time = datetime.now(timezone.utc)
    timestamp = current_time.isoformat()
    timestamp_ms = int(time.time() * 1000000)  # microseconds for uniqueness
    
    run_type_clean = (run_type or "Unknown").replace(" ", "")
    run_key = f"{run_type_clean}#{timestamp_ms}"
    
    try:
        table = dynamodb.Table(VALIDATION_RUNS_TABLE_NAME)
        item = {
            'session_id': session_id,
            'run_key': run_key,
            'email': email,
            'status': 'PENDING',
            'total_rows': total_rows,
            'processed_rows': 0,
            'start_time': timestamp,
            'last_update': timestamp
        }
        if batch_size is not None:
            item['batch_size'] = batch_size
        if run_type is not None:
            item['run_type'] = run_type
        
        table.put_item(Item=item)
        
        # Return the run_key for subsequent update calls
        return run_key
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.warning(f"Table {VALIDATION_RUNS_TABLE_NAME} not found. Attempting to create it now.")
            create_validation_runs_table()
            # Retry the operation once after creating the table
            item = {
                'session_id': session_id,
                'run_key': run_key,
                'email': email,
                'status': 'PENDING',
                'total_rows': total_rows,
                'processed_rows': 0,
                'start_time': timestamp,
                'last_update': timestamp
            }
            if batch_size is not None:
                item['batch_size'] = batch_size
            if run_type is not None:
                item['run_type'] = run_type
            
            table.put_item(Item=item)
            return run_key
        else:
            raise

def update_run_status(session_id: str, run_key: str, status: str, run_type: str = None, processed_rows: int = None, error_message: str = None, results_s3_key: str = None, verbose_status: str = None, percent_complete: int = None, email_status: str = None, preview_data: dict = None, batch_size: int = None, account_current_balance: float = None, account_sufficient_balance: str = None, account_credits_needed: str = None, account_domain_multiplier: float = None, models: str = None, input_table_name: str = None, configuration_id: str = None, total_rows: int = None, eliyahu_cost: float = None, quoted_validation_cost: float = None, estimated_validation_eliyahu_cost: float = None, time_per_row_seconds: float = None, estimated_validation_time_minutes: float = None, run_time_s: float = None, provider_metrics: dict = None, qc_metrics: dict = None, total_provider_calls: int = None, **kwargs):
    """Updates the status and progress of a validation run using composite primary key."""
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
    if batch_size is not None:
        update_expression += ", batch_size = :bs"
        expression_attribute_values[':bs'] = batch_size
    if account_current_balance is not None:
        update_expression += ", account_current_balance = :acb"
        expression_attribute_values[':acb'] = convert_floats_to_decimal(account_current_balance)
    if account_sufficient_balance is not None:
        update_expression += ", account_sufficient_balance = :asb"
        expression_attribute_values[':asb'] = account_sufficient_balance
    if account_credits_needed is not None:
        update_expression += ", account_credits_needed = :acn"
        expression_attribute_values[':acn'] = account_credits_needed
    if account_domain_multiplier is not None:
        update_expression += ", account_domain_multiplier = :adm"
        expression_attribute_values[':adm'] = convert_floats_to_decimal(account_domain_multiplier)
    if models is not None:
        update_expression += ", models = :models"
        expression_attribute_values[':models'] = models
    if input_table_name is not None:
        update_expression += ", input_table_name = :itn"
        expression_attribute_values[':itn'] = input_table_name
    if configuration_id is not None:
        update_expression += ", configuration_id = :cid"
        expression_attribute_values[':cid'] = configuration_id
    if total_rows is not None:
        update_expression += ", total_rows = :tr"
        expression_attribute_values[':tr'] = total_rows
    if run_type is not None:
        update_expression += ", run_type = :rt"
        expression_attribute_values[':rt'] = run_type
    # ========== HARDENED THREE-TIER COST FIELD HANDLING ==========
    # Handle cost fields with validation and atomicity
    cost_fields_provided = any([
        eliyahu_cost is not None,
        quoted_validation_cost is not None,
        estimated_validation_eliyahu_cost is not None
    ])
    
    if cost_fields_provided:
        # Determine operation type for validation
        operation_type = "validation"
        if run_type:
            if "config" in run_type.lower():
                operation_type = "config_generation"
            elif "preview" in run_type.lower():
                operation_type = "preview"
        
        # Validate cost fields
        validation_result = validate_cost_fields(
            eliyahu_cost=eliyahu_cost,
            quoted_validation_cost=quoted_validation_cost,
            estimated_validation_eliyahu_cost=estimated_validation_eliyahu_cost,
            operation_type=operation_type
        )
        
        # Use atomic transaction for cost updates if validation is critical
        if not validation_result['is_valid']:
            logger.error(f"[COST_UPDATE] Cost validation failed for session {session_id}: {validation_result['errors']}")
        
        # Apply sanitized values
        sanitized_costs = validation_result['sanitized_values']
        
        if 'eliyahu_cost' in sanitized_costs:
            update_expression += ", eliyahu_cost = :ec"
            expression_attribute_values[':ec'] = sanitized_costs['eliyahu_cost']
        if 'quoted_validation_cost' in sanitized_costs:
            update_expression += ", quoted_validation_cost = :qvc"
            expression_attribute_values[':qvc'] = sanitized_costs['quoted_validation_cost']
        if 'estimated_validation_eliyahu_cost' in sanitized_costs:
            update_expression += ", estimated_validation_eliyahu_cost = :evec"
            expression_attribute_values[':evec'] = sanitized_costs['estimated_validation_eliyahu_cost']
        
        # Add cost validation metadata
        update_expression += ", cost_validation_info = :cost_validation_info"
        expression_attribute_values[':cost_validation_info'] = convert_floats_to_decimal({
            'validation_timestamp': validation_result['audit_info']['validation_timestamp'],
            'is_valid': validation_result['is_valid'],
            'warnings_count': len(validation_result['warnings']),
            'errors_count': len(validation_result['errors']),
            'operation_type': operation_type
        })
        
        # Log audit information
        if validation_result['warnings']:
            logger.warning(f"[COST_AUDIT] Session {session_id} cost warnings: {validation_result['warnings']}")
        if validation_result['errors']:
            logger.error(f"[COST_AUDIT] Session {session_id} cost errors: {validation_result['errors']}")
    else:
        # No cost fields provided - legacy behavior
        if eliyahu_cost is not None:
            update_expression += ", eliyahu_cost = :ec"
            expression_attribute_values[':ec'] = convert_floats_to_decimal(eliyahu_cost)
        if quoted_validation_cost is not None:
            update_expression += ", quoted_validation_cost = :qvc"
            expression_attribute_values[':qvc'] = convert_floats_to_decimal(quoted_validation_cost)
        if estimated_validation_eliyahu_cost is not None:
            update_expression += ", estimated_validation_eliyahu_cost = :evec"
            expression_attribute_values[':evec'] = convert_floats_to_decimal(estimated_validation_eliyahu_cost)
    
    # ========== ENHANCED PROVIDER-SPECIFIC METRICS ==========
    if provider_metrics is not None and isinstance(provider_metrics, dict):
        try:
            # Validate and sanitize provider metrics before storage
            sanitized_provider_metrics = {}
            
            # Extract provider-specific costs, tokens, and timing data
            for provider, metrics in provider_metrics.items():
                if isinstance(metrics, dict):
                    sanitized_metrics = {}
                    
                    # Cost metrics by provider
                    for cost_field in ['cost_actual', 'cost_estimated', 'cache_savings_cost']:
                        if cost_field in metrics and isinstance(metrics[cost_field], (int, float)):
                            sanitized_metrics[cost_field] = convert_floats_to_decimal(metrics[cost_field])
                    
                    # Token and call metrics by provider
                    for count_field in ['calls', 'tokens', 'cache_hit_tokens']:
                        if count_field in metrics and isinstance(metrics[count_field], int):
                            sanitized_metrics[count_field] = metrics[count_field]
                    
                    # Timing metrics by provider
                    for time_field in ['processing_time', 'cache_savings_time']:
                        if time_field in metrics and isinstance(metrics[time_field], (int, float)):
                            sanitized_metrics[time_field] = convert_floats_to_decimal(metrics[time_field])
                    
                    # Per-row metrics by provider
                    for per_row_field in ['cost_per_row_actual', 'cost_per_row_estimated', 'time_per_row_actual', 'time_per_row_estimated']:
                        if per_row_field in metrics and isinstance(metrics[per_row_field], (int, float)):
                            sanitized_metrics[per_row_field] = convert_floats_to_decimal(metrics[per_row_field])
                    
                    # Cache efficiency metrics
                    for efficiency_field in ['cache_efficiency_percent', 'cache_hit_rate_percent']:
                        if efficiency_field in metrics and isinstance(metrics[efficiency_field], (int, float)):
                            sanitized_metrics[efficiency_field] = convert_floats_to_decimal(metrics[efficiency_field])
                    
                    if sanitized_metrics:  # Only add if we have valid metrics
                        sanitized_provider_metrics[provider] = sanitized_metrics
            
            if sanitized_provider_metrics:
                update_expression += ", provider_metrics = :pm"
                expression_attribute_values[':pm'] = sanitized_provider_metrics
                
                # Also store aggregated totals for easy querying
                total_cost_actual = sum(metrics.get('cost_actual', 0) for metrics in sanitized_provider_metrics.values()
                                       if not metrics.get('is_metadata_only', False))
                total_cost_estimated = sum(metrics.get('cost_estimated', 0) for metrics in sanitized_provider_metrics.values()
                                          if not metrics.get('is_metadata_only', False))
                total_calls = sum(metrics.get('calls', 0) for metrics in sanitized_provider_metrics.values()
                                 if not metrics.get('is_metadata_only', False))
                total_tokens = sum(metrics.get('tokens', 0) for metrics in sanitized_provider_metrics.values()
                                  if not metrics.get('is_metadata_only', False))
                
                update_expression += ", total_provider_cost_actual = :tpca, total_provider_cost_estimated = :tpce"
                update_expression += ", total_provider_calls = :tpc, total_provider_tokens = :tpt"
                expression_attribute_values[':tpca'] = total_cost_actual
                expression_attribute_values[':tpce'] = total_cost_estimated
                # Use the total_provider_calls parameter if provided, otherwise use calculated value
                expression_attribute_values[':tpc'] = total_provider_calls if total_provider_calls is not None else total_calls
                expression_attribute_values[':tpt'] = total_tokens
                
                # Calculate overall cache efficiency
                if total_cost_estimated > 0:
                    cache_efficiency = ((total_cost_estimated - total_cost_actual) / total_cost_estimated) * 100
                    update_expression += ", overall_cache_efficiency_percent = :oce"
                    expression_attribute_values[':oce'] = convert_floats_to_decimal(cache_efficiency)
                
                logger.info(f"[PROVIDER_METRICS] Session {session_id}: {len(sanitized_provider_metrics)} providers, "
                           f"Total cost: ${float(total_cost_actual):.6f} (actual) / ${float(total_cost_estimated):.6f} (estimated), "
                           f"Total calls: {total_calls}, Total tokens: {total_tokens}")
        
        except Exception as e:
            logger.error(f"[PROVIDER_METRICS] Failed to process provider metrics for session {session_id}: {e}")
            # Continue execution - provider metrics are supplemental, not critical
    
    if time_per_row_seconds is not None:
        update_expression += ", time_per_row_seconds = :tprs"
        expression_attribute_values[':tprs'] = convert_floats_to_decimal(time_per_row_seconds)
    if estimated_validation_time_minutes is not None:
        converted_value = convert_floats_to_decimal(estimated_validation_time_minutes)
        logger.info(f"[DB_UPDATE_DEBUG] Setting estimated_validation_time_minutes = {estimated_validation_time_minutes} (converted to {converted_value})")
        update_expression += ", estimated_validation_time_minutes = :evtm"
        expression_attribute_values[':evtm'] = converted_value
    if run_time_s is not None:
        update_expression += ", run_time_s = :rts"
        expression_attribute_values[':rts'] = convert_floats_to_decimal(run_time_s)
    # Add qc_metrics as a separate field if provided
    if qc_metrics is not None:
        logger.info(f"[DB_UPDATE_DEBUG] Setting qc_metrics = {qc_metrics}")
        update_expression += ", qc_metrics = :qcm"
        expression_attribute_values[':qcm'] = convert_floats_to_decimal(qc_metrics)
    # Handle total_provider_calls override if not handled by provider_metrics
    if total_provider_calls is not None and provider_metrics is None:
        update_expression += ", total_provider_calls = :tpc_override"
        expression_attribute_values[':tpc_override'] = total_provider_calls
    if status in ['COMPLETED', 'FAILED']:
        update_expression += ", end_time = :et"
        expression_attribute_values[':et'] = now
        
        # Calculate and store actual processing time
        try:
            response = table.get_item(Key={'session_id': session_id, 'run_key': run_key})
            if 'Item' in response:
                item = response['Item']
                start_time_str = item.get('start_time')
                if start_time_str and processed_rows:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(now.replace('Z', '+00:00'))
                    actual_duration_seconds = (end_time - start_time).total_seconds()
                    
                    # Calculate per-row and per-batch timing metrics
                    time_per_row = actual_duration_seconds / processed_rows if processed_rows > 0 else 0
                    actual_batch_size = batch_size or item.get('batch_size', 10)  # fallback to default if none
                    
                    # For previews, calculate time_per_batch based on actual rows processed
                    # For full validations, use configured batch size for projection
                    run_type = item.get('run_type', '')
                    if run_type == 'Preview':
                        # For previews, time per batch should reflect the actual batch that was processed
                        time_per_batch = actual_duration_seconds  # Total time = time for this one batch
                        logger.info(f"Preview batch timing: {actual_duration_seconds:.3f}s for {processed_rows} rows")
                    else:
                        # For full validations, calculate theoretical time per batch
                        time_per_batch = time_per_row * actual_batch_size
                    
                    # Store actual timing metrics and replace estimated values with actual ones
                    update_expression += ", actual_processing_time_seconds = :apt"
                    # Only set time_per_row_seconds if it wasn't already set by parameter
                    if time_per_row_seconds is None:
                        update_expression += ", time_per_row_seconds = :tprs_calc"
                        expression_attribute_values[':tprs_calc'] = convert_floats_to_decimal(time_per_row)
                    update_expression += ", actual_time_per_batch_seconds = :atpb"
                    # Only set run_time_s if it wasn't already set by parameter
                    if run_time_s is None:
                        update_expression += ", run_time_s = :rts_calc"
                        expression_attribute_values[':rts_calc'] = convert_floats_to_decimal(actual_duration_seconds)
                    # Only set estimated_validation_time_minutes if it wasn't already set by parameter
                    if estimated_validation_time_minutes is None:
                        update_expression += ", estimated_validation_time_minutes = :evtm_calc"
                        expression_attribute_values[':evtm_calc'] = convert_floats_to_decimal(actual_duration_seconds / 60)
                    
                    expression_attribute_values[':apt'] = convert_floats_to_decimal(actual_duration_seconds)
                    expression_attribute_values[':atpb'] = convert_floats_to_decimal(time_per_batch)
                    
                    logger.info(f"Calculated actual timing for {session_id}: {actual_duration_seconds:.2f}s total, {time_per_row:.2f}s/row, {time_per_batch:.2f}s/batch")
        except Exception as e:
            logger.warning(f"Could not calculate actual processing time for {session_id}: {e}")

    try:
        logger.info(f"[DB_FINAL_UPDATE] About to update DynamoDB with:")
        logger.info(f"[DB_FINAL_UPDATE]   UpdateExpression: {update_expression}")
        if ':evtm' in expression_attribute_values:
            logger.info(f"[DB_FINAL_UPDATE]   estimated_validation_time_minutes (:evtm) = {expression_attribute_values[':evtm']}")
        if ':evtm_calc' in expression_attribute_values:
            logger.info(f"[DB_FINAL_UPDATE]   estimated_validation_time_minutes calculated (:evtm_calc) = {expression_attribute_values[':evtm_calc']}")

        table.update_item(
            Key={'session_id': session_id, 'run_key': run_key},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ExpressionAttributeNames=expression_attribute_names
        )
        logger.info(f"Successfully updated run status for session {session_id}, run_key {run_key}, status: {status}")
        if estimated_validation_time_minutes is not None or qc_metrics is not None or total_provider_calls is not None:
            logger.info(f"[DB_UPDATE_DEBUG] Updated fields - time_minutes: {estimated_validation_time_minutes}, qc_metrics: {qc_metrics is not None}, total_calls: {total_provider_calls}")
    except Exception as e:
        logger.error(f"DynamoDB UPDATE FAILED for session {session_id}, run_key {run_key}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        logger.error(f"Update expression: {update_expression}")
        logger.error(f"Expression values: {expression_attribute_values}")
        logger.error(f"Expression names: {expression_attribute_names}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise  # Re-raise the exception so calling code knows it failed

def get_run_status(session_id: str, run_key: str) -> Optional[Dict]:
    """Retrieves the status of a specific validation run."""
    table = dynamodb.Table(VALIDATION_RUNS_TABLE_NAME)
    try:
        response = table.get_item(Key={'session_id': session_id, 'run_key': run_key})
        return response.get('Item')
    except ClientError as e:
        logger.error(f"Error getting run status for {session_id}/{run_key}: {e}")
        return None

def find_run_key_by_type(session_id: str, run_type: str) -> Optional[str]:
    """Find run_key for a session_id by run_type (e.g., 'Preview' or 'Validation')."""
    table = dynamodb.Table(VALIDATION_RUNS_TABLE_NAME)
    try:
        from boto3.dynamodb.conditions import Key
        response = table.query(
            KeyConditionExpression=Key('session_id').eq(session_id),
            FilterExpression='begins_with(run_key, :run_type)',
            ExpressionAttributeValues={':run_type': f'{run_type}#'},
            ScanIndexForward=False,  # Get most recent first
            Limit=1
        )
        items = response.get('Items', [])
        if items:
            run_key = items[0].get('run_key')
            logger.info(f"Found run_key for session {session_id} type {run_type}: {run_key}")
            return run_key
        return None
    except ClientError as e:
        logger.error(f"Error finding run_key by type for {session_id}/{run_type}: {e}")
        return None

def find_existing_run_key(session_id: str) -> Optional[str]:
    """Find existing run_key for a session_id by scanning the runs table."""
    table = dynamodb.Table(VALIDATION_RUNS_TABLE_NAME)
    try:
        # Use query with session_id as partition key to find any existing runs  
        from boto3.dynamodb.conditions import Key
        response = table.query(
            KeyConditionExpression=Key('session_id').eq(session_id),
            Limit=1  # We only need one existing run
        )
        items = response.get('Items', [])
        if items:
            existing_run = items[0]
            run_key = existing_run.get('run_key')
            logger.info(f"Found existing run_key for session {session_id}: {run_key}")
            return run_key
        else:
            logger.info(f"No existing run found for session {session_id}")
            return None
    except Exception as e:
        logger.error(f"Error finding existing run_key for {session_id}: {e}")
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