# Text Operations Extension for JSON Patch

**Spec version:** 2.0

Extension to JSON Patch (RFC 6902) that enables AI-powered modifications to **portions of text fields**, not just entire field values.

## Overview

Standard JSON Patch operations (`replace`, `add`, `remove`) work on complete field values. When you have long text fields (reports, markdown documents, logs), you often want to modify just a portion of the text. The text operations extension provides:

- ✅ **Find and replace** within string fields
- ✅ **Insert before/after** specific markers
- ✅ **Delete** portions of text
- ✅ **Append/prepend** to fields
- ✅ **Regex support** (with timeout protection)
- ✅ **Safe by default** (literal matching, uniqueness checks)

## Installation

No additional dependencies required beyond `jsonpatch`:

```bash
pip install jsonpatch
```

## Quick Start

```python
from shared.ai_patch_utils import apply_patches_with_validation

data = {
    "report": "| Name | Age |\n| Alice | 30 |\n| Bob | 25 |"
}

# Mix text operations with standard JSON Patch
operations = [
    # Text operation: replace a table row
    {"op": "text_replace", "path": "/report", "match": "| Alice | 30 |", "value": "| Alice | 31 |"},

    # Text operation: append a new row
    {"op": "text_extend", "path": "/report", "value": "\n| Charlie | 35 |"},

    # Standard JSON Patch: add a new field
    {"op": "add", "path": "/version", "value": 1}
]

result = apply_patches_with_validation(data, operations)
print(result.patched_data)
```

**Output:**
```json
{
  "report": "| Name | Age |\n| Alice | 31 |\n| Bob | 25 |\n| Charlie | 35 |",
  "version": 1
}
```

## Operations

### text_replace

Find and replace text within a string field. Supports:
- Simple string replacement
- Insert before (by making value include the match at the end)
- Insert after (by making value include the match at the beginning)
- Delete (by setting value to empty string)
- Regex patterns with backreferences

**Required fields:**
- `op`: `"text_replace"`
- `path`: JSON Pointer to string field
- `match`: String or regex pattern to find
- `value`: Replacement text

**Optional fields:**
- `regex`: `true` for regex mode, `false` (default) for literal
- `count`: Number of matches to replace
  - `1` (default): Replace first match only, error if multiple exist
  - `-1`: Replace all matches
  - `N`: Replace first N matches

**Examples:**

```json
// Simple replacement
{"op": "text_replace", "path": "/report", "match": "Draft", "value": "Final"}

// Delete text (empty value)
{"op": "text_replace", "path": "/report", "match": "| Bob | 25 |", "value": ""}

// Insert after existing text
{"op": "text_replace", "path": "/report", "match": "| Bob | 25 |", "value": "| Bob | 25 |\n| Charlie | 35 |"}

// Insert before existing text
{"op": "text_replace", "path": "/report", "match": "## Conclusion", "value": "## New Section\nContent\n\n## Conclusion"}

// Regex with backreferences (convert YYYY-MM-DD to MM/DD/YYYY)
{
  "op": "text_replace",
  "path": "/dates",
  "match": "(\\d{4})-(\\d{2})-(\\d{2})",
  "value": "\\2/\\3/\\1",
  "regex": true,
  "count": -1
}

// Regex redaction (replace all emails)
{
  "op": "text_replace",
  "path": "/log",
  "match": "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b",
  "value": "[REDACTED]",
  "regex": true,
  "count": -1
}
```

### text_extend

Append or prepend text to a string field. Simpler than `text_replace` when you don't need an anchor point.

**Required fields:**
- `op`: `"text_extend"`
- `path`: JSON Pointer to string field
- `value`: Text to add

**Optional fields:**
- `position`: `"end"` (default) or `"start"`

**Examples:**

```json
// Append to end
{"op": "text_extend", "path": "/report", "value": "\n\n## Additional Notes"}

// Prepend to beginning
{"op": "text_extend", "path": "/notes", "value": "URGENT: ", "position": "start"}
```

## Rules and Safety

