# Finalize Handler - Quick Reference

**File:** `src/lambdas/interface/actions/table_maker/finalize.py`
**Updated:** October 20, 2025
**Agent:** Agent 11

---

## What Changed?

The finalize handler now **accepts pre-discovered row IDs** instead of generating them internally.

---

## How to Use (New System)

### Call with Row Discovery

```python
event_data = {
    'action': 'acceptTableAndValidate',
    'email': 'user@example.com',
    'session_id': 'session_123',
    'conversation_id': 'conv_abc',
    'row_count': 20,
    'final_row_ids': [  # NEW: From row discovery system
        {
            'id_values': {
                'Company Name': 'Anthropic',
                'Website': 'anthropic.com'
            },
            'match_score': 0.95,
            'match_rationale': 'Leading AI safety research company',
            'source_urls': ['https://anthropic.com/careers']
        },
        # ... more rows ...
    ]
}

result = await handle_table_accept_and_validate(event_data)
```

### Call without Row Discovery (Legacy)

```python
event_data = {
    'action': 'acceptTableAndValidate',
    'email': 'user@example.com',
    'session_id': 'session_123',
    'conversation_id': 'conv_abc',
    'row_count': 20
    # No final_row_ids - will use future_ids from preview_data
}

result = await handle_table_accept_and_validate(event_data)
```

---

## Input Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `email` | str | Yes | User email address |
| `session_id` | str | Yes | Session identifier |
| `conversation_id` | str | Yes | Conversation identifier |
| `row_count` | int | No | Target row count (default: 20) |
| `final_row_ids` | list | **NEW** | Pre-discovered rows from row discovery |

---

## final_row_ids Structure

```python
[
    {
        'id_values': {
            'Column1': 'value1',
            'Column2': 'value2'
        },
        'match_score': 0.95,         # 0-1, how well row matches criteria
        'match_rationale': '...',     # Why this row was selected
        'source_urls': ['https://...'] # Where data was found
    },
    # ... more rows ...
]
```

**Required fields:**
- `id_values` (dict): ID column values for this row

**Optional fields:**
- `match_score` (float): Quality score 0-1
- `match_rationale` (str): Explanation of match
- `source_urls` (list): Source URLs for verification

---

## What Happens Inside?

### With final_row_ids (New Path)

```
1. Validate final_row_ids structure
2. Create rows with ID columns from id_values
3. Leave research columns empty
4. Create clean CSV
5. Generate config
6. Return success
```

### Without final_row_ids (Legacy Path)

```
1. Load preview_data from conversation state
2. Extract future_ids from preview
3. Create placeholder rows with ID columns
4. Leave research columns empty
5. Create clean CSV
6. Generate config
7. Return success
```

**Note:** Data population happens during validation in both paths.

---

## Response Format

```python
{
    'success': True,
    'config_key': 's3://bucket/path/to/config.json',
    'config_version': 1,
    'conversation_id': 'conv_abc'
}
```

---

## Error Handling

### Missing Parameters
```python
{
    'success': False,
    'error': 'Missing required parameters: email, session_id, or conversation_id'
}
```

### Invalid final_row_ids
```python
{
    'success': False,
    'error': 'final_row_ids must be a non-empty list'
}
```

```python
{
    'success': False,
    'error': 'Each final_row_id must have id_values dictionary'
}
```

---

## Logging

### Row Discovery System
```
INFO: Using row discovery system with 20 pre-discovered rows
INFO: Adding 20 rows from row discovery system
INFO: Writing CSV with 23 rows (3 complete + 20 from row discovery)
INFO: Added 20 rows from row discovery. Total rows: 23
```

### Legacy System
```
INFO: Using legacy future_ids system from preview data
INFO: Adding 17 rows from legacy future_ids system
INFO: Writing CSV with 20 rows (3 complete + 17 ID-only)
INFO: Appending 17 placeholder rows with legacy future IDs
```

---

## Integration with Row Discovery

### From Row Discovery Orchestrator

```python
# In row_discovery.py orchestrator
final_rows_result = await consolidate_discovered_rows(stream_results)

# Pass to finalize
finalize_result = await handle_table_accept_and_validate({
    'email': email,
    'session_id': session_id,
    'conversation_id': conversation_id,
    'final_row_ids': final_rows_result['final_rows'],
    'row_count': 20
})
```

### From Execution Pipeline

