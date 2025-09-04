#!/usr/bin/env python3
"""
Model Configuration DynamoDB Table Management

This module manages model configurations (batch sizing + pricing) in DynamoDB,
replacing CSV files with a centralized, auditable configuration system.
"""

import boto3
import csv
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# Table name
MODEL_CONFIG_TABLE = "perplexity-validator-model-config"


class ModelConfigTable:
    """Manages model configurations in DynamoDB."""
    
    def __init__(self, table_name: str = MODEL_CONFIG_TABLE):
        """
        Initialize the model config table manager.
        
        Args:
            table_name: Name of the DynamoDB table
        """
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
        
    def load_config_from_csv(self, csv_file_path: str) -> int:
        """
        Load model configurations from CSV into DynamoDB.
        
        Args:
            csv_file_path: Path to the unified model config CSV file
            
        Returns:
            Number of configurations loaded
        """
        loaded_count = 0
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                # Skip comment lines and empty lines
                rows = [row for row in reader if not row.get('model_pattern', '').startswith('#')]
                
                for row in rows:
                    if not row.get('model_pattern'):
                        continue
                        
                    try:
                        config_id = str(uuid.uuid4())
                        timestamp = datetime.now(timezone.utc).isoformat()
                        
                        item = {
                            'config_id': config_id,
                            'model_pattern': row['model_pattern'].strip(),
                            'api_provider': row.get('api_provider', 'unknown').strip(),
                            'priority': int(row['priority']),
                            'enabled': row['enabled'].lower() in ('true', '1', 'yes'),
                            'last_updated': timestamp,
                            'created_at': timestamp,
                            
                            # Batch sizing configuration
                            'min_batch_size': int(row['min_batch_size']),
                            'max_batch_size': int(row['max_batch_size']),
                            'initial_batch_size': int(row['initial_batch_size']),
                            'weight': Decimal(str(float(row['weight']))),
                            'rate_limit_factor': Decimal(str(float(row['rate_limit_factor']))),
                            'success_threshold': int(row['success_threshold']),
                            'failure_threshold': int(row['failure_threshold']),
                            
                            # Pricing configuration
                            'input_cost_per_million_tokens': Decimal(str(float(row['input_cost_per_million_tokens']))),
                            'output_cost_per_million_tokens': Decimal(str(float(row['output_cost_per_million_tokens']))),
                            
                            'notes': row.get('notes', '').strip(),
                            
                            # TTL: Keep configs for 1 year unless updated
                            'ttl': int((datetime.now(timezone.utc).timestamp() + (365 * 24 * 60 * 60)))
                        }
                        
                        self.table.put_item(Item=item)
                        loaded_count += 1
                        
                        logger.info(f"Loaded config: {item['model_pattern']} (priority {item['priority']})")
                        
                    except (ValueError, KeyError) as e:
                        logger.error(f"Invalid config row: {row}. Error: {e}")
            
            logger.info(f"Successfully loaded {loaded_count} model configurations from {csv_file_path}")
            return loaded_count
            
        except Exception as e:
            logger.error(f"Failed to load CSV file: {e}")
            return 0
    
    def get_config_for_model(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the best matching configuration for a model.
        
        Args:
            model_name: The model name to match
            
        Returns:
            Configuration dict or None if no match
        """
        try:
            # Get all enabled configurations, sorted by priority
            response = self.table.scan(
                FilterExpression='enabled = :enabled',
                ExpressionAttributeValues={':enabled': True}
            )
            
            configs = response.get('Items', [])
            # Sort by priority (lower number = higher priority)
            configs.sort(key=lambda c: c.get('priority', 999))
            
            # Find first matching pattern
            for config in configs:
                pattern = config.get('model_pattern', '')
                if self._matches_pattern(model_name, pattern):
                    logger.debug(f"Model '{model_name}' matched pattern '{pattern}' with priority {config.get('priority')}")
                    return config
            
            logger.warning(f"No configuration found for model: {model_name}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get config for model {model_name}: {e}")
            return None
    
    def _matches_pattern(self, model_name: str, pattern: str) -> bool:
        """Check if model name matches the pattern."""
        import re
        # Convert glob pattern to regex
        regex_pattern = pattern.replace('*', '.*')
        regex_pattern = f"^{regex_pattern}$"
        return re.match(regex_pattern, model_name, re.IGNORECASE) is not None
    
    def list_all_configs(self) -> List[Dict[str, Any]]:
        """Get all model configurations."""
        try:
            response = self.table.scan()
            configs = response.get('Items', [])
            
            # Sort by priority
            configs.sort(key=lambda c: c.get('priority', 999))
            return configs
            
        except Exception as e:
            logger.error(f"Failed to list configurations: {e}")
            return []
    
    def update_config(self, config_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a specific configuration.
        
        Args:
            config_id: The configuration ID to update
            updates: Dictionary of fields to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            updates['last_updated'] = datetime.now(timezone.utc).isoformat()
            
            # Build update expression
            update_expr = "SET "
            expr_values = {}
            expr_names = {}
            
            for key, value in updates.items():
                if key in ['config_id']:  # Skip key fields
                    continue
                    
                # Handle reserved words
                attr_name = f"#{key}"
                attr_value = f":{key}"
                
                update_expr += f"{attr_name} = {attr_value}, "
                expr_names[attr_name] = key
                
                # Convert floats to Decimal for DynamoDB
                if isinstance(value, float):
                    expr_values[attr_value] = Decimal(str(value))
                else:
                    expr_values[attr_value] = value
            
            # Remove trailing comma
            update_expr = update_expr.rstrip(', ')
            
            self.table.update_item(
                Key={'config_id': config_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values
            )
            
            logger.info(f"Updated configuration {config_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update configuration {config_id}: {e}")
            return False
    
    def delete_config(self, config_id: str) -> bool:
        """Delete a configuration."""
        try:
            self.table.delete_item(Key={'config_id': config_id})
            logger.info(f"Deleted configuration {config_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete configuration {config_id}: {e}")
            return False
    
    def clear_all_configs(self) -> int:
        """Clear all configurations from the table."""
        try:
            response = self.table.scan()
            items = response.get('Items', [])
            
            deleted_count = 0
            for item in items:
                self.table.delete_item(Key={'config_id': item['config_id']})
                deleted_count += 1
            
            logger.info(f"Cleared {deleted_count} configurations")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to clear configurations: {e}")
            return 0


def create_model_config_table():
    """Create the model configuration table with proper schema and indexes."""
    dynamodb = boto3.resource('dynamodb')
    
    table_config = {
        'TableName': MODEL_CONFIG_TABLE,
        'KeySchema': [
            {
                'AttributeName': 'config_id',
                'KeyType': 'HASH'  # Partition key
            }
        ],
        'AttributeDefinitions': [
            {
                'AttributeName': 'config_id',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'model_pattern',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'api_provider',
                'AttributeType': 'S'
            },
            {
                'AttributeName': 'priority',
                'AttributeType': 'N'
            }
        ],
        'GlobalSecondaryIndexes': [
            {
                'IndexName': 'ModelPatternIndex',
                'KeySchema': [
                    {
                        'AttributeName': 'model_pattern',
                        'KeyType': 'HASH'
                    },
                    {
                        'AttributeName': 'priority',
                        'KeyType': 'RANGE'
                    }
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                }
            },
            {
                'IndexName': 'ProviderIndex',
                'KeySchema': [
                    {
                        'AttributeName': 'api_provider',
                        'KeyType': 'HASH'
                    },
                    {
                        'AttributeName': 'priority',
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
        print(f"Creating table {MODEL_CONFIG_TABLE}...")
        
        # Wait for table to be created
        table.wait_until_exists()
        print(f"Table {MODEL_CONFIG_TABLE} created successfully!")
        
        return table
        
    except Exception as e:
        print(f"Error creating table: {e}")
        return None


if __name__ == "__main__":
    # Test the model config table
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Create table (comment out if it already exists)
        # create_model_config_table()
        
        # Test config management
        config_table = ModelConfigTable()
        
        # Load configurations from CSV
        csv_path = "../config/unified_model_config.csv"
        loaded = config_table.load_config_from_csv(csv_path)
        print(f"Loaded {loaded} configurations")
        
        # Test model matching
        test_models = [
            "claude-4-opus",
            "claude-3.5-sonnet-20241022",
            "llama-3.1-sonar-large-128k-online",
            "unknown-model"
        ]
        
        for model in test_models:
            config = config_table.get_config_for_model(model)
            if config:
                print(f"{model}: pattern='{config['model_pattern']}', "
                      f"batch_size={config['initial_batch_size']}, "
                      f"input_cost=${float(config['input_cost_per_million_tokens']):.2f}")
            else:
                print(f"{model}: No configuration found")
        
    except Exception as e:
        print(f"Test failed: {e}")
        print("Note: This test requires AWS credentials and DynamoDB access.")