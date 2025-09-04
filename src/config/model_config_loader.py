#!/usr/bin/env python3
"""
Model Configuration Loader for Batch Size Management

This module loads and manages hierarchical model configurations from CSV files,
supporting pattern matching for flexible model management.
"""

import csv
import re
import os
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, NamedTuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ModelConfig:
    """Configuration for a model or model pattern."""
    model_pattern: str
    min_batch_size: int
    max_batch_size: int
    initial_batch_size: int
    priority: int
    weight: float
    rate_limit_factor: float
    success_threshold: int
    failure_threshold: int
    enabled: bool
    notes: str
    
    def matches_model(self, model_name: str) -> bool:
        """Check if this config matches the given model name."""
        # Convert glob pattern to regex
        pattern = self.model_pattern.replace('*', '.*')
        pattern = f"^{pattern}$"
        return re.match(pattern, model_name, re.IGNORECASE) is not None


class ModelConfigLoader:
    """Loads and manages hierarchical model configurations."""
    
    def __init__(self, config_file_path: Optional[str] = None):
        """
        Initialize the config loader.
        
        Args:
            config_file_path: Path to CSV config file. If None, uses default.
        """
        if config_file_path is None:
            # Default to config file in the same directory
            config_dir = Path(__file__).parent
            config_file_path = config_dir / "model_batch_config.csv"
        
        self.config_file_path = Path(config_file_path)
        self.configs: List[ModelConfig] = []
        self._load_configurations()
    
    def _load_configurations(self):
        """Load configurations from CSV file."""
        try:
            if not self.config_file_path.exists():
                logger.warning(f"Config file not found: {self.config_file_path}. Using defaults.")
                self._create_default_config()
                return
            
            with open(self.config_file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                # Skip comment lines and empty lines
                rows = [row for row in reader if not row.get('model_pattern', '').startswith('#')]
                
                for row in rows:
                    if not row.get('model_pattern'):
                        continue
                        
                    try:
                        config = ModelConfig(
                            model_pattern=row['model_pattern'].strip(),
                            min_batch_size=int(row['min_batch_size']),
                            max_batch_size=int(row['max_batch_size']),
                            initial_batch_size=int(row['initial_batch_size']),
                            priority=int(row['priority']),
                            weight=float(row['weight']),
                            rate_limit_factor=float(row['rate_limit_factor']),
                            success_threshold=int(row['success_threshold']),
                            failure_threshold=int(row['failure_threshold']),
                            enabled=row['enabled'].lower() in ('true', '1', 'yes'),
                            notes=row.get('notes', '').strip()
                        )
                        self.configs.append(config)
                    except (ValueError, KeyError) as e:
                        logger.error(f"Invalid config row: {row}. Error: {e}")
            
            # Sort by priority (lower number = higher priority)
            self.configs.sort(key=lambda c: c.priority)
            logger.info(f"Loaded {len(self.configs)} model configurations from {self.config_file_path}")
            
        except Exception as e:
            logger.error(f"Failed to load config file: {e}. Using defaults.")
            self._create_default_config()
    
    def _create_default_config(self):
        """Create default configuration if file doesn't exist."""
        self.configs = [
            ModelConfig(
                model_pattern="*",
                min_batch_size=10,
                max_batch_size=100,
                initial_batch_size=50,
                priority=999,
                weight=1.0,
                rate_limit_factor=0.75,
                success_threshold=5,
                failure_threshold=2,
                enabled=True,
                notes="Default fallback configuration"
            )
        ]
        logger.info("Using default model configuration")
    
    def get_config_for_model(self, model_name: str) -> ModelConfig:
        """
        Get the best matching configuration for a model.
        
        Args:
            model_name: The model name to match
            
        Returns:
            ModelConfig: The best matching configuration (highest priority)
        """
        # Find all matching configs
        matching_configs = [
            config for config in self.configs
            if config.enabled and config.matches_model(model_name)
        ]
        
        if not matching_configs:
            logger.warning(f"No configuration found for model: {model_name}. Using default.")
            # Return a basic default config
            return ModelConfig(
                model_pattern="*",
                min_batch_size=10,
                max_batch_size=100,
                initial_batch_size=50,
                priority=999,
                weight=1.0,
                rate_limit_factor=0.75,
                success_threshold=5,
                failure_threshold=2,
                enabled=True,
                notes=f"Emergency default for {model_name}"
            )
        
        # Return the highest priority match (lowest priority number)
        best_config = matching_configs[0]
        logger.debug(f"Model '{model_name}' matched pattern '{best_config.model_pattern}' "
                    f"with priority {best_config.priority}")
        return best_config
    
    def list_configurations(self) -> List[Dict]:
        """Return all configurations as dictionaries for logging/debugging."""
        return [
            {
                'pattern': config.model_pattern,
                'priority': config.priority,
                'batch_range': f"{config.min_batch_size}-{config.max_batch_size}",
                'initial': config.initial_batch_size,
                'weight': config.weight,
                'enabled': config.enabled,
                'notes': config.notes
            }
            for config in self.configs
        ]
    
    def reload_config(self):
        """Reload configuration from file."""
        logger.info("Reloading model configuration...")
        self.configs = []
        self._load_configurations()
    
    def test_model_matching(self, test_models: List[str]) -> Dict[str, Dict]:
        """
        Test which configuration each model would match.
        
        Args:
            test_models: List of model names to test
            
        Returns:
            Dict mapping model names to their matched configuration info
        """
        results = {}
        for model in test_models:
            config = self.get_config_for_model(model)
            results[model] = {
                'matched_pattern': config.model_pattern,
                'priority': config.priority,
                'initial_batch_size': config.initial_batch_size,
                'batch_range': f"{config.min_batch_size}-{config.max_batch_size}",
                'weight': config.weight,
                'notes': config.notes
            }
        return results


def test_config_loader():
    """Test function to demonstrate configuration loading and matching."""
    loader = ModelConfigLoader()
    
    # Test models
    test_models = [
        "claude-4-opus",
        "claude-3.5-sonnet-20241022",
        "claude-3-haiku",
        "llama-3.1-sonar-large-128k-online",
        "llama-3.1-sonar-small-128k-online",
        "gpt-4-turbo",
        "unknown-model-123"
    ]
    
    print("Model Configuration Test Results:")
    print("=" * 50)
    
    results = loader.test_model_matching(test_models)
    for model, config_info in results.items():
        print(f"Model: {model}")
        print(f"  Matched Pattern: {config_info['matched_pattern']}")
        print(f"  Priority: {config_info['priority']}")
        print(f"  Initial Batch Size: {config_info['initial_batch_size']}")
        print(f"  Batch Range: {config_info['batch_range']}")
        print(f"  Weight: {config_info['weight']}")
        print(f"  Notes: {config_info['notes']}")
        print()


if __name__ == "__main__":
    # Configure logging for testing
    logging.basicConfig(level=logging.INFO)
    test_config_loader()