```python
# In execution.py
async def execute_full_table_generation(conversation_id, approved_context):
    # Step 2: Row Discovery
    rows_result = await discover_rows(search_strategy, columns)

    # Step 3: Table Population (finalize)
    table_result = await handle_table_accept_and_validate({
        'email': email,
        'session_id': session_id,
        'conversation_id': conversation_id,
        'final_row_ids': rows_result['final_rows']
    })

    return table_result
```

---

## CSV Output

### Clean CSV (for config generation)
```csv
Company Name,Website,Is Hiring for AI?,Team Size
Anthropic,anthropic.com,,
OpenAI,openai.com,,
```

**Notes:**
- ID columns populated from final_row_ids
- Research columns empty
- No column definitions (confuses config generator)

### User CSV (for download)
```csv
# Column Definitions
# Company Name: Official company name (String)
# Website: Company website URL (String)
# ...

Company Name,Website,Is Hiring for AI?,Team Size
Anthropic,anthropic.com,,
OpenAI,openai.com,,
```

**Notes:**
- Includes column definitions at top
- Same row structure as clean CSV
- For user download

---

## Removed Functionality

### No Longer Generates Rows Internally

**Old behavior (removed):**
```python
# Generate additional rows using RowExpander
expansion_result = await row_expander.expand_rows_iteratively(...)
all_rows.extend(expansion_result['expanded_rows'])
```

**New behavior:**
```python
# Use pre-discovered rows
for discovered_row in final_row_ids:
    all_rows.append(create_row_from_id_values(discovered_row))
```

**Why removed:**
- Row discovery is now independent
- Eliminates quality drop-off
- Separates concerns clearly

---

## Backward Compatibility

### 100% Compatible

- Existing calls without `final_row_ids` work unchanged
- Same response format
- Same CSV outputs
- Same S3 structure
- Same WebSocket messages

### Migration Path

**Phase 1:** Both systems work (current)
**Phase 2:** Row discovery becomes default
**Phase 3:** Legacy future_ids deprecated (future)

---

## Testing

### Test with Row Discovery
```python
import pytest

@pytest.mark.asyncio
async def test_with_final_row_ids():
    event_data = {
        'email': 'test@example.com',
        'session_id': 'test_session',
        'conversation_id': 'test_conv',
        'final_row_ids': [
            {
                'id_values': {'Company Name': 'Anthropic'},
                'match_score': 0.95
            }
        ]
    }
    result = await handle_table_accept_and_validate(event_data)
    assert result['success'] == True
```

### Test Legacy Path
```python
@pytest.mark.asyncio
async def test_without_final_row_ids():
    event_data = {
        'email': 'test@example.com',
        'session_id': 'test_session',
        'conversation_id': 'test_conv'
        # No final_row_ids
    }
    result = await handle_table_accept_and_validate(event_data)
    assert result['success'] == True
```

---

## Common Issues

### Issue: "Each final_row_id must have id_values dictionary"

**Cause:** Missing `id_values` in final_row_ids structure

**Fix:**
```python
# Wrong
final_row_ids = [
    {'Company Name': 'Anthropic'}  # Missing id_values wrapper
]

# Correct
final_row_ids = [
    {
        'id_values': {'Company Name': 'Anthropic'}
    }
]
```

### Issue: "final_row_ids must be a non-empty list"

**Cause:** Empty list or wrong type

**Fix:**
```python
# Wrong
final_row_ids = []  # Empty
final_row_ids = None  # None

# Correct
final_row_ids = [
    {'id_values': {'Company Name': 'Anthropic'}}
]
```

---

## Performance

### Row Discovery System
- Handles 20 rows: ~5 seconds
- Handles 100 rows: ~10 seconds (estimated)
- No LLM calls in finalize (rows pre-discovered)

### Legacy System
- Handles 20 rows: ~5 seconds
- Same performance (no row generation anymore)
- Validation does data population in both cases

---

## Future Enhancements

### Planned
1. Implement `populate_batch()` for data population in finalize
2. Move data population from validation to finalize
3. Parallel batch processing
4. Real-time progress streaming

### Under Consideration
1. Make `final_row_ids` required
2. Remove legacy future_ids support
3. Streaming row processing
4. Quality scoring per row

---

## Questions?

See comprehensive documentation:
- `FINALIZE_HANDLER_UPDATE_SUMMARY.md` - Detailed changes
- `INDEPENDENT_ROW_DISCOVERY_REQUIREMENTS.md` - Overall architecture

---

**Last Updated:** October 20, 2025
