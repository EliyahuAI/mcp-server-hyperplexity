# Memory Cross-Contamination: Implementation Details

## 1. Enforce Single Immutable ID Column

### Decision: Lock ID Column in Table Maker

**Requirement**: Table Maker config must have exactly ONE ID column that CANNOT be changed after table creation.

### Implementation

#### 1A. Update Table Maker Configuration

```python
# In table_maker/config.py or equivalent

class TableConfig:
    """
    Table configuration with immutable ID column enforcement.
    """

    def __init__(self, columns: list):
        self.columns = columns
        self._validate_id_columns()

    def _validate_id_columns(self):
        """Ensure exactly one ID column exists."""
        id_columns = [col for col in self.columns if col.get('is_id', False)]

        if len(id_columns) == 0:
            raise ValueError("Table must have exactly 1 ID column")
        if len(id_columns) > 1:
            raise ValueError(f"Table must have exactly 1 ID column, found {len(id_columns)}")

    def update_columns(self, new_columns: list):
        """
        Update columns, but prevent changes to ID column.
        """
        # Find the original ID column
        original_id_col = next((col for col in self.columns if col.get('is_id')), None)
        new_id_col = next((col for col in new_columns if col.get('is_id')), None)

        # Ensure ID column hasn't changed
        if original_id_col and new_id_col:
            if original_id_col['name'] != new_id_col['name']:
                raise ValueError(
                    f"Cannot change ID column from '{original_id_col['name']}' to '{new_id_col['name']}'. "
                    f"ID columns are immutable."
                )

        self.columns = new_columns
        self._validate_id_columns()
```

#### 1B. Prevent ID Column Changes in Frontend

```javascript
// In table_maker frontend

function validateColumnChange(originalColumns, newColumns) {
    const originalIdCol = originalColumns.find(col => col.is_id);
    const newIdCol = newColumns.find(col => col.is_id);

    if (!originalIdCol || !newIdCol) {
        throw new Error("Table must have exactly 1 ID column");
    }

    if (originalIdCol.name !== newIdCol.name) {
        throw new Error(
            `Cannot change ID column from '${originalIdCol.name}' to '${newIdCol.name}'. ` +
            `ID columns are immutable once set.`
        );
    }

    return true;
}
```

#### 1C. UI Indicator for ID Column

```javascript
// Show locked icon next to ID column
function renderColumnHeader(column) {
    if (column.is_id) {
        return `
            <div class="column-header locked">
                <span class="column-name">${column.name}</span>
                <span class="id-badge" title="ID Column (Immutable)">
                    🔒 ID
                </span>
            </div>
        `;
    }
    // ... regular column rendering
}
```

### Migration Strategy

For existing tables with multiple ID columns:

```python
def migrate_existing_tables():
    """
    Migrate tables with multiple ID columns to single ID column.
    """
    for table in existing_tables:
        id_columns = [col for col in table['columns'] if col.get('is_id')]

        if len(id_columns) > 1:
            # Strategy: Keep the first ID column, remove is_id flag from others
            primary_id = id_columns[0]

            for col in table['columns']:
                if col.get('is_id') and col['name'] != primary_id['name']:
                    col['is_id'] = False
                    col['_migrated_from_id'] = True  # Track migration

            logger.warning(
                f"Table {table['name']}: Migrated to single ID column '{primary_id['name']}'. "
                f"Other ID columns converted to regular columns."
            )
```

---

## 2. Wire ID Columns to Search (Without Bloating Prompt)

### Challenge

The validation prompt is already large and used across many systems. We need to pass ID column information to the clone WITHOUT increasing prompt size.

### Solution: Separate Parameter + Compact Encoding

**Strategy**: Pass ID column info as a **separate parameter** to `the_clone.query()`, not in the prompt text.

#### 2A. Add `row_context` Parameter to Clone

