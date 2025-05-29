#!/usr/bin/env python3
"""
Centralized row key generation utilities.

This module provides a single source of truth for generating row keys
to ensure consistency across the entire codebase.
"""

import logging
from typing import Dict, List, Any
import re

logger = logging.getLogger(__name__)

# Define acceptable characters for row keys
# Only ASCII letters, numbers, spaces, and common punctuation
ACCEPTABLE_CHARS = set(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    '0123456789'
    ' -_.,/()[]{}|:;!?@#$%^&*+=<>"\''
)

def sanitize_for_row_key(value: str) -> str:
    """
    Sanitize a value to only contain acceptable characters for row keys.
    
    This uses a whitelist approach - only characters in ACCEPTABLE_CHARS are kept.
    All other characters (including Unicode variants) are replaced with their 
    closest ASCII equivalent or removed.
    
    Args:
        value: String value to sanitize
        
    Returns:
        Sanitized string containing only acceptable characters
    """
    if not value:
        return ""
    
    # Common Unicode replacements
    unicode_replacements = {
        '\u2011': '-',  # Non-breaking hyphen → regular hyphen
        '\u2010': '-',  # Hyphen → regular hyphen
        '\u2012': '-',  # Figure dash → regular hyphen
        '\u2013': '-',  # En dash → regular hyphen
        '\u2014': '-',  # Em dash → regular hyphen
        '\u2015': '-',  # Horizontal bar → regular hyphen
        '\u2212': '-',  # Minus sign → regular hyphen
        '\u00a0': ' ',  # Non-breaking space → regular space
        '\u2009': ' ',  # Thin space → regular space
        '\u200a': ' ',  # Hair space → regular space
        '\u2018': "'",  # Left single quote → apostrophe
        '\u2019': "'",  # Right single quote → apostrophe
        '\u201c': '"',  # Left double quote → double quote
        '\u201d': '"',  # Right double quote → double quote
    }
    
    # First, replace known Unicode characters
    result = value
    for unicode_char, ascii_char in unicode_replacements.items():
        result = result.replace(unicode_char, ascii_char)
    
    # Then, keep only acceptable characters
    sanitized = ''.join(char for char in result if char in ACCEPTABLE_CHARS)
    
    # Clean up multiple spaces/hyphens
    sanitized = re.sub(r'\s+', ' ', sanitized)  # Multiple spaces to single space
    sanitized = re.sub(r'-+', '-', sanitized)   # Multiple hyphens to single hyphen
    sanitized = sanitized.strip()
    
    if sanitized != value:
        logger.debug(f"Sanitized row key value: '{value}' → '{sanitized}'")
    
    return sanitized

def generate_row_key(row: Dict[str, Any], primary_keys: List[str]) -> str:
    """
    Generate a unique row key based on primary key columns.
    
    This is the single source of truth for row key generation across the entire codebase.
    All other modules should import and use this function.
    
    The function ensures all row keys contain only acceptable ASCII characters
    to prevent Unicode-related mismatches.
    
    Args:
        row: Dictionary containing row data
        primary_keys: List of column names that form the primary key
        
    Returns:
        A string key that uniquely identifies the row, containing only ASCII characters
    """
    if not primary_keys:
        logger.warning("No primary keys provided for row key generation")
        return "NO_KEY"
    
    key_parts = []
    for key_field in primary_keys:
        # Get the value, ensuring it's a string
        value = str(row.get(key_field, "")).strip()
        
        # Sanitize the value to contain only acceptable characters
        sanitized_value = sanitize_for_row_key(value)
        
        # If sanitization removed all characters, use a placeholder
        if not sanitized_value:
            sanitized_value = "EMPTY"
        
        key_parts.append(sanitized_value)
    
    # Join with double pipe separator
    row_key = "||".join(key_parts)
    
    logger.debug(f"Generated row key: {row_key}")
    return row_key

def validate_row_key(row_key: str) -> bool:
    """
    Validate that a row key contains only acceptable characters.
    
    Args:
        row_key: Row key to validate
        
    Returns:
        True if the row key is valid, False otherwise
    """
    if not row_key:
        return False
    
    # Check if all characters are in the acceptable set
    for char in row_key:
        if char not in ACCEPTABLE_CHARS:
            logger.warning(f"Invalid character in row key: '{char}' (ord={ord(char)})")
            return False
    
    return True

def convert_legacy_row_key(legacy_key: str) -> str:
    """
    Convert a legacy row key (with single pipe separator) to new format.
    Also sanitizes the key to ensure it contains only acceptable characters.
    
    Args:
        legacy_key: Legacy row key with single pipe separator
        
    Returns:
        Converted row key with double pipe separator and sanitized values
    """
    if not legacy_key:
        return "NO_KEY"
    
    # Split by single pipe (handling the case where || might already exist)
    if "||" in legacy_key:
        # Already in new format, just sanitize
        parts = legacy_key.split("||")
    else:
        # Legacy format with single pipe
        parts = legacy_key.split("|")
    
    # Sanitize each part
    sanitized_parts = [sanitize_for_row_key(part) for part in parts]
    
    # Join with double pipe
    new_key = "||".join(sanitized_parts)
    
    if new_key != legacy_key:
        logger.info(f"Converted/sanitized row key: '{legacy_key}' → '{new_key}'")
    
    return new_key

# Export the main function at module level for easy import
__all__ = ['generate_row_key', 'validate_row_key', 'convert_legacy_row_key', 'sanitize_for_row_key'] 