#!/usr/bin/env python3
"""
Enhanced Dynamic Batch Size Manager

This module provides configuration-driven, audit-logged batch size management
with hierarchical model pattern matching and comprehensive tracking.
"""

import logging
import os
from typing import Dict, Any, Optional, Set
from pathlib import Path

logger = logging.getLogger(__name__)


class EnhancedDynamicBatchSizeManager:
    """
    Manages dynamic batch sizing with CSV configuration and audit logging.
    
    ENHANCED PER-MODEL STRATEGY:
    - CSV-driven configuration with hierarchical pattern matching
    - Auto-registers new models with pattern-based configuration
    - Audit logging of all batch size changes to DynamoDB
    - Weight-based adjustment factors for different model tiers
    - When multiple models are used in a batch, use the minimum batch size
    - When multiple models are successful, only increase the model with lowest batch size
    """
    
    def __init__(self, 
                 config_file_path: Optional[str] = None,
                 session_id: Optional[str] = None,
                 enable_audit_logging: bool = True):
        """
        Initialize the enhanced batch size manager.
        
        Args:
            config_file_path: Path to CSV configuration file
            session_id: Session ID for audit logging
            enable_audit_logging: Whether to log changes to DynamoDB
        """
        
        self.session_id = session_id
        self.enable_audit_logging = enable_audit_logging
        
        # Try to import configuration modules
        self.config_table = None
        self.config_loader = None  # Fallback to CSV
        self.audit_logger = None
        
        # Try DynamoDB config first (preferred)
        try:
            from shared.model_config_table import ModelConfigTable
            self.config_table = ModelConfigTable()
            logger.info("✅ Using DynamoDB model configuration table")
        except ImportError as e:
            logger.warning(f"DynamoDB config not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to initialize DynamoDB config: {e}")
        
        # Fallback to CSV config if DynamoDB not available
        if not self.config_table:
            try:
                from config.model_config_loader import ModelConfigLoader
                config_path = config_file_path or self._get_default_config_path()
                self.config_loader = ModelConfigLoader(config_path)
                logger.info(f"✅ Loaded CSV model configuration from: {config_path}")
            except ImportError as e:
                logger.warning(f"CSV config loader not available: {e}. Using defaults.")
            except Exception as e:
                logger.error(f"Failed to load CSV model configuration: {e}. Using defaults.")
        
        # Initialize audit logging
        if enable_audit_logging:
            try:
                from shared.batch_audit_logger import BatchAuditLogger
                self.audit_logger = BatchAuditLogger()
                logger.info("✅ Batch audit logging enabled")
            except ImportError as e:
                logger.warning(f"Audit logger not available: {e}")
                self.enable_audit_logging = False
            except Exception as e:
                logger.warning(f"Failed to initialize audit logger: {e}")
                self.enable_audit_logging = False
        
        # Per-model tracking dictionaries
        self.model_batch_sizes = {}  # Dict[str, int]
        self.model_consecutive_successes = {}  # Dict[str, int]
        self.model_consecutive_failures = {}  # Dict[str, int]
        self.model_rate_limit_events = {}  # Dict[str, int]
        self.model_configs = {}  # Dict[str, ModelConfig] - cached configurations
        
        self.total_batches = 0
        
        logger.info(f"🔧 ENHANCED BATCH MANAGER: session_id={session_id or 'none'}, "
                   f"audit={'on' if self.enable_audit_logging else 'off'}")
    
    def _get_default_config_path(self) -> str:
        """Get the default path for model configuration CSV."""
        # Try to find config relative to this file
        current_dir = Path(__file__).parent
        config_path = current_dir.parent / "config" / "model_batch_config.csv"
        return str(config_path)
    
    def register_model(self, model: str):
        """Register a new model with configuration-driven settings."""
        if model in self.model_batch_sizes:
            return  # Already registered
        
        # Get configuration for this model
        config = None
        if self.config_table:
            # Use DynamoDB configuration (preferred)
            try:
                config_dict = self.config_table.get_config_for_model(model)
                if config_dict:
                    # Convert DynamoDB item to config-like object
                    from types import SimpleNamespace
                    config = SimpleNamespace()
                    config.model_pattern = config_dict.get('model_pattern', model)
                    config.min_batch_size = int(config_dict.get('min_batch_size', 10))
                    config.max_batch_size = int(config_dict.get('max_batch_size', 100))
                    config.initial_batch_size = int(config_dict.get('initial_batch_size', 50))
                    config.priority = int(config_dict.get('priority', 999))
                    config.weight = float(config_dict.get('weight', 1.0))
                    config.rate_limit_factor = float(config_dict.get('rate_limit_factor', 0.75))
                    config.success_threshold = int(config_dict.get('success_threshold', 5))
                    config.failure_threshold = int(config_dict.get('failure_threshold', 2))
                    config.api_provider = config_dict.get('api_provider', 'unknown')
                    config.input_cost_per_million = float(config_dict.get('input_cost_per_million_tokens', 5.0))
                    config.output_cost_per_million = float(config_dict.get('output_cost_per_million_tokens', 10.0))
                    config.notes = config_dict.get('notes', '')
                    self.model_configs[model] = config
            except Exception as e:
                logger.error(f"Failed to get DynamoDB config for model {model}: {e}")
        elif self.config_loader:
            # Fallback to CSV configuration
            try:
                config = self.config_loader.get_config_for_model(model)
                self.model_configs[model] = config
            except Exception as e:
                logger.error(f"Failed to get CSV config for model {model}: {e}")
        
        # Use configuration values or defaults
        if config:
            initial_batch_size = config.initial_batch_size
            logger.info(f"📝 NEW MODEL REGISTERED: {model} with batch_size={initial_batch_size}")
            logger.info(f"   ↳ Pattern: '{config.model_pattern}', priority: {config.priority}, "
                       f"range: [{config.min_batch_size}-{config.max_batch_size}], weight: {config.weight}")
        else:
            initial_batch_size = 50  # Default production batch size
            logger.info(f"📝 NEW MODEL REGISTERED: {model} with default batch_size={initial_batch_size}")
        
        # Register the model
        self.model_batch_sizes[model] = initial_batch_size
        self.model_consecutive_successes[model] = 0
        self.model_consecutive_failures[model] = 0
        self.model_rate_limit_events[model] = 0
        
        # Audit log the registration
        if self.enable_audit_logging and self.audit_logger:
            try:
                config_dict = {
                    'model_pattern': config.model_pattern if config else 'default',
                    'initial_batch_size': initial_batch_size,
                    'min_batch_size': config.min_batch_size if config else 10,
                    'max_batch_size': config.max_batch_size if config else 100,
                    'priority': config.priority if config else 999,
                    'weight': config.weight if config else 1.0
                }
                self.audit_logger.log_model_registration(model, config_dict, self.session_id)
            except Exception as e:
                logger.error(f"Failed to audit log model registration: {e}")
    
    def get_batch_size_for_models(self, models: Set[str]) -> int:
        """
        Get the appropriate batch size based on which models will be used.
        
        Args:
            models: Set of model names
            
        Returns:
            The batch size to use for this batch (minimum across all models)
        """
        if not models:
            return 50  # Default fallback
        
        # Register any new models
        for model in models:
            self.register_model(model)
        
        # Use minimum batch size across all models
        batch_sizes = [self.model_batch_sizes[model] for model in models]
        min_batch_size = min(batch_sizes)
        
        if len(models) > 1:
            model_sizes_str = ", ".join([f"{model}={self.model_batch_sizes[model]}" for model in sorted(models)])
            logger.info(f"🔀 MULTI-MODEL BATCH: Using minimum batch size {min_batch_size} ({model_sizes_str})")
        
        return min_batch_size
    
    def on_rate_limit(self, model: str):
        """
        Called when a rate limit is encountered for a specific model.
        
        Args:
            model: The model that hit the rate limit
        """
        self.register_model(model)
        
        # Get model configuration for limits and factors
        config = self.model_configs.get(model)
        min_batch_size = config.min_batch_size if config else 10
        rate_limit_factor = config.rate_limit_factor if config else 0.75
        
        old_batch_size = self.model_batch_sizes[model]
        self.model_rate_limit_events[model] += 1
        self.model_consecutive_failures[model] += 1
        self.model_consecutive_successes[model] = 0
        
        new_batch_size = max(
            min_batch_size,
            int(old_batch_size * rate_limit_factor)
        )
        
        if new_batch_size != old_batch_size:
            self.model_batch_sizes[model] = new_batch_size
            logger.warning(f"🚨 {model} RATE LIMIT: {old_batch_size} → {new_batch_size} "
                          f"(factor: {rate_limit_factor})")
            
            # Audit log the change
            if self.enable_audit_logging and self.audit_logger:
                try:
                    self.audit_logger.log_batch_size_change(
                        model=model,
                        old_batch_size=old_batch_size,
                        new_batch_size=new_batch_size,
                        change_reason="rate_limit",
                        session_id=self.session_id,
                        additional_context={
                            "rate_limit_count": self.model_rate_limit_events[model],
                            "rate_limit_factor": rate_limit_factor
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to audit log rate limit change: {e}")
        else:
            logger.warning(f"🚨 {model} RATE LIMIT: Already at minimum ({old_batch_size})")
    
    def on_success(self, models_used: Set[str]):
        """
        Called when a batch completes successfully.
        
        Args:
            models_used: Set of models actually used in this batch
        """
        self.total_batches += 1
        
        if not models_used:
            return
        
        # Register any new models and update success counters
        for model in models_used:
            self.register_model(model)
            self.model_consecutive_successes[model] += 1
            self.model_consecutive_failures[model] = 0
        
        # Only increase the model with the lowest batch size
        min_model = min(models_used, key=lambda m: self.model_batch_sizes[m])
        self._try_increase_batch_size(min_model)
    
    def on_failure(self, models_used: Set[str], is_rate_limit: bool = False):
        """
        Called when a batch fails.
        
        Args:
            models_used: Set of models used in this batch
            is_rate_limit: Whether the failure was due to rate limiting
        """
        if is_rate_limit:
            # Rate limits are handled by on_rate_limit
            return
        
        if not models_used:
            return
        
        # Register models and update failure counters
        for model in models_used:
            self.register_model(model)
            self.model_consecutive_failures[model] += 1
            self.model_consecutive_successes[model] = 0
            self._try_decrease_batch_size(model)
    
    def _try_increase_batch_size(self, model: str):
        """Helper method to try increasing batch size for a specific model."""
        config = self.model_configs.get(model)
        success_threshold = config.success_threshold if config else 5
        max_batch_size = config.max_batch_size if config else 100
        weight = config.weight if config else 1.0
        
        if (self.model_consecutive_successes[model] >= success_threshold and 
            self.model_batch_sizes[model] < max_batch_size):
            
            old_batch_size = self.model_batch_sizes[model]
            
            # Use weight to determine increase factor
            # Higher weight = more aggressive increases
            base_increase = 1.1  # 10% base increase
            weighted_increase = base_increase + ((weight - 1.0) * 0.05)  # +5% per weight point above 1.0
            weighted_increase = max(1.05, min(weighted_increase, 1.3))  # Cap between 5% and 30%
            
            new_batch_size = min(
                max_batch_size,
                int(old_batch_size * weighted_increase)
            )
            
            if new_batch_size != old_batch_size:
                self.model_batch_sizes[model] = new_batch_size
                self.model_consecutive_successes[model] = 0
                
                logger.info(f"✅ {model} SUCCESS STREAK: {old_batch_size} → {new_batch_size} "
                           f"(weight: {weight}, factor: {weighted_increase:.2f}, "
                           f"successes: {self.model_consecutive_successes[model]})")
                
                # Audit log the change
                if self.enable_audit_logging and self.audit_logger:
                    try:
                        self.audit_logger.log_batch_size_change(
                            model=model,
                            old_batch_size=old_batch_size,
                            new_batch_size=new_batch_size,
                            change_reason="success_streak",
                            session_id=self.session_id,
                            additional_context={
                                "consecutive_successes": self.model_consecutive_successes[model] + success_threshold,
                                "weight": weight,
                                "increase_factor": weighted_increase
                            }
                        )
                    except Exception as e:
                        logger.error(f"Failed to audit log success increase: {e}")
    
    def _try_decrease_batch_size(self, model: str):
        """Helper method to try decreasing batch size for a specific model."""
        config = self.model_configs.get(model)
        failure_threshold = config.failure_threshold if config else 2
        min_batch_size = config.min_batch_size if config else 10
        
        if self.model_consecutive_failures[model] >= failure_threshold:
            old_batch_size = self.model_batch_sizes[model]
            
            # Use fixed 25% decrease for failures
            new_batch_size = max(
                min_batch_size,
                int(old_batch_size * 0.75)
            )
            
            if new_batch_size != old_batch_size:
                self.model_batch_sizes[model] = new_batch_size
                self.model_consecutive_failures[model] = 0
                
                logger.warning(f"⚠️ {model} FAILURE STREAK: {old_batch_size} → {new_batch_size} "
                              f"(failures: {self.model_consecutive_failures[model]})")
                
                # Audit log the change
                if self.enable_audit_logging and self.audit_logger:
                    try:
                        self.audit_logger.log_batch_size_change(
                            model=model,
                            old_batch_size=old_batch_size,
                            new_batch_size=new_batch_size,
                            change_reason="failure_streak",
                            session_id=self.session_id,
                            additional_context={
                                "consecutive_failures": self.model_consecutive_failures[model] + failure_threshold,
                                "decrease_factor": 0.75
                            }
                        )
                    except Exception as e:
                        logger.error(f"Failed to audit log failure decrease: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics for monitoring."""
        stats = {
            'total_batches': self.total_batches,
            'registered_models': list(self.model_batch_sizes.keys()),
            'model_batch_sizes': dict(self.model_batch_sizes),
            'model_consecutive_successes': dict(self.model_consecutive_successes),
            'model_consecutive_failures': dict(self.model_consecutive_failures),
            'model_rate_limit_events': dict(self.model_rate_limit_events),
            'config_enabled': self.config_loader is not None,
            'audit_enabled': self.enable_audit_logging
        }
        
        # Add model configurations
        model_configs = {}
        for model, config in self.model_configs.items():
            model_configs[model] = {
                'pattern': config.model_pattern,
                'priority': config.priority,
                'weight': config.weight,
                'batch_range': f"{config.min_batch_size}-{config.max_batch_size}",
                'thresholds': f"success:{config.success_threshold}, failure:{config.failure_threshold}"
            }
        stats['model_configurations'] = model_configs
        
        # Add success rates per model
        model_success_rates = {}
        for model in self.model_batch_sizes.keys():
            failures = self.model_consecutive_failures[model]
            rate_limits = self.model_rate_limit_events[model]
            total_issues = failures + rate_limits
            # Simple heuristic for success rate
            if self.total_batches > 10:
                model_success_rates[model] = max(0.0, 1.0 - (total_issues / max(1, self.total_batches)))
            else:
                model_success_rates[model] = 1.0 if total_issues == 0 else 0.5
        
        stats['model_success_rates'] = model_success_rates
        return stats
    
    def log_status(self):
        """Log current status for monitoring."""
        if not self.model_batch_sizes:
            logger.info("📊 ENHANCED BATCH MANAGER: No models registered yet")
            return
        
        model_status = []
        for model in sorted(self.model_batch_sizes.keys()):
            config = self.model_configs.get(model)
            weight_str = f"w:{config.weight:.1f}" if config else "w:1.0"
            
            status = (f"{model}={self.model_batch_sizes[model]} "
                     f"(succ={self.model_consecutive_successes[model]}, "
                     f"fail={self.model_consecutive_failures[model]}, "
                     f"rl={self.model_rate_limit_events[model]}, {weight_str})")
            model_status.append(status)
        
        logger.info(f"📊 ENHANCED BATCH MANAGER STATUS: {'; '.join(model_status)}")


def test_enhanced_manager():
    """Test function for the enhanced batch manager."""
    import logging
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Enhanced Dynamic Batch Size Manager")
    print("=" * 50)
    
    # Initialize manager
    manager = EnhancedDynamicBatchSizeManager(
        session_id="test_session_123",
        enable_audit_logging=False  # Disable for testing
    )
    
    # Test model registration
    test_models = {
        "claude-4-opus",
        "claude-3.5-sonnet-20241022", 
        "llama-3.1-sonar-large-128k-online",
        "gpt-4-unknown"
    }
    
    # Get batch size for models
    batch_size = manager.get_batch_size_for_models(test_models)
    print(f"Initial batch size for {len(test_models)} models: {batch_size}")
    
    # Simulate some operations
    print("\nSimulating operations:")
    
    # Success
    manager.on_success({"claude-4-opus"})
    print("✅ Recorded success for claude-4-opus")
    
    # Rate limit
    manager.on_rate_limit("claude-3.5-sonnet-20241022")
    print("🚨 Recorded rate limit for claude-3.5-sonnet-20241022")
    
    # Show final status
    print("\nFinal Status:")
    manager.log_status()
    
    # Show stats
    print("\nStatistics:")
    stats = manager.get_stats()
    for key, value in stats.items():
        if key != 'model_configurations':  # Skip complex nested dict
            print(f"  {key}: {value}")


if __name__ == "__main__":
    test_enhanced_manager()