```python
# In the_clone.py

async def query(
    self,
    prompt: str,
    session_id: str = None,
    email: str = None,
    s3_manager = None,
    use_memory: bool = True,
    row_context: dict = None,  # NEW PARAMETER
    **kwargs
) -> dict:
    """
    Execute a query with optional memory.

    Args:
        prompt: The validation query (existing)
        row_context: Row identity information (NEW):
            {
                'row_key': 'abc123...',
                'id_column': 'Company Name',
                'id_value': 'Bayer',
                'all_id_columns': ['Company Name'],  # For multi-ID support later
                'all_id_values': ['Bayer']
            }
        ...
    """
    # Use row_context for memory filtering
    if use_memory and memory and row_context:
        recall_result = await memory.recall(
            query=prompt,
            keywords=keywords,
            row_identifiers={
                'id_values': row_context.get('all_id_values', []),
                'row_key': row_context.get('row_key')
            },
            **recall_kwargs
        )
```

#### 2B. Validation Lambda Passes Row Context

```python
# In validation lambda

async def validate_cell(
    cell_value: str,
    column_name: str,
    row: dict,
    table_metadata: dict,
    **kwargs
):
    """Validate a single cell."""

    # Extract ID column info from table metadata
    id_column = next((col for col in table_metadata['columns'] if col.get('is_id')), None)

    if not id_column:
        raise ValueError("Table must have an ID column")

    # Extract ID value from this row
    id_value = row['cells'].get(id_column['name'], {}).get('full_value', '')

    # Build row context
    row_context = {
        'row_key': row.get('row_key'),
        'id_column': id_column['name'],
        'id_value': id_value,
        'all_id_columns': [id_column['name']],  # Future-proof for multi-ID
        'all_id_values': [id_value]
    }

    # Call the clone with row context
    result = await clone.query(
        prompt=validation_prompt,
        session_id=session_id,
        email=email,
        s3_manager=s3_manager,
        use_memory=True,
        row_context=row_context,  # Pass as parameter, not in prompt
        **kwargs
    )

    return result
```

#### 2C. Optional: Compact Encoding in Prompt (If Needed)

If the LLM validator itself needs to know the row identity (for search query generation), use a compact encoding:

```python
def build_validation_prompt(cell_value: str, column_name: str, row_context: dict) -> str:
    """
    Build validation prompt with optional compact row identity encoding.
    """

    prompt = f"""
Validate the following cell:

Column: {column_name}
Value: {cell_value}

"""

    # OPTIONAL: Add compact row identity if LLM needs it
    # This is ONLY if the LLM needs to generate search queries with the ID
    if row_context:
        id_value = row_context.get('id_value', '')
        if id_value:
            # Compact encoding: Single line, easy to parse out
            prompt += f"[ROW_ID: {id_value}]\n\n"

    prompt += """
Validation instructions...
"""

    return prompt
```

**Compact Encoding Benefits**:
- Single line: `[ROW_ID: Bayer]`
- Easy to parse out if needed
- Minimal prompt bloat (~10-20 characters)
- Can be stripped if not needed by specific systems

**When to include in prompt**:
- ✅ Include: If the LLM validator generates search queries (so it can include the ID in searches)
- ❌ Skip: If the LLM just validates a cell value against sources (memory system handles ID filtering)

#### 2D. Backward Compatibility

```python
# Graceful degradation for systems that don't pass row_context yet
async def query(self, prompt: str, row_context: dict = None, **kwargs):
    """
    row_context is optional. If not provided:
    - Memory filtering skips ID-based filtering (falls back to keyword-only)
    - System still works, just without cross-contamination protection
    """

    if use_memory and memory:
        if row_context:
            # New behavior: Filter by ID
            row_identifiers = {
                'id_values': row_context.get('all_id_values', []),
                'row_key': row_context.get('row_key')
            }
        else:
            # Backward compatibility: No ID filtering
            logger.warning("[MEMORY] No row_context provided, skipping ID-based filtering")
            row_identifiers = None

        recall_result = await memory.recall(
            query=prompt,
            keywords=keywords,
            row_identifiers=row_identifiers,
            **kwargs
        )
```

---

## 3. Add ID Column Information to Memory Query Scoring

### Goal

When recalling from memory, prioritize queries that were for the SAME row, penalize queries for DIFFERENT rows, and treat general queries neutrally.

### Scoring System

```
+10 points: Stored query is for the SAME row (ID values match)
-5 points: Stored query is for a DIFFERENT row (ID values don't match)
0 points: Stored query has no row ID (general information, e.g., background research)
```