### 1. Literal Mode (default, safer)

When `regex: false` (or omitted):
- Match is treated as a literal string
- `count: 1` (default) requires the match to be **unique**
  - ✅ Prevents accidental multiple replacements
  - ❌ Errors if match appears 2+ times
  - Use `count: -1` to replace all occurrences

```json
// ❌ ERROR: "foo" appears 2 times
{"op": "text_replace", "path": "/text", "match": "foo", "value": "bar"}

// ✅ OK: Replace all
{"op": "text_replace", "path": "/text", "match": "foo", "value": "bar", "count": -1}

// ✅ OK: Replace first 2
{"op": "text_replace", "path": "/text", "match": "foo", "value": "bar", "count": 2}
```

### 2. Regex Mode (powerful but riskier)

When `regex: true`:
- Match is treated as a regex pattern
- Value can use backreferences like `\1`, `\2`
- **Timeout protection**: 2-second limit per operation
  - Prevents catastrophic backtracking (e.g., `(a+)+`)
  - Uses threading for cross-platform support

```json
// ✅ Safe regex
{"op": "text_replace", "path": "/text", "match": "\\d{4}", "value": "YEAR", "regex": true}

// ⚠️ Potentially slow but protected by timeout
{"op": "text_replace", "path": "/text", "match": "(a+)+", "value": "X", "regex": true}
```

### 3. Include Whitespace Explicitly

You must include surrounding whitespace/newlines in both `match` and `value`:

```json
// ❌ BAD: Doesn't include newline
{"op": "text_replace", "path": "/report", "match": "| Bob | 25 |", "value": ""}
// Result: "| Alice | 30 |\n| Charlie | 35 |" (dangling newline)

// ✅ GOOD: Includes newline
{"op": "text_replace", "path": "/report", "match": "| Bob | 25 |\n", "value": ""}
// Result: "| Alice | 30 |\n| Charlie | 35 |"
```

### 4. Operations Apply Sequentially

Each operation sees the result of previous operations:

```json
[
  {"op": "text_replace", "path": "/text", "match": "foo", "value": "bar"},
  {"op": "text_extend", "path": "/text", "value": " baz"},
  {"op": "text_replace", "path": "/text", "match": "bar baz", "value": "qux"}
]
// Step 1: "foo" → "bar"
// Step 2: "bar" → "bar baz"
// Step 3: "bar baz" → "qux"
```

### 5. Use Standard `replace` for Entire Fields

If you're replacing the **entire** field value, use standard JSON Patch `replace`:

```json
// ❌ Inefficient
{"op": "text_replace", "path": "/status", "match": "draft", "value": "published"}

// ✅ Better
{"op": "replace", "path": "/status", "value": "published"}
```

## Integration with PatchRefinementManager

Text operations work seamlessly with AI-powered refinements:

```python
from shared.ai_patch_utils import PatchRefinementManager

manager = PatchRefinementManager(
    original_data=my_config,
    validator_fn=validate_config,
    ai_client=ai_client
)

result = await manager.refine_with_patches(
    instructions="Fix the typo in the report and add a new row for Charlie (age 35)",
    fallback_to_full=True
)

# AI can now use text operations:
# [
#   {"op": "text_replace", "path": "/report", "match": "Reprot", "value": "Report"},
#   {"op": "text_extend", "path": "/report", "value": "\n| Charlie | 35 |"}
# ]
```

The schema is automatically extended to include text operations when `TEXT_OPS_AVAILABLE` is `True`.

## Common Use Cases

### 1. Markdown Document Editing

```python
data = {
    "document": """# My Report

## Section 1
Content here.

## Conclusion
End."""
}

ops = [
    {
        "op": "text_replace",
        "path": "/document",
        "match": "## Conclusion",
        "value": "## Section 2\n\nNew content.\n\n## Conclusion"
    }
]
```

### 2. Table Manipulation

