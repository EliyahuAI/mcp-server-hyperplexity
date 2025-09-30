#!/usr/bin/env python3
"""
Centralized row key generation utilities using hashing.

This module provides a single source of truth for generating row keys
using cryptographic hashing to ensure consistency and avoid encoding issues.
"""

import hashlib
import json
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

def generate_row_key(row: Dict[str, Any], primary_keys: List[str]) -> str:
    """
    Generate a unique row key based on primary key columns using hashing.
    
    This uses SHA-256 hashing of the primary key values to create a stable,
    encoding-agnostic row key. This approach avoids all Unicode normalization
    issues by treating the data as bytes.
    
    Args:
        row: Dictionary containing row data
        primary_keys: List of column names that form the primary key
        
    Returns:
        A hex string of the SHA-256 hash of the primary key values
    """
    if not primary_keys:
        logger.warning("No primary keys provided for row key generation")
        return "NO_KEY"
    
    # Collect primary key values in order
    key_values = []
    for key_field in primary_keys:
        value = row.get(key_field, "")
        # Convert to string representation
        if value is None:
            value_str = "NULL"
        elif isinstance(value, str) and not value.strip():
            value_str = "EMPTY"
        else:
            value_str = str(value).strip()
        key_values.append(value_str)
        
    # Create a stable JSON representation
    # JSON ensures consistent ordering and handles Unicode properly
    key_data = {
        "keys": primary_keys,
        "values": key_values
    }
    
    # Convert to JSON string with sorted keys for consistency
    json_str = json.dumps(key_data, sort_keys=True, ensure_ascii=False)

    # Hash the JSON string
    # Use UTF-8 encoding to handle all Unicode properly
    hash_obj = hashlib.sha256(json_str.encode('utf-8'))
    row_key = hash_obj.hexdigest()

    logger.debug(f"Generated row key hash: {row_key[:8]}... for values: {key_values}")
    logger.error(f"[ROW_KEY_GENERATION] Full hash: {row_key}")
    logger.error(f"[ROW_KEY_GENERATION] Primary keys: {primary_keys}")
    logger.error(f"[ROW_KEY_GENERATION] Key values: {key_values}")
    logger.error(f"[ROW_KEY_GENERATION] JSON string: {json_str}")

    return row_key

def validate_row_key(row_key: str) -> bool:
    """
    Validate that a row key is a valid SHA-256 hash.
    
    Args:
        row_key: Row key to validate
        
    Returns:
        True if the row key is a valid 64-character hex string, False otherwise
    """
    if not row_key:
        return False
    
    # SHA-256 produces 64 hex characters
    if len(row_key) != 64:
        return False
    
    # Check if all characters are valid hex
    try:
        int(row_key, 16)
        return True
    except ValueError:
        return False

def convert_legacy_row_key(legacy_key: str, row_data: Dict[str, Any] = None, primary_keys: List[str] = None) -> str:
    """
    Convert a legacy row key to the new hash format.
    
    Since we can't reverse a hash, this function requires the original row data
    to generate the new hash-based key.
    
    Args:
        legacy_key: Legacy row key (not used in new format)
        row_data: Original row data (required)
        primary_keys: List of primary key columns (required)
        
    Returns:
        New hash-based row key
    """
    if not row_data or not primary_keys:
        logger.error("Cannot convert legacy key without row data and primary keys")
        return "CONVERSION_ERROR"
    
    return generate_row_key(row_data, primary_keys)

# Cleanup functions - no longer needed with hash-based approach
def sanitize_for_row_key(value: str) -> str:
    """
    DEPRECATED: No longer needed with hash-based row keys.
    Kept for backward compatibility only.
    """
    logger.warning("sanitize_for_row_key is deprecated with hash-based row keys")
    return value

def normalize_unicode_spaces(text: str) -> str:
    """
    DEPRECATED: No longer needed with hash-based row keys.
    Kept for backward compatibility only.
    """
    logger.warning("normalize_unicode_spaces is deprecated with hash-based row keys")
    return text

# Export the main functions
__all__ = ['generate_row_key', 'validate_row_key', 'convert_legacy_row_key'] 