### Implementation

#### 3A. Store Row Context with Each Query

```python
# In search_memory.py, modify store_search()

async def store_search(
    self,
    search_term: str,
    results: dict,
    parameters: dict,
    strategy: str,
    row_context: dict = None  # NEW PARAMETER
):
    """
    Store search results in memory with row context.

    Args:
        row_context: {
            'row_key': 'abc123...',
            'id_values': ['Bayer'],
            'id_column_names': ['Company Name']
        }
    """
    query_id = self._generate_query_id(search_term, parameters)

    query_data = {
        'query_text': search_term,
        'search_term': search_term,
        'query_time': datetime.utcnow().isoformat(),
        'parameters': parameters,
        'results': results.get('results', []),
        'metadata': {
            'cost': results.get('cost', 0),
            'num_results': len(results.get('results', [])),
            'strategy': strategy
        },
        'row_context': row_context  # NEW FIELD
    }

    self.memory['queries'][query_id] = query_data
    self._update_indexes(query_id, query_data)

    await self._backup_to_s3()
```

#### 3B. Modify Keyword Filter to Include Row Context Scoring

```python
# In search_memory.py, modify _keyword_filter()

def _keyword_filter(
    self,
    query: str,
    keywords: dict,
    row_identifiers: dict = None,  # Current row's ID info
    top_k: int = 30
) -> list:
    """
    Filter queries by keyword match + row context match.

    Args:
        row_identifiers: {
            'id_values': ['Bayer'],
            'row_key': 'abc123...'
        }
    """
    scored_queries = []

    for query_id, query_data in self.memory['queries'].items():
        # Existing: Calculate keyword match score
        keyword_score = self._calculate_keyword_score(query_data, query, keywords)

        # NEW: Calculate row context match score
        row_context_score = self._calculate_row_context_score(
            query_data,
            row_identifiers
        )

        # Combined score
        total_score = keyword_score + row_context_score

        scored_queries.append({
            'query_id': query_id,
            'query_data': query_data,
            'keyword_score': keyword_score,
            'row_context_score': row_context_score,
            'total_score': total_score
        })

    # Sort by total score
    scored_queries.sort(key=lambda q: q['total_score'], reverse=True)

    # Return top K
    return scored_queries[:top_k]

def _calculate_row_context_score(
    self,
    stored_query: dict,
    current_row_identifiers: dict
) -> float:
    """
    Calculate row context match score.

    Returns:
        +10: Same row (ID values match)
        -5: Different row (ID values don't match)
        0: No row context (general query)
    """
    if not current_row_identifiers:
        return 0.0  # No filtering requested

    current_id_values = current_row_identifiers.get('id_values', [])
    if not current_id_values:
        return 0.0

    # Get stored row context
    stored_row_context = stored_query.get('row_context')

    if not stored_row_context:
        # Stored query has no row context (general information)
        return 0.0

    stored_id_values = stored_row_context.get('id_values', [])

    if not stored_id_values:
        return 0.0

    # Compare ID values
    match = self._id_values_match(current_id_values, stored_id_values)

    if match == 'exact':
        return 10.0  # SAME ROW - Strong boost
    elif match == 'partial':
        return 5.0   # Partial match (e.g., one ID matches)
    elif match == 'none':
        return -5.0  # DIFFERENT ROW - Penalize
    else:
        return 0.0   # Unclear

def _id_values_match(self, current_ids: list, stored_ids: list) -> str:
    """
    Check if ID values match.

    Returns:
        'exact': All ID values match
        'partial': Some ID values match
        'none': No ID values match
    """
    if not current_ids or not stored_ids:
        return 'unknown'

    matches = 0
    for current_id in current_ids:
        for stored_id in stored_ids:
            # Case-insensitive comparison
            if current_id.lower() == stored_id.lower():
                matches += 1
                break

    if matches == len(current_ids) and matches == len(stored_ids):
        return 'exact'  # All match
    elif matches > 0:
        return 'partial'  # Some match
    else:
        return 'none'  # No match
```

#### 3C. Update MemoryCache to Pass Row Context

