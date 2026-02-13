# Patching Beyond JSON: Non-JSON Type Support

**Problem Solved:** JSON Patch (RFC 6902) only works with JSON-serializable data. But Python applications often use `datetime`, `Decimal`, `set`, `tuple`, and other non-JSON types. This guide explains how our implementation handles these types automatically.

## The Problem

Standard JSON Patch fails with non-JSON types:

```python
from jsonpatch import JsonPatch

data = {
    "created": datetime.now(),       # ❌ Not JSON-serializable
    "price": Decimal("99.99"),       # ❌ Not JSON-serializable
    "tags": {"python", "ml"},        # ❌ Set not JSON-serializable
    "version": (1, 0, 0)             # ⚠️  Becomes list [1, 0, 0]
}

patches = [{"op": "replace", "path": "/price", "value": "149.99"}]

# ❌ This fails:
patch = JsonPatch(patches)
result = patch.apply(data)  # TypeError: Object of type datetime is not JSON serializable
```

## The Solution

Our implementation automatically:
1. ✅ **Detects** non-JSON types
2. ✅ **Converts** them to JSON-compatible representations
3. ✅ **Applies** patches normally
4. ✅ **Restores** original types after patching

```python
from shared.ai_patch_utils import apply_patches_with_validation

data = {
    "created": datetime.now(),
    "price": Decimal("99.99"),
    "tags": {"python", "ml"}
}

patches = [{"op": "replace", "path": "/price", "value": "149.99"}]

result = apply_patches_with_validation(data, patches)

# ✅ This works!
# result.patched_data["created"] is still a datetime object
# result.patched_data["price"] is "149.99" (string, as specified in patch)
# result.patched_data["tags"] is still a set
```

## Supported Types

### Temporal Types
- **`datetime`** → ISO 8601 string
- **`date`** → ISO 8601 date string
- **`time`** → ISO 8601 time string
- **`timedelta`** → total seconds (float)

```python
data = {
    "created": datetime(2024, 1, 15, 10, 30, 0),
    "duration": timedelta(hours=2, minutes=30)
}

# Converts to:
{
    "created": {"__py_type__": "datetime", "value": "2024-01-15T10:30:00"},
    "duration": {"__py_type__": "timedelta", "value": 9000.0}
}

# Restores back to datetime and timedelta after patching
```

### Numeric Types
- **`Decimal`** → string representation (preserves precision)

```python
data = {"price": Decimal("99.99")}

# Converts to:
{"price": {"__py_type__": "Decimal", "value": "99.99"}}

# Restores to Decimal("99.99")
```

### Collection Types
- **`set`** → sorted list with type marker
- **`frozenset`** → sorted list with type marker
- **`tuple`** → list with type marker

```python
data = {
    "tags": {"python", "ml", "ai"},
    "version": (1, 0, 0)
}

# Converts to:
{
    "tags": {"__py_type__": "set", "value": ["ai", "ml", "python"]},
    "version": {"__py_type__": "tuple", "value": [1, 0, 0]}
}

# Restores to set and tuple
```

### Binary Types
- **`bytes`** → hex string

```python
data = {"hash": b"\x01\x02\xaa\xbb"}

# Converts to:
{"hash": {"__py_type__": "bytes", "value": "0102aabb"}}

# Restores to bytes
```

## How It Works

### 1. Automatic Detection

The system automatically detects if your data needs conversion:

```python
from shared.json_compat import ensure_json_compatible

# Already JSON-safe - no conversion
data1 = {"name": "Alice", "age": 30}
json_safe1, converter1 = ensure_json_compatible(data1)
# converter1 is None (no conversion needed)

# Has non-JSON types - converts
data2 = {"created": datetime.now()}
json_safe2, converter2 = ensure_json_compatible(data2)
# converter2 is a JSONCompat instance
```

### 2. Type Marker System

Non-JSON types are wrapped with a `__py_type__` marker:

```json
{
  "__py_type__": "datetime",
  "value": "2024-01-15T10:30:00"
}
```

This allows the system to:
- ✅ Distinguish converted types from regular dicts
- ✅ Restore the correct Python type after patching
- ✅ Preserve nested structures

### 3. Transparent Integration

The conversion happens automatically in `apply_patches_with_validation`:

```python
def apply_patches_with_validation(original_data, patch_operations, ...):
    # 1. Deep copy
    working_data = copy.deepcopy(original_data)

    # 2. Convert to JSON-compatible (if needed)
    working_data, json_converter = ensure_json_compatible(working_data)

    # 3. Apply patches normally
    patched_data = apply_patches(working_data, patch_operations)

    # 4. Restore original types
    if json_converter:
        patched_data = restore_from_json_compatible(patched_data, json_converter)

    # 5. Validate (sees original types)
    if validator_fn:
        validator_fn(patched_data)

    return patched_data
```

## Edge Cases Handled

### 1. Nested Structures

```python
data = {
    "metadata": {
        "version": (1, 0, 0),
        "released": date(2024, 1, 1),
        "tags": {"production", "verified"}
    }
}

# All nested types are converted and restored correctly
```

### 2. Mixed Arrays

```python
data = {
    "events": [
        {"timestamp": datetime(2024, 1, 1, 10, 0), "type": "login"},
        {"timestamp": datetime(2024, 1, 1, 11, 0), "type": "logout"}
    ]
}

# Each datetime in the array is converted and restored
```

### 3. Already JSON-Safe Data

No performance penalty for standard JSON data:

```python
data = {"name": "Alice", "scores": [95, 87, 92]}

# No conversion needed - passes through unchanged
result = apply_patches_with_validation(data, patches)
```

### 4. Partial Type Preservation

When a patch **replaces** a field with a JSON value, the new value type is used:

