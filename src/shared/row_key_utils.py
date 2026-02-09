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

def generate_row_key(row: Dict[str, Any], primary_keys: List[str] = None) -> str:
    """
    Generate a unique row key based on primary key columns (or entire row) using hashing.

    This uses SHA-256 hashing to create a stable, encoding-agnostic row key.
    This approach avoids all Unicode normalization issues by treating the data as bytes.

    Args:
        row: Dictionary containing row data
        primary_keys: List of column names that form the primary key.
                     If None or empty, hashes the ENTIRE row (all fields).

    Returns:
        A hex string of the SHA-256 hash of the primary key values or entire row
    """
    if not primary_keys:
        # Hash ENTIRE row when no primary keys specified
        # This ensures every unique row gets validated, even with duplicate IDs
        logger.debug("No primary keys provided, hashing entire row for row key generation")

        # Sort keys for deterministic hashing
        sorted_items = sorted(row.items())

        # Build key data from all fields
        # Exclude all internal fields (starting with '_') like _row_key, _history
        key_data = {
            "mode": "full_row",
            "fields": {k: (str(v).strip() if v is not None and str(v).strip() else "EMPTY")
                      for k, v in sorted_items if not k.startswith('_')}
        }

        # Convert to JSON string with sorted keys for consistency
        json_str = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
    else:
        # Hash only primary key fields (original behavior)
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
            "mode": "primary_keys",
            "keys": primary_keys,
            "values": key_values
        }

        # Convert to JSON string with sorted keys for consistency
        json_str = json.dumps(key_data, sort_keys=True, ensure_ascii=False)

    # Hash the JSON string
    # Use UTF-8 encoding to handle all Unicode properly
    hash_obj = hashlib.sha256(json_str.encode('utf-8'))
    row_key = hash_obj.hexdigest()

    if primary_keys:
        logger.debug(f"Generated row key hash: {row_key[:8]}... for primary keys: {primary_keys}")
    else:
        logger.debug(f"Generated full-row hash: {row_key[:8]}... from {len(row)} fields")

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

def extract_id_column_values(row: Dict[str, Any], id_columns: List[str]) -> Dict[str, Any]:
    """
    Extract ID column values from a row for memory row context.

    Args:
        row: Dictionary containing row data
        id_columns: List of column names that are identity columns

    Returns:
        Dict with id_columns, id_values, row_key (hash), and row_id_display
    """
    if not id_columns:
        return {
            'id_columns': [],
            'id_values': [],
            'row_key': generate_row_key(row),
            'row_id_display': ''
        }

    id_values = []
    for col in id_columns:
        val = row.get(col, '')
        id_values.append(str(val).strip() if val is not None else '')

    return {
        'id_columns': list(id_columns),
        'id_values': id_values,
        'row_key': generate_row_key(row, primary_keys=id_columns),
        'row_id_display': ' | '.join(v for v in id_values if v)
    }

# Export the main functions
__all__ = ['generate_row_key', 'validate_row_key', 'convert_legacy_row_key', 'extract_id_column_values']