```python
# In search_memory_cache.py

@classmethod
def store_search(
    cls,
    session_id: str,
    search_term: str,
    results: dict,
    parameters: dict,
    strategy: str,
    row_context: dict = None  # NEW PARAMETER
):
    """Store search with row context."""

    memory = cls.get(session_id)

    await memory.store_search(
        search_term=search_term,
        results=results,
        parameters=parameters,
        strategy=strategy,
        row_context=row_context  # Pass through
    )

    cls._mark_dirty(session_id)
```

#### 3D. Wire Row Context Through the Clone

```python
# In the_clone.py

async def query(self, prompt: str, row_context: dict = None, **kwargs):
    """Execute query with row context."""

    # ... initial decision, etc. ...

    # Memory recall
    if use_memory and memory:
        recall_result = await memory.recall(
            query=prompt,
            keywords=keywords,
            row_identifiers={
                'id_values': row_context.get('all_id_values', []),
                'row_key': row_context.get('row_key')
            } if row_context else None,
            **recall_kwargs
        )

    # ... search execution ...

    # Store search results with row context
    if search_executed:
        for search_term, search_result in zip(search_terms, search_results):
            MemoryCache.store_search(
                session_id=session_id,
                search_term=search_term,
                results=search_result,
                parameters={'max_results': 10},
                strategy=strategy,
                row_context=row_context  # NEW: Include row context
            )
```

### Example Scoring Scenario

**Table**: Radiopharmaceutical companies

**Current validation**: Row for "Bayer, 225Ac-PSMA I&T"

**Memory contains**:
1. Query about "Bayer PSMA trials" (stored with row_context: ["Bayer"])
2. Query about "Curium PSMA product" (stored with row_context: ["Curium"])
3. Query about "PSMA mechanism of action" (stored with NO row_context - general info)

**Scoring**:
```
Query 1: keyword_score=8.5, row_context_score=+10.0 (same row), total=18.5 ✅ TOP PRIORITY
Query 3: keyword_score=7.2, row_context_score=0.0 (general), total=7.2  ✅ NEUTRAL
Query 2: keyword_score=8.0, row_context_score=-5.0 (different row), total=3.0 ❌ DEPRIORITIZED
```

**Result**: Query 1 is recalled first (same row), Query 3 is considered (general info), Query 2 is deprioritized (different row).

---

## Implementation Order

### Phase 1: Foundation (Week 1)

1. ✅ **Enforce single immutable ID column** (Section 1)
   - Update Table Maker config validation
   - Lock ID column in frontend
   - Migrate existing tables

2. ✅ **Add row_context parameter to clone** (Section 2A-2B)
   - Add parameter to `the_clone.query()`
   - Update validation lambda to extract and pass row context
   - Backward compatible (optional parameter)

### Phase 2: Memory Filtering (Week 2)

3. ✅ **Store row context with queries** (Section 3A)
   - Add row_context field to stored queries
   - Update MemoryCache.store_search()

4. ✅ **Implement row context scoring** (Section 3B)
   - Modify _keyword_filter() to score by row context
   - Implement _calculate_row_context_score()
   - Test scoring logic

### Phase 3: Testing & Monitoring (Week 3)

5. ✅ **Test cross-contamination fixes**
   - Run validation on known problematic cases (PharmaLogic/Ratio, Curium/POINT)
   - Verify memory recalls are row-specific
   - Check scoring impact

6. ✅ **Monitor metrics**
   - Memory hit rate (should remain >40%)
   - Cross-contamination rate (should drop to <1%)
   - Row context score distribution

---

## Testing

### Test Case 1: Row Context Scoring

```python
async def test_row_context_scoring():
    """Test that same-row queries are prioritized."""

    # Setup memory with queries for different rows
    memory.store_search(
        search_term="Bayer PSMA trial results",
        results={...},
        row_context={'id_values': ['Bayer']}
    )

    memory.store_search(
        search_term="Curium PSMA trial results",
        results={...},
        row_context={'id_values': ['Curium']}
    )

    memory.store_search(
        search_term="PSMA targeting mechanism",
        results={...},
        row_context=None  # General info
    )

    # Recall for Bayer row
    results = await memory.recall(
        query="Bayer PSMA clinical data",
        keywords={'positive': ['PSMA', 'clinical']},
        row_identifiers={'id_values': ['Bayer']}
    )

    # Verify Bayer query is top-ranked
    assert results['memories'][0]['query_text'] == "Bayer PSMA trial results"
    assert results['memories'][0]['row_context_score'] == 10.0

    # Verify Curium query is deprioritized
    curium_query = next(m for m in results['memories'] if 'Curium' in m['query_text'])
    assert curium_query['row_context_score'] == -5.0
```

