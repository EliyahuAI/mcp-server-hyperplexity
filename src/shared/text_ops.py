#!/usr/bin/env python3
"""
Extended Text Operations for JSON Patch
Provides text manipulation operations that work within string fields before standard JSON Patch.

Spec version: 2.0

Operations:
- text_replace: Find and replace within string fields (supports regex, insert before/after, delete)
- text_extend: Append or prepend text to string fields

Example:
    from shared.text_ops import apply_text_operations

    ops = [
        {"op": "text_replace", "path": "/report", "match": "| Alice | 30 |", "value": "| Alice | 31 |"},
        {"op": "text_extend", "path": "/report", "value": "\\n| New | Row |"}
    ]

    result = apply_text_operations(data, ops)
"""

import re
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import threading
from functools import wraps

logger = logging.getLogger(__name__)

TEXT_OPS_VERSION = "2.0"


@dataclass
class TextOpResult:
    """Result of applying text operations"""
    success: bool
    modified_data: Optional[Dict] = None
    error: Optional[str] = None
    operations_applied: int = 0


class RegexTimeout(Exception):
    """Raised when regex operation exceeds timeout"""
    pass


def with_timeout(timeout_seconds=2):
    """
    Decorator to add timeout to regex operations.
    Uses threading to support all platforms (Windows/Linux/Mac).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = [None]
            exception = [None]

            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout_seconds)

            if thread.is_alive():
                # Thread is still running - timeout occurred
                raise RegexTimeout(f"Regex operation timed out after {timeout_seconds}s")

            if exception[0]:
                raise exception[0]

            return result[0]

        return wrapper
    return decorator


@with_timeout(timeout_seconds=2)
def safe_regex_sub(pattern: str, repl: str, text: str, count: int = 1) -> str:
    """
    Safely perform regex substitution with timeout protection.

    Args:
        pattern: Regex pattern
        repl: Replacement string (can use \\1, \\2 for backreferences)
        text: Text to search in
        count: Number of replacements (0 = all, -1 = all)

    Returns:
        Modified text

    Raises:
        RegexTimeout: If regex takes too long
        re.error: If pattern is invalid
    """
    # Convert count=-1 to count=0 (re.sub uses 0 for "all")
    if count == -1:
        count = 0

    return re.sub(pattern, repl, text, count=count)


def _get_value_at_path(data: Dict[str, Any], path: str) -> Any:
    """
    Get value at JSON Pointer path.

    Args:
        data: Dict to traverse
        path: JSON Pointer path like "/field" or "/nested/field"

    Returns:
        Value at path

    Raises:
        KeyError: If path doesn't exist
        ValueError: If path is invalid
    """
    if not path.startswith('/'):
        raise ValueError(f"Path must start with '/': {path}")

    if path == '/':
        return data

    parts = path[1:].split('/')
    current = data

    for part in parts:
        # Unescape JSON Pointer special characters
        part = part.replace('~1', '/').replace('~0', '~')

        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as e:
                raise KeyError(f"Invalid array index in path {path}: {part}")
        elif isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Path not found: {path} (missing key: {part})")
            current = current[part]
        else:
            raise KeyError(f"Cannot traverse path {path} - {part} is not dict/list")

    return current


def _set_value_at_path(data: Dict[str, Any], path: str, value: Any) -> None:
    """
    Set value at JSON Pointer path (modifies data in place).

    Args:
        data: Dict to modify
        path: JSON Pointer path
        value: New value

    Raises:
        KeyError: If path doesn't exist
        ValueError: If path is invalid
    """
    if not path.startswith('/'):
        raise ValueError(f"Path must start with '/': {path}")

    if path == '/':
        raise ValueError("Cannot replace root object")

    parts = path[1:].split('/')
    current = data

    # Navigate to parent
    for part in parts[:-1]:
        part = part.replace('~1', '/').replace('~0', '~')

        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as e:
                raise KeyError(f"Invalid array index in path {path}: {part}")
        elif isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Path not found: {path} (missing key: {part})")
            current = current[part]
        else:
            raise KeyError(f"Cannot traverse path {path}")

    # Set final value
    final_key = parts[-1].replace('~1', '/').replace('~0', '~')

    if isinstance(current, list):
        try:
            current[int(final_key)] = value
        except (ValueError, IndexError) as e:
            raise KeyError(f"Invalid array index: {final_key}")
    elif isinstance(current, dict):
        current[final_key] = value
    else:
        raise KeyError(f"Cannot set value on non-dict/list at {path}")


def apply_text_replace(
    data: Dict[str, Any],
    path: str,
    match: str,
    value: str,
    regex: bool = False,
    count: int = 1
) -> None:
    """
    Apply text_replace operation to modify a string field.

    Supports:
    - Simple string replacement
    - Regex replacement with backreferences
    - Delete (value = "")
    - Insert before (value + match)
    - Insert after (match + value)

    Args:
        data: Dict to modify (modified in place)
        path: JSON Pointer to string field
        match: String or regex pattern to find
        value: Replacement text (empty string deletes match)
        regex: If True, match is regex and value can use \\1 backreferences
        count: Number of matches to replace (1 = first, -1 = all)

    Raises:
        KeyError: If path doesn't exist
        ValueError: If field is not a string or match not found
        RegexTimeout: If regex takes too long
    """
    # Get current value
    current = _get_value_at_path(data, path)

    if not isinstance(current, str):
        raise ValueError(f"Path {path} is not a string field (type: {type(current).__name__})")

    if regex:
        # Regex mode
        try:
            # First check if pattern matches at all
            if not re.search(match, current):
                raise ValueError(f"Regex pattern '{match}' not found in field {path}")

            # Apply replacement with timeout protection
            new_value = safe_regex_sub(match, value, current, count=count)

        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{match}': {e}")
        except RegexTimeout as e:
            raise ValueError(f"Regex pattern '{match}' timed out (possible catastrophic backtracking)")
    else:
        # Literal string mode
        if match not in current:
            raise ValueError(f"String '{match}' not found in field {path}")

        # Check uniqueness when count=1
        if count == 1 and current.count(match) > 1:
            raise ValueError(
                f"String '{match}' appears {current.count(match)} times in {path}. "
                f"Use count=-1 to replace all, or make match more specific."
            )

        # Perform replacement
        if count == -1:
            # Replace all
            new_value = current.replace(match, value)
        else:
            # Replace first N occurrences
            new_value = current.replace(match, value, count)

    # Set modified value
    _set_value_at_path(data, path, new_value)

    logger.debug(f"text_replace: {path} ({len(current)} → {len(new_value)} chars)")


def apply_text_extend(
    data: Dict[str, Any],
    path: str,
    value: str,
    position: str = "end"
) -> None:
    """
    Apply text_extend operation to append/prepend to a string field.

    Args:
        data: Dict to modify (modified in place)
        path: JSON Pointer to string field
        value: Text to add
        position: "end" (default) or "start"

    Raises:
        KeyError: If path doesn't exist
        ValueError: If field is not a string or position invalid
    """
    # Get current value
    current = _get_value_at_path(data, path)

    if not isinstance(current, str):
        raise ValueError(f"Path {path} is not a string field (type: {type(current).__name__})")

    # Apply extension
    if position == "end":
        new_value = current + value
    elif position == "start":
        new_value = value + current
    else:
        raise ValueError(f"Invalid position '{position}' (must be 'start' or 'end')")

    # Set modified value
    _set_value_at_path(data, path, new_value)

    logger.debug(f"text_extend: {path} at {position} (+{len(value)} chars)")


def apply_text_operations(
    data: Dict[str, Any],
    operations: List[Dict[str, Any]]
) -> TextOpResult:
    """
    Apply a sequence of text operations to data.

    Text operations are applied BEFORE standard JSON Patch operations.
    Operations are processed sequentially - each operation sees the
    result of previous operations.

    Args:
        data: Dict to modify (will be modified in place)
        operations: List of text operation dicts

    Returns:
        TextOpResult with success status and modified data

    Example:
        >>> ops = [
        ...     {"op": "text_replace", "path": "/report", "match": "Draft", "value": "Final"},
        ...     {"op": "text_extend", "path": "/report", "value": "\\n\\nEnd of report"}
        ... ]
        >>> result = apply_text_operations(data, ops)
        >>> if result.success:
        ...     use_data(result.modified_data)
    """
    if not operations:
        return TextOpResult(
            success=True,
            modified_data=data,
            operations_applied=0
        )

    try:
        applied_count = 0

        for i, op in enumerate(operations):
            op_type = op.get('op')

            if op_type == 'text_replace':
                # Required fields
                path = op.get('path')
                match = op.get('match')
                value = op.get('value')

                if not path or match is None or value is None:
                    raise ValueError(
                        f"text_replace requires 'path', 'match', and 'value' "
                        f"(op #{i+1})"
                    )

                # Optional fields
                regex = op.get('regex', False)
                count = op.get('count', 1)

                apply_text_replace(data, path, match, value, regex, count)
                applied_count += 1

            elif op_type == 'text_extend':
                # Required fields
                path = op.get('path')
                value = op.get('value')

                if not path or value is None:
                    raise ValueError(
                        f"text_extend requires 'path' and 'value' (op #{i+1})"
                    )

                # Optional fields
                position = op.get('position', 'end')

                apply_text_extend(data, path, value, position)
                applied_count += 1

            else:
                # Not a text operation - skip it (will be handled by JSON Patch)
                logger.debug(f"Skipping non-text operation: {op_type}")
                continue

        logger.info(f"✅ Applied {applied_count} text operations successfully")

        return TextOpResult(
            success=True,
            modified_data=data,
            operations_applied=applied_count
        )

    except Exception as e:
        logger.error(f"❌ Text operation failed: {e}")
        return TextOpResult(
            success=False,
            error=str(e),
            operations_applied=0
        )


def get_text_ops_schema_extension() -> Dict[str, Any]:
    """
    Get JSON schema extension for text operations.

    This extends the standard JSON Patch operation enum to include
    text_replace and text_extend.

    Returns:
        Schema properties to merge into operation items
    """
    return {
        "op": {
            "type": "string",
            "enum": [
                # Standard JSON Patch operations
                "add", "remove", "replace", "test", "move", "copy",
                # Extended text operations
                "text_replace", "text_extend"
            ],
            "description": (
                "Operation type:\n\n"
                "**Standard JSON Patch (RFC 6902):**\n"
                "- 'replace': Change entire field value\n"
                "- 'add': Add new field or array element\n"
                "- 'remove': Delete field or array element\n"
                "- 'test': Verify expected value (safety check)\n"
                "- 'move': Move value from one path to another\n"
                "- 'copy': Copy value from one path to another\n\n"
                "**Extended Text Operations:**\n"
                "- 'text_replace': Find and replace within string field (supports regex, insert, delete)\n"
                "- 'text_extend': Append or prepend to string field"
            )
        },
        # text_replace fields
        "match": {
            "type": "string",
            "description": (
                "For text_replace: String or regex pattern to find.\n"
                "- Literal mode (default): Exact string to match\n"
                "- Regex mode: Pattern like '\\d{4}-\\d{2}-\\d{2}' for dates"
            )
        },
        "regex": {
            "type": "boolean",
            "description": (
                "For text_replace: If true, 'match' is a regex pattern and 'value' can use \\1 backreferences.\n"
                "Default: false (safer - use literal string matching)"
            )
        },
        "count": {
            "type": "integer",
            "description": (
                "For text_replace: Number of occurrences to replace.\n"
                "- 1 (default): Replace first match only, error if multiple matches\n"
                "- -1: Replace all occurrences\n"
                "- N: Replace first N matches"
            )
        },
        "position": {
            "type": "string",
            "enum": ["start", "end"],
            "description": (
                "For text_extend: Where to add text.\n"
                "- 'end' (default): Append to end of string\n"
                "- 'start': Prepend to beginning of string"
            )
        }
    }


def get_text_ops_examples() -> List[Dict[str, str]]:
    """
    Get example text operations for documentation/prompts.

    Returns:
        List of example operations with descriptions
    """
    return [
        {
            "description": "Replace specific text in a field",
            "operation": {
                "op": "text_replace",
                "path": "/report",
                "match": "| Alice | 30 |",
                "value": "| Alice | 31 |"
            }
        },
        {
            "description": "Delete text (replace with empty string)",
            "operation": {
                "op": "text_replace",
                "path": "/report",
                "match": "| Bob | 25 |\\n",
                "value": ""
            }
        },
        {
            "description": "Insert after existing text",
            "operation": {
                "op": "text_replace",
                "path": "/report",
                "match": "| Bob | 25 |",
                "value": "| Bob | 25 |\\n| Charlie | 35 |"
            }
        },
        {
            "description": "Insert before existing text",
            "operation": {
                "op": "text_replace",
                "path": "/report",
                "match": "## Conclusion",
                "value": "## New Section\\nContent\\n\\n## Conclusion"
            }
        },
        {
            "description": "Regex replacement with backreferences",
            "operation": {
                "op": "text_replace",
                "path": "/report",
                "match": "(\\d{4})-(\\d{2})-(\\d{2})",
                "value": "\\2/\\3/\\1",
                "regex": True,
                "count": -1
            }
        },
        {
            "description": "Append to end of field",
            "operation": {
                "op": "text_extend",
                "path": "/report",
                "value": "\\n\\n| New | Row |"
            }
        },
        {
            "description": "Prepend to beginning of field",
            "operation": {
                "op": "text_extend",
                "path": "/notes",
                "value": "URGENT: ",
                "position": "start"
            }
        }
    ]


# Export main functions
__all__ = [
    'apply_text_operations',
    'apply_text_replace',
    'apply_text_extend',
    'get_text_ops_schema_extension',
    'get_text_ops_examples',
    'TextOpResult',
    'RegexTimeout',
    'TEXT_OPS_VERSION'
]
