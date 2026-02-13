#!/usr/bin/env python3
"""
Patch Path Validator

Validates that JSON Patch operations match the actual structure of the target data.
Prevents errors when patches assume a structure that doesn't exist (e.g., trying to
patch /answer/field1 when answer is just a string, not an object).

Example:
    from shared.patch_validator import validate_patches, PatchValidationError

    data = {"answer": "Just a string"}
    patches = [{"op": "replace", "path": "/answer/field1", "value": "x"}]

    try:
        validate_patches(data, patches)
    except PatchValidationError as e:
        print(f"Invalid patch: {e}")
        # Output: "Invalid patch: Path /answer/field1 expects object at /answer, but found str"
"""

import logging
from typing import Any, Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class PatchValidationError(Exception):
    """Raised when a patch operation is invalid for the target data structure"""
    def __init__(self, message: str, patch_index: int = None, patch_op: Dict = None):
        super().__init__(message)
        self.patch_index = patch_index
        self.patch_op = patch_op


def _parse_json_pointer(path: str) -> List[str]:
    """
    Parse JSON Pointer (RFC 6901) into components.

    Args:
        path: JSON Pointer like "/field" or "/nested/field/0"

    Returns:
        List of path components

    Example:
        >>> _parse_json_pointer("/answer/field1")
        ['answer', 'field1']
    """
    if not path:
        return []

    if path == "/":
        return []

    # Remove leading slash and split
    if path.startswith('/'):
        path = path[1:]

    components = path.split('/')

    # Unescape JSON Pointer special chars
    return [comp.replace('~1', '/').replace('~0', '~') for comp in components]


def _get_value_at_path(data: Any, path_components: List[str]) -> Tuple[Any, bool]:
    """
    Get value at path, returning (value, exists).

    Args:
        data: Data to traverse
        path_components: Path components from _parse_json_pointer

    Returns:
        (value, exists) tuple
    """
    current = data

    for component in path_components:
        if isinstance(current, dict):
            if component not in current:
                return None, False
            current = current[component]
        elif isinstance(current, list):
            try:
                index = int(component)
                if index < 0 or index >= len(current):
                    return None, False
                current = current[index]
            except (ValueError, IndexError):
                return None, False
        else:
            # Can't traverse into non-dict/list
            return None, False

    return current, True


def _get_parent_path_and_key(path_components: List[str]) -> Tuple[List[str], str]:
    """
    Split path into parent path and final key.

    Args:
        path_components: Path components

    Returns:
        (parent_components, final_key) tuple

    Example:
        >>> _get_parent_path_and_key(['answer', 'field1', 'subfield'])
        (['answer', 'field1'], 'subfield')
    """
    if not path_components:
        return [], ""

    return path_components[:-1], path_components[-1]