### Test Case 2: Backward Compatibility

```python
async def test_backward_compatibility():
    """Test that system works without row_context."""

    # Call clone without row_context
    result = await clone.query(
        prompt="Validate this cell",
        session_id="test123",
        use_memory=True
        # No row_context parameter
    )

    # Should not crash, should work with keyword-only filtering
    assert result is not None
```

---

## Monitoring Dashboards

### Row Context Scoring Metrics

```python
# Track scoring distribution
metrics = {
    'same_row_recalls': 0,      # row_context_score = +10
    'different_row_recalls': 0, # row_context_score = -5
    'neutral_recalls': 0,       # row_context_score = 0
    'total_recalls': 0
}

# Calculate percentage
same_row_percentage = metrics['same_row_recalls'] / metrics['total_recalls']
# Target: >70% of recalls should be same-row
```

### Cross-Contamination Detection

```python
def detect_contamination_in_result(result: dict, expected_row_context: dict) -> bool:
    """Check if result contains information about wrong row."""

    expected_id = expected_row_context['id_values'][0]

    for source in result['sources']:
        text = f"{source['title']} {source['snippet']}"

        # Check if other rows' ID values appear (but expected ID doesn't)
        other_ids_found = []
        for row in all_table_rows:
            other_id = row['id_values'][0]
            if other_id != expected_id and other_id.lower() in text.lower():
                other_ids_found.append(other_id)

        if other_ids_found and expected_id.lower() not in text.lower():
            return True  # Contamination detected

    return False
```

---

## Questions & Answers

### Q: What if a source mentions multiple rows legitimately (e.g., comparison article)?

**A**: The row context scoring handles this:
- If the source mentions BOTH the current row and other rows → Neutral score (0 points)
- If the source ONLY mentions other rows → Negative score (-5 points)
- If the source mentions ONLY the current row → Positive score (+10 points)

The scoring prioritizes row-specific sources while still allowing comparative/general sources to be recalled.

### Q: Should we completely filter out different-row sources, or just deprioritize?

**A**: **Deprioritize, don't filter completely**.

**Reasoning**:
- Some sources legitimately discuss multiple rows (partnerships, comparisons)
- Filtering too aggressively may remove valid information
- Negative scoring (-5 points) pushes them down the ranking while keeping them available

If cross-contamination persists after scoring, we can add a **hard filter** option:

```python
if row_context_strict_mode:
    # Hard filter: Remove queries with negative row context score
    scored_queries = [q for q in scored_queries if q['row_context_score'] >= 0]
```

### Q: How do we handle legacy memory (stored queries without row_context)?

**A**: Graceful degradation:

```python
stored_row_context = stored_query.get('row_context')

if not stored_row_context:
    # Legacy query (no row context stored)
    return 0.0  # Treat as general information
```

Legacy queries get neutral scoring, so they:
- ✅ Can still be recalled (not penalized)
- ⚠️ Don't get priority boost (not as good as row-specific queries)

Over time, as new validations run and store row_context, the memory will accumulate row-specific queries that get priority.

---

## Migration Checklist

- [ ] Update Table Maker to enforce single immutable ID column
- [ ] Migrate existing tables to single ID column
- [ ] Add row_context parameter to the_clone.query()
- [ ] Update validation lambda to extract and pass row context
- [ ] Add row_context field to search_memory.store_search()
- [ ] Update MemoryCache.store_search() to accept row_context
- [ ] Implement row context scoring in _keyword_filter()
- [ ] Add _calculate_row_context_score() method
- [ ] Test scoring logic with unit tests
- [ ] Deploy and monitor cross-contamination rate
- [ ] Adjust scoring weights if needed (+10/-5 vs other values)