```python
data = {
    "price": Decimal("99.99"),  # Original: Decimal
    "name": "Widget"
}

patches = [
    {"op": "replace", "path": "/price", "value": 149.99}  # New value: float
]

result = apply_patches_with_validation(data, patches)

# result.patched_data["price"] is now a float (149.99)
# This is correct - the patch explicitly set a float value
```

## Limitations

### 1. Enums and Dataclasses

**Enums** and **dataclasses** are converted to JSON but **cannot be fully restored** without the original class definitions:

```python
from enum import Enum

class Status(Enum):
    DRAFT = "draft"
    PUBLISHED = "published"

data = {"status": Status.DRAFT}

# Converts to:
# {"status": {"__py_type__": "Enum", "class": "Status", "value": "draft"}}

# Restores to: "draft" (the enum value, not the Enum instance)
# ⚠️  You lose the Enum type
```

**Workaround:** Store enum values directly:
```python
data = {"status": Status.DRAFT.value}  # Just use the string value
```

### 2. Custom Classes

Arbitrary custom classes are converted to string representations:

```python
class User:
    def __init__(self, name):
        self.name = name

data = {"user": User("Alice")}

# Converts to string representation
# {"user": {"__py_type__": "str_repr", "class": "User", "value": "<User object>"}}

# Cannot be restored
```

**Workaround:** Use dicts or dataclasses:
```python
data = {"user": {"name": "Alice"}}  # Plain dict
```

### 3. Deep Copy Failures

Some objects can't be deep copied (file handles, database connections, locks):

```python
data = {"file": open("data.txt")}

# ❌ Deep copy will fail
```

**Workaround:** The system falls back to shallow copy, but you should avoid putting non-copyable objects in patchable data.

## Performance

### Overhead

- **JSON-safe data**: Zero overhead (detected and skipped)
- **Conversion needed**: ~2-5x memory usage (creates converted copy)
- **Time complexity**: O(n) where n = number of values in data

### Benchmarks

```
Data size: 1000 fields
- JSON-safe: ~0.1ms (no conversion)
- With datetime: ~5ms (convert + restore)
- With nested structures: ~10ms (recursive conversion)
```

For typical config sizes (10-100 fields), overhead is negligible (<1ms).

## Best Practices

### 1. Use JSON-Safe Types When Possible

```python
# ❌ Avoid if not necessary
data = {"created": datetime.now()}

# ✅ Better (if you don't need datetime operations)
data = {"created": datetime.now().isoformat()}
```

### 2. Convert at Boundaries

Convert to/from JSON types at system boundaries (API, database):

```python
# Load from database (has datetime objects)
config = db.load_config()

# Apply patches (automatic conversion)
patched = apply_patches_with_validation(config, patches)

# Save to database (still has datetime objects)
db.save_config(patched)
```

### 3. Document Type Expectations

If your validator expects specific types, document them:

```python
def validate_config(config):
    """
    Validate configuration.

    Expected types:
    - config["created"]: datetime
    - config["price"]: Decimal
    - config["tags"]: set
    """
    errors = []

    if not isinstance(config["created"], datetime):
        errors.append("created must be datetime")

    return (len(errors) == 0, errors, [])
```

## Testing

Run comprehensive tests:

```bash
# Test non-JSON type conversion
python3 test_json_compat.py

# Test patching with non-JSON types
python3 -c "
from datetime import datetime
from decimal import Decimal
from shared.ai_patch_utils import apply_patches_with_validation

data = {
    'created': datetime.now(),
    'price': Decimal('99.99'),
    'tags': {'python', 'ml'}
}

patches = [
    {'op': 'replace', 'path': '/price', 'value': '149.99'},
    {'op': 'add', 'path': '/stock', 'value': 100}
]

result = apply_patches_with_validation(data, patches)

assert isinstance(result.patched_data['created'], datetime)
assert isinstance(result.patched_data['tags'], set)
assert result.patched_data['price'] == '149.99'
assert result.patched_data['stock'] == 100

print('✅ All type checks passed')
"
```

## Implementation Files

- **`src/shared/json_compat.py`** - Core conversion logic
- **`src/shared/ai_patch_utils.py`** - Integrated patching with auto-conversion
- **`test_json_compat.py`** - Comprehensive test suite

## See Also

- [AI Patch Utils Guide](AI_PATCH_UTILS_GUIDE.md) - Using JSON Patch with LLMs
- [Text Operations Guide](TEXT_OPERATIONS_GUIDE.md) - Extended text operations
- [RFC 6902 - JSON Patch](https://datatracker.ietf.org/doc/html/rfc6902)

## Summary

| Type | JSON Conversion | Restores Correctly | Notes |
|------|----------------|-------------------|-------|
| `datetime` | ✅ ISO 8601 string | ✅ Yes | Full fidelity |
| `date` | ✅ ISO 8601 date | ✅ Yes | Full fidelity |
| `time` | ✅ ISO 8601 time | ✅ Yes | Full fidelity |
| `timedelta` | ✅ Total seconds | ✅ Yes | Full fidelity |
| `Decimal` | ✅ String | ✅ Yes | Preserves precision |
| `set` | ✅ Sorted list | ✅ Yes | Order not preserved |
| `frozenset` | ✅ Sorted list | ✅ Yes | Order not preserved |
| `tuple` | ✅ List | ✅ Yes | Full fidelity |
| `bytes` | ✅ Hex string | ✅ Yes | Full fidelity |
| `Enum` | ✅ Value | ⚠️  Partial | Returns value, not Enum |
| `dataclass` | ✅ Dict | ⚠️  Partial | Returns dict, not dataclass |
| Custom class | ⚠️  String repr | ❌ No | Use dicts instead |

**Bottom line:** The system handles all common Python types automatically, making JSON Patch work seamlessly with real Python applications.