def validate_patch_operation(data: Any, patch: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate a single patch operation against data structure.

    Args:
        data: Target data
        patch: Single patch operation dict

    Returns:
        (is_valid, error_message) tuple

    Example:
        >>> data = {"answer": "text"}
        >>> patch = {"op": "replace", "path": "/answer/field1", "value": "x"}
        >>> validate_patch_operation(data, patch)
        (False, "Path /answer/field1 expects object at /answer, but found str")
    """
    op = patch.get('op')
    path = patch.get('path')

    if not op:
        return False, "Patch missing 'op' field"

    if not path and path != "":
        return False, "Patch missing 'path' field"

    # Parse path
    path_components = _parse_json_pointer(path)

    # Skip text operations (handled separately)
    if op in ('text_replace', 'text_extend'):
        # Just check that path exists and is a string
        if path_components:
            value, exists = _get_value_at_path(data, path_components)
            if not exists:
                return False, f"Path {path} does not exist in data"
            if not isinstance(value, str):
                return False, f"Text operation on {path} requires string field, but found {type(value).__name__}"
        return True, None

    # Validate based on operation type
    if op == 'add':
        # For 'add', parent path must exist and be dict/list
        if not path_components:
            return False, "Cannot add to root"

        parent_components, final_key = _get_parent_path_and_key(path_components)

        if parent_components:
            parent, exists = _get_value_at_path(data, parent_components)
            if not exists:
                return False, f"Parent path /{'/'.join(parent_components)} does not exist"

            if not isinstance(parent, (dict, list)):
                return False, f"Cannot add to /{'/'.join(parent_components)} - not a dict or list (found {type(parent).__name__})"

            # For list, check if index is valid
            if isinstance(parent, list):
                try:
                    index = int(final_key)
                    # 'add' allows index == len(list) to append
                    if index < 0 or index > len(parent):
                        return False, f"Array index {index} out of range for path /{'/'.join(parent_components)}"
                except ValueError:
                    return False, f"Invalid array index '{final_key}' in path {path}"
        else:
            # Adding to root - data must be dict
            if not isinstance(data, dict):
                return False, f"Cannot add to root - data is {type(data).__name__}, not dict"

        return True, None

    elif op in ('remove', 'replace', 'test'):
        # Path must exist
        if not path_components:
            if op == 'remove':
                return False, "Cannot remove root"
            # For replace/test on root, allow it
            return True, None

        value, exists = _get_value_at_path(data, path_components)
        if not exists:
            return False, f"Path {path} does not exist in data"

        return True, None

    elif op in ('move', 'copy'):
        # Both 'from' and 'path' must be valid
        from_path = patch.get('from')
        if not from_path:
            return False, f"'{op}' operation missing 'from' field"

        from_components = _parse_json_pointer(from_path)
        from_value, from_exists = _get_value_at_path(data, from_components)

        if not from_exists:
            return False, f"Source path {from_path} does not exist"

        # Validate target path like 'add'
        if path_components:
            parent_components, final_key = _get_parent_path_and_key(path_components)
            if parent_components:
                parent, exists = _get_value_at_path(data, parent_components)
                if not exists:
                    return False, f"Target parent path /{'/'.join(parent_components)} does not exist"
                if not isinstance(parent, (dict, list)):
                    return False, f"Cannot {op} to /{'/'.join(parent_components)} - not a dict or list"

        return True, None

    else:
        # Unknown operation
        logger.warning(f"Unknown patch operation: {op}")
        return True, None  # Allow unknown ops (might be extended ops)


def validate_patches(
    data: Any,
    patches: List[Dict[str, Any]],
    raise_on_error: bool = True
) -> Tuple[bool, List[str]]:
    """
    Validate all patch operations against data structure.

    Args:
        data: Target data
        patches: List of patch operations
        raise_on_error: If True, raise PatchValidationError on first error

    Returns:
        (all_valid, error_messages) tuple

    Raises:
        PatchValidationError: If raise_on_error=True and validation fails

    Example:
        >>> data = {"answer": "text", "status": "draft"}
        >>> patches = [
        ...     {"op": "replace", "path": "/status", "value": "final"},
        ...     {"op": "replace", "path": "/answer/field1", "value": "x"}  # Invalid!
        ... ]
        >>> is_valid, errors = validate_patches(data, patches, raise_on_error=False)
        >>> print(errors)
        ['Patch #2: Path /answer/field1 expects object at /answer, but found str']
    """
    errors = []

    for i, patch in enumerate(patches):
        is_valid, error_msg = validate_patch_operation(data, patch)

        if not is_valid:
            full_error = f"Patch #{i+1}: {error_msg}"
            errors.append(full_error)

            if raise_on_error:
                raise PatchValidationError(full_error, patch_index=i, patch_op=patch)

    return (len(errors) == 0, errors)


def filter_invalid_patches(
    data: Any,
    patches: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """
    Filter out invalid patches, returning valid and invalid separately.

    Args:
        data: Target data
        patches: List of patch operations

    Returns:
        (valid_patches, invalid_patches, error_messages) tuple

    Example:
        >>> data = {"answer": "text", "status": "draft"}
        >>> patches = [
        ...     {"op": "replace", "path": "/status", "value": "final"},
        ...     {"op": "replace", "path": "/answer/field1", "value": "x"}
        ... ]
        >>> valid, invalid, errors = filter_invalid_patches(data, patches)
        >>> len(valid)  # 1 valid patch
        1
        >>> len(invalid)  # 1 invalid patch
        1
    """
    valid_patches = []
    invalid_patches = []
    errors = []

    for i, patch in enumerate(patches):
        is_valid, error_msg = validate_patch_operation(data, patch)

        if is_valid:
            valid_patches.append(patch)
        else:
            invalid_patches.append(patch)
            errors.append(f"Patch #{i+1}: {error_msg}")

    return valid_patches, invalid_patches, errors


def get_structure_summary(data: Any, max_depth: int = 3, current_depth: int = 0) -> str:
    """
    Generate a human-readable summary of data structure.

    Useful for error messages to show what the actual structure is.

    Args:
        data: Data to summarize
        max_depth: Maximum nesting depth to show
        current_depth: Current depth (for recursion)

    Returns:
        String summary

    Example:
        >>> data = {"answer": "text", "metadata": {"version": 1, "tags": ["a", "b"]}}
        >>> print(get_structure_summary(data))
        {
          "answer": <str>,
          "metadata": {
            "version": <int>,
            "tags": <list[2]>
          }
        }
    """
    indent = "  " * current_depth

    if current_depth >= max_depth:
        return f"<{type(data).__name__}>"

    if isinstance(data, dict):
        if not data:
            return "{}"

        lines = ["{"]
        for key, value in list(data.items())[:10]:  # Show max 10 keys
            value_summary = get_structure_summary(value, max_depth, current_depth + 1)
            lines.append(f'{indent}  "{key}": {value_summary},')

        if len(data) > 10:
            lines.append(f'{indent}  ... {len(data) - 10} more keys')

        lines.append(f"{indent}}}")
        return "\n".join(lines)

    elif isinstance(data, list):
        if not data:
            return "[]"

        if len(data) <= 3:
            items = [get_structure_summary(item, max_depth, current_depth + 1) for item in data]
            return "[" + ", ".join(items) + "]"
        else:
            first_item = get_structure_summary(data[0], max_depth, current_depth + 1)
            return f"<list[{len(data)}] of {first_item}>"

    else:
        return f"<{type(data).__name__}>"


# Export main functions
__all__ = [
    'validate_patches',
    'validate_patch_operation',
    'filter_invalid_patches',
    'get_structure_summary',
    'PatchValidationError'
]
