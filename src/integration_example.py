#!/usr/bin/env python3
"""
Integration Example: Enhanced Batch Size Manager

This script demonstrates how to integrate the enhanced batch manager
into the lambda function with minimal changes to existing code.
"""

import logging
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_enhanced_batch_manager(session_id: Optional[str] = None, 
                                enable_audit_logging: bool = True) -> 'DynamicBatchSizeManager':
    """
    Create either the enhanced or fallback batch manager.
    
    This function attempts to create the enhanced batch manager with CSV config
    and audit logging. If that fails, it falls back to the original implementation.
    
    Args:
        session_id: Session ID for audit logging
        enable_audit_logging: Whether to enable DynamoDB audit logging
        
    Returns:
        Either EnhancedDynamicBatchSizeManager or original DynamicBatchSizeManager
    """
    
    # Try to use the enhanced version
    try:
        from shared.enhanced_batch_manager import EnhancedDynamicBatchSizeManager
        
        manager = EnhancedDynamicBatchSizeManager(
            session_id=session_id,
            enable_audit_logging=enable_audit_logging
        )
        
        logger.info("✅ Using EnhancedDynamicBatchSizeManager with CSV config and audit logging")
        return manager
        
    except ImportError as e:
        logger.warning(f"Enhanced batch manager not available: {e}")
    except Exception as e:
        logger.error(f"Failed to create enhanced batch manager: {e}")
    
    # Fallback to original implementation
    logger.info("⚠️ Falling back to original DynamicBatchSizeManager")
    from lambda_function import DynamicBatchSizeManager  # Original implementation
    
    return DynamicBatchSizeManager(
        initial_batch_size=50,
        min_batch_size=10,
        max_batch_size=100,
        success_increase_factor=1.1,
        failure_decrease_factor=0.75,
        consecutive_successes_for_increase=5,
        consecutive_failures_for_decrease=2
    )


def integration_test():
    """Test the integration and show how to use it."""
    print("Enhanced Batch Manager Integration Test")
    print("=" * 50)
    
    # Create enhanced manager
    session_id = "integration_test_session_123"
    manager = create_enhanced_batch_manager(
        session_id=session_id,
        enable_audit_logging=False  # Disable for testing
    )
    
    print(f"Manager type: {type(manager).__name__}")
    print(f"Session ID: {session_id}")
    print()
    
    # Test with various models
    test_models = {
        "claude-4-opus",
        "claude-3.5-sonnet-20241022", 
        "llama-3.1-sonar-large-128k-online"
    }
    
    print("Testing model registration and batch sizing:")
    batch_size = manager.get_batch_size_for_models(test_models)
    print(f"Batch size for {len(test_models)} models: {batch_size}")
    print()
    
    # Show statistics
    print("Current statistics:")
    stats = manager.get_stats()
    for key, value in stats.items():
        if key not in ['model_configurations']:  # Skip complex nested structures
            print(f"  {key}: {value}")
    print()
    
    # Show status
    print("Manager status:")
    manager.log_status()
    print()
    
    return manager


def lambda_integration_example():
    """
    Example of how to modify the lambda function to use enhanced batch manager.
    
    This shows the minimal changes needed in the existing lambda code.
    """
    
    print("Lambda Integration Example")
    print("=" * 50)
    print()
    
    # In your lambda_handler function, replace the DynamicBatchSizeManager creation:
    print("BEFORE (in process_all_rows function):")
    print("""
    # Initialize dynamic batch size manager
    batch_manager = DynamicBatchSizeManager(
        initial_batch_size=50,
        min_batch_size=10,
        max_batch_size=100,
        success_increase_factor=1.1,
        failure_decrease_factor=0.75,
        consecutive_successes_for_increase=5,
        consecutive_failures_for_decrease=2
    )
    """)
    
    print("AFTER:")
    print("""
    # Initialize enhanced dynamic batch size manager
    batch_manager = create_enhanced_batch_manager(
        session_id=session_id,  # Pass the session ID for audit logging
        enable_audit_logging=True  # Enable audit logging to DynamoDB
    )
    """)
    
    print("That's it! The enhanced manager is a drop-in replacement.")
    print("All existing code (get_batch_size_for_models, on_success, on_failure, etc.) works unchanged.")
    print()
    
    # Show example configuration
    print("Example CSV Configuration (/src/config/model_batch_config.csv):")
    print("-" * 60)
    print("model_pattern,min_batch_size,max_batch_size,initial_batch_size,priority,weight,...")
    print("claude-4*,5,200,100,1,1.5,0.5,5,2,true,Latest Claude models")
    print("claude-3.5*,10,150,80,2,1.3,0.6,5,2,true,Claude 3.5 family") 
    print("llama-3.1-sonar-large*,8,120,60,1,1.4,0.7,5,2,true,Large Perplexity models")
    print("*,25,50,30,999,1.0,0.9,3,2,true,Default for unknown models")
    print()
    
    # Show management commands
    print("Batch Audit Management Commands:")
    print("-" * 40)
    print("python manage_dynamodb_tables.py batch-history claude-3.5-sonnet-20241022")
    print("python manage_dynamodb_tables.py recent-batch-changes 24")
    print("python manage_dynamodb_tables.py create-batch-audit-table")
    print()


if __name__ == "__main__":
    # Run integration test
    manager = integration_test()
    
    print("\n" + "=" * 50)
    
    # Show lambda integration example
    lambda_integration_example()
    
    print("Integration test completed!")