```python
data = {
    "table": "| Name | Age | City |\n| Alice | 30 | NYC |\n| Bob | 25 | LA |"
}

ops = [
    # Update a cell
    {"op": "text_replace", "path": "/table", "match": "| Alice | 30 |", "value": "| Alice | 31 |"},

    # Add a row
    {"op": "text_extend", "path": "/table", "value": "\n| Charlie | 35 | SF |"}
]
```

### 3. Log Sanitization

```python
data = {
    "logs": "User alice@example.com logged in. API key: sk-abc123xyz"
}

ops = [
    # Redact emails
    {
        "op": "text_replace",
        "path": "/logs",
        "match": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "value": "[EMAIL]",
        "regex": True,
        "count": -1
    },
    # Redact API keys
    {
        "op": "text_replace",
        "path": "/logs",
        "match": r"sk-[a-zA-Z0-9]+",
        "value": "[API_KEY]",
        "regex": True,
        "count": -1
    }
]
```

### 4. Version String Updates

```python
data = {
    "readme": "Version: 1.2.3\n\nSee CHANGELOG.md for details."
}

ops = [
    {
        "op": "text_replace",
        "path": "/readme",
        "match": r"Version: (\d+\.\d+)\.\d+",
        "value": r"Version: \1.4",  # Increment patch version
        "regex": True
    }
]
```

### 5. Template Parameter Substitution

```python
data = {
    "template": "Hello {{NAME}}, your order {{ORDER_ID}} is ready."
}

# Replace all placeholders
ops = [
    {"op": "text_replace", "path": "/template", "match": "{{NAME}}", "value": "Alice"},
    {"op": "text_replace", "path": "/template", "match": "{{ORDER_ID}}", "value": "#12345"}
]
```

## API Reference

### apply_text_operations

```python
from shared.text_ops import apply_text_operations

result = apply_text_operations(
    data: Dict[str, Any],           # Data to modify (modified in place)
    operations: List[Dict[str, Any]] # Text operations
) -> TextOpResult
```

**Returns:** `TextOpResult` with fields:
- `success: bool`
- `modified_data: Dict` (same as input data, modified)
- `error: str` (if failed)
- `operations_applied: int`

### apply_patches_with_validation

Use this for mixed text + JSON Patch operations:

```python
from shared.ai_patch_utils import apply_patches_with_validation

result = apply_patches_with_validation(
    original_data: Dict[str, Any],
    patch_operations: List[Dict[str, Any]],  # Can include text ops
    validator_fn: Optional[Callable] = None,
    dry_run: bool = False
) -> PatchResult
```

Text operations are automatically detected and applied **before** standard JSON Patch operations.

## Error Handling

Text operations fail fast with clear error messages:

```python
# Match not found
{"op": "text_replace", "path": "/text", "match": "NOTFOUND", "value": "X"}
# ❌ Error: String 'NOTFOUND' not found in field /text

# Multiple matches with count=1
{"op": "text_replace", "path": "/text", "match": "foo", "value": "bar"}
# ❌ Error: String 'foo' appears 2 times in /text. Use count=-1 to replace all.

# Invalid path
{"op": "text_replace", "path": "/nonexistent", "match": "X", "value": "Y"}
# ❌ Error: Path not found: /nonexistent (missing key: nonexistent)

# Non-string field
{"op": "text_replace", "path": "/number", "match": "1", "value": "2"}
# ❌ Error: Path /number is not a string field (type: int)

# Invalid regex
{"op": "text_replace", "path": "/text", "match": "[invalid(", "value": "X", "regex": true}
# ❌ Error: Invalid regex pattern '[invalid(': ...

# Regex timeout
{"op": "text_replace", "path": "/text", "match": "(a+)+", "value": "X", "regex": true}
# ❌ Error: Regex pattern '(a+)+' timed out (possible catastrophic backtracking)
```

## Testing

Run the test suite:

```bash
python3 test_text_ops.py
```

