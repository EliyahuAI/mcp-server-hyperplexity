#!/usr/bin/env python3
"""
JSON Compatibility Layer for Patch Operations

Handles conversion of non-JSON-serializable Python types to/from JSON-compatible
representations, enabling JSON Patch operations on Python objects with datetimes,
Decimals, sets, tuples, and other special types.

Example:
    from shared.json_compat import JSONCompat

    # Data with non-JSON types
    data = {
        "created": datetime.now(),
        "amount": Decimal("123.45"),
        "tags": {"python", "ml"},
        "coords": (1, 2, 3)
    }

    # Convert to JSON-compatible form
    compat = JSONCompat(data)
    json_safe = compat.to_json_compatible()

    # Apply patches...
    # patched = apply_patches(json_safe, patches)

    # Restore original types
    restored = compat.from_json_compatible(patched)
"""

import json
import logging
from typing import Any, Dict, List, Set, Tuple, Optional
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from enum import Enum
from dataclasses import is_dataclass, asdict

logger = logging.getLogger(__name__)


class JSONCompat:
    """
    Bidirectional converter for Python objects ↔ JSON-compatible dicts.

    Handles common non-JSON-serializable types:
    - datetime, date, time, timedelta
    - Decimal
    - set, frozenset
    - tuple
    - Enum
    - dataclasses
    - bytes
    """

    # Type markers for restoration
    TYPE_MARKER = "__py_type__"

    def __init__(self, original_data: Any = None):
        """
        Initialize JSON compatibility converter.

        Args:
            original_data: Optional reference data for type inference
        """
        self.original_data = original_data
        self.type_map: Dict[str, str] = {}  # Path -> original type

    def to_json_compatible(self, data: Any, path: str = "") -> Any:
        """
        Convert Python object to JSON-compatible representation.

        Args:
            data: Python object to convert
            path: Current JSON pointer path (for tracking)

        Returns:
            JSON-compatible representation
        """
        # None, bool, int, float, str - already JSON compatible
        if data is None or isinstance(data, (bool, int, float, str)):
            return data

        # datetime types
        if isinstance(data, datetime):
            self.type_map[path] = "datetime"
            return {
                self.TYPE_MARKER: "datetime",
                "value": data.isoformat()
            }
        elif isinstance(data, date):
            self.type_map[path] = "date"
            return {
                self.TYPE_MARKER: "date",
                "value": data.isoformat()
            }
        elif isinstance(data, time):
            self.type_map[path] = "time"
            return {
                self.TYPE_MARKER: "time",
                "value": data.isoformat()
            }
        elif isinstance(data, timedelta):
            self.type_map[path] = "timedelta"
            return {
                self.TYPE_MARKER: "timedelta",
                "value": data.total_seconds()
            }

        # Decimal
        elif isinstance(data, Decimal):
            self.type_map[path] = "Decimal"
            return {
                self.TYPE_MARKER: "Decimal",
                "value": str(data)
            }

        # Set/frozenset
        elif isinstance(data, (set, frozenset)):
            type_name = "frozenset" if isinstance(data, frozenset) else "set"
            self.type_map[path] = type_name
            return {
                self.TYPE_MARKER: type_name,
                "value": [self.to_json_compatible(item, f"{path}[{i}]")
                         for i, item in enumerate(sorted(data, key=str))]
            }

        # Tuple
        elif isinstance(data, tuple):
            self.type_map[path] = "tuple"
            return {
                self.TYPE_MARKER: "tuple",
                "value": [self.to_json_compatible(item, f"{path}[{i}]")
                         for i, item in enumerate(data)]
            }

        # Enum
        elif isinstance(data, Enum):
            self.type_map[path] = f"Enum:{data.__class__.__name__}"
            return {
                self.TYPE_MARKER: "Enum",
                "class": data.__class__.__name__,
                "value": data.value
            }

        # Dataclass
        elif is_dataclass(data) and not isinstance(data, type):
            self.type_map[path] = f"dataclass:{data.__class__.__name__}"
            dict_data = asdict(data)
            return {
                self.TYPE_MARKER: "dataclass",
                "class": data.__class__.__name__,
                "value": self.to_json_compatible(dict_data, path)
            }

        # Bytes
        elif isinstance(data, bytes):
            self.type_map[path] = "bytes"
            return {
                self.TYPE_MARKER: "bytes",
                "value": data.hex()
            }

        # Dict
        elif isinstance(data, dict):
            result = {}
            for key, value in data.items():
                # JSON keys must be strings
                str_key = str(key) if not isinstance(key, str) else key
                new_path = f"{path}/{str_key}" if path else f"/{str_key}"
                result[str_key] = self.to_json_compatible(value, new_path)
            return result

        # List
        elif isinstance(data, list):
            return [
                self.to_json_compatible(item, f"{path}/{i}")
                for i, item in enumerate(data)
            ]

        # Unknown type - try JSON serialization
        else:
            try:
                json.dumps(data)  # Test if JSON-serializable
                logger.debug(f"Type {type(data).__name__} at {path} is JSON-serializable")
                return data
            except (TypeError, ValueError):
                logger.warning(
                    f"Cannot convert type {type(data).__name__} at {path} to JSON. "
                    f"Converting to string representation."
                )
                self.type_map[path] = f"str_repr:{type(data).__name__}"
                return {
                    self.TYPE_MARKER: "str_repr",
                    "class": type(data).__name__,
                    "value": str(data)
                }

    def from_json_compatible(self, data: Any, path: str = "") -> Any:
        """
        Restore Python object from JSON-compatible representation.

        Args:
            data: JSON-compatible data to restore
            path: Current JSON pointer path

        Returns:
            Restored Python object with original types
        """
        # None, bool, int, float, str - pass through
        if data is None or isinstance(data, (bool, int, float, str)):
            return data

        # Check for type marker
        if isinstance(data, dict) and self.TYPE_MARKER in data:
            type_name = data[self.TYPE_MARKER]
            value = data["value"]

            if type_name == "datetime":
                return datetime.fromisoformat(value)
            elif type_name == "date":
                return date.fromisoformat(value)
            elif type_name == "time":
                return time.fromisoformat(value)
            elif type_name == "timedelta":
                return timedelta(seconds=value)
            elif type_name == "Decimal":
                return Decimal(value)
            elif type_name == "set":
                return set(self.from_json_compatible(item, f"{path}[{i}]")
                          for i, item in enumerate(value))
            elif type_name == "frozenset":
                return frozenset(self.from_json_compatible(item, f"{path}[{i}]")
                                for i, item in enumerate(value))
            elif type_name == "tuple":
                return tuple(self.from_json_compatible(item, f"{path}[{i}]")
                           for i, item in enumerate(value))
            elif type_name == "bytes":
                return bytes.fromhex(value)
            elif type_name == "Enum":
                # Can't restore without the actual Enum class
                logger.warning(f"Cannot restore Enum {data.get('class')} - returning value")
                return value
            elif type_name == "dataclass":
                # Can't restore without the actual dataclass
                logger.warning(f"Cannot restore dataclass {data.get('class')} - returning dict")
                return self.from_json_compatible(value, path)
            elif type_name == "str_repr":
                # Can't restore - was converted to string
                logger.warning(f"Cannot restore {data.get('class')} from string representation")
                return value
            else:
                logger.warning(f"Unknown type marker: {type_name}")
                return data

        # Regular dict
        elif isinstance(data, dict):
            return {
                key: self.from_json_compatible(value, f"{path}/{key}" if path else f"/{key}")
                for key, value in data.items()
            }

        # List
        elif isinstance(data, list):
            return [
                self.from_json_compatible(item, f"{path}/{i}")
                for i, item in enumerate(data)
            ]

        # Unknown
        else:
            return data

    def is_json_safe(self, data: Any) -> bool:
        """
        Check if data is already JSON-safe (no conversion needed).

        Args:
            data: Data to check

        Returns:
            True if data can be JSON serialized without conversion
        """
        try:
            json.dumps(data)
            return True
        except (TypeError, ValueError):
            return False


def ensure_json_compatible(data: Any) -> Tuple[Any, Optional[JSONCompat]]:
    """
    Ensure data is JSON-compatible, converting if necessary.

    Args:
        data: Data to make JSON-compatible

    Returns:
        Tuple of (json_safe_data, converter_or_none)
        If converter is None, data was already JSON-safe
    """
    compat = JSONCompat(data)

    if compat.is_json_safe(data):
        logger.debug("Data is already JSON-safe, no conversion needed")
        return data, None

    logger.info("Converting data to JSON-compatible format")
    json_safe = compat.to_json_compatible(data)
    return json_safe, compat


def restore_from_json_compatible(
    data: Any,
    converter: Optional[JSONCompat]
) -> Any:
    """
    Restore data from JSON-compatible format if it was converted.

    Args:
        data: JSON-compatible data
        converter: Converter used for original conversion (or None)

    Returns:
        Restored data with original types (or data unchanged if no converter)
    """
    if converter is None:
        return data

    logger.info("Restoring data from JSON-compatible format")
    return converter.from_json_compatible(data)


# Export main classes and functions
__all__ = [
    'JSONCompat',
    'ensure_json_compatible',
    'restore_from_json_compatible'
]