Test coverage includes:
- ✅ Simple string replacement
- ✅ Delete (replace with empty)
- ✅ Insert before/after
- ✅ Append/prepend (text_extend)
- ✅ Regex replacement with backreferences
- ✅ Regex redaction
- ✅ Multiple sequential operations
- ✅ Combined text + JSON Patch
- ✅ Nested paths (`/config/settings/field`)
- ✅ Array element paths (`/items/1/status`)
- ✅ Count parameter (`count=-1` for all)
- ✅ Error handling (invalid paths, non-unique matches, etc.)

## Performance

- **Literal mode**: Very fast, uses Python's built-in `str.replace()`
- **Regex mode**: Depends on pattern complexity
  - Simple patterns (e.g., `\d{4}`): Fast
  - Complex patterns: Protected by 2-second timeout
- **Memory**: Deep copies data before modification (safe but uses 2x memory)

## Limitations

1. **String fields only** - Text operations require `path` to point to a string field
2. **No multi-field operations** - Each operation targets one field
3. **Sequential, not atomic** - Operations apply one by one (not transactional)
4. **Case-sensitive** - Literal matching is case-sensitive (use regex for case-insensitive)
5. **UTF-8 only** - Assumes UTF-8 text encoding

## Best Practices

### 1. Prefer Literal Mode

Use `regex: false` (default) whenever possible:
- Faster
- Safer (no catastrophic backtracking)
- More predictable
- Easier for LLMs to generate correctly

### 2. Be Specific with Matches

```json
// ❌ Too generic
{"op": "text_replace", "path": "/report", "match": "30", "value": "31"}

// ✅ More specific
{"op": "text_replace", "path": "/report", "match": "| Alice | 30 |", "value": "| Alice | 31 |"}
```

### 3. Use count=-1 Intentionally

Only use `count: -1` when you actually want to replace all occurrences:

```json
// ❌ Dangerous if you only expect one match
{"op": "text_replace", "path": "/text", "match": "foo", "value": "bar", "count": -1}

// ✅ Safe default (errors if multiple matches)
{"op": "text_replace", "path": "/text", "match": "foo", "value": "bar"}
```

### 4. Test Regex Patterns

Always test regex patterns before deploying to production:

```python
import re
test_text = "Sample data 2024-01-15"
pattern = r"(\d{4})-(\d{2})-(\d{2})"
result = re.sub(pattern, r"\2/\3/\1", test_text)
print(result)  # "Sample data 01/15/2024"
```

### 5. Validate After Operations

Use a validator function to ensure text operations didn't break data integrity:

```python
def validate_table(data):
    errors = []
    if data['table'].count('|') % 3 != 0:
        errors.append("Table has mismatched columns")
    return (len(errors) == 0, errors, [])

result = apply_patches_with_validation(
    data,
    operations,
    validator_fn=validate_table
)
```

## Troubleshooting

### "Match not found" error

**Problem:** The match string doesn't exist in the field.

**Solutions:**
1. Check for exact spacing, newlines, and capitalization
2. Print the field value to see exact content
3. Use regex mode for fuzzy matching

### "Multiple matches" error

**Problem:** Match appears more than once with `count: 1`.

**Solutions:**
1. Make match more specific (include more context)
2. Use `count: -1` to replace all
3. Use `count: N` to replace first N

### Regex timeout

**Problem:** Regex pattern causes catastrophic backtracking.

**Solutions:**
1. Simplify the pattern
2. Avoid nested quantifiers like `(a+)+`
3. Use atomic groups or possessive quantifiers if needed
4. Switch to literal mode if possible

## See Also

- [AI Patch Utils Guide](AI_PATCH_UTILS_GUIDE.md) - Using JSON Patch with LLMs
- [RFC 6902 - JSON Patch](https://datatracker.ietf.org/doc/html/rfc6902)
- [RFC 6901 - JSON Pointer](https://datatracker.ietf.org/doc/html/rfc6901)
- [Python re module](https://docs.python.org/3/library/re.html) - Regex documentation

## Version History

- **2.0** (2025-02-13): Initial release
  - `text_replace` operation with literal and regex modes
  - `text_extend` operation for append/prepend
  - Timeout protection for regex
  - Integration with `ai_patch_utils`
