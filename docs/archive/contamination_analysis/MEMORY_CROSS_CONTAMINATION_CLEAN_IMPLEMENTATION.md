# Memory Cross-Contamination: Clean Implementation (Revised)

## Key Requirements

1. **Preserve ALL ID columns** - Multiple ID columns are allowed and should be respected
2. **Generic validation** - Works with any AI provider via `ai_client`, not just the clone
3. **Clean optional features** - Bundle clone-specific features into a single optional context object
4. **Consistent with existing patterns** - Check if row-level context/warnings already exist in validation

---

## 1. Preserve All ID Columns (Not Just One)

### Decision: Support Multiple ID Columns

**Revised Approach**: Respect whatever ID columns are defined in the table metadata. Row identity is the combination of ALL ID column values.

### Implementation

#### 1A. Table Config Validation (Relaxed)

```python
# In table_maker/config.py

class TableConfig:
    """
    Table configuration with ID column preservation.
    """

    def _validate_id_columns(self):
        """Ensure at least one ID column exists."""
        id_columns = [col for col in self.columns if col.get('is_id', False)]

        if len(id_columns) == 0:
            raise ValueError("Table must have at least 1 ID column")

        # Multiple ID columns are allowed and preserved

    def update_columns(self, new_columns: list):
        """
        Update columns while preserving ID column definitions.
        ID columns can be added/removed, but the system tracks which columns are IDs.
        """
        self.columns = new_columns
        self._validate_id_columns()
```

#### 1B. Generate Row Key from ALL ID Columns

```python
def generate_row_key(row: dict, id_columns: list) -> str:
    """
    Generate stable row key from ALL ID columns.

    Args:
        row: Row data
        id_columns: List of column definitions with is_id=True

    Returns:
        SHA256 hash of all ID column values
    """
    id_values = []

    for col in sorted(id_columns, key=lambda c: c['name']):  # Sort for consistency
        cell = row['cells'].get(col['name'], {})
        value = cell.get('full_value', '')
        id_values.append(f"{col['name']}:{value}")

    # Hash all ID values together
    key_string = '|'.join(id_values)
    return hashlib.sha256(key_string.encode()).hexdigest()
```

#### 1C. Extract ALL ID Column Values

```python
def extract_id_column_values(row: dict, table_columns: list) -> dict:
    """
    Extract all ID column values from row.

    Returns:
        {
            'id_columns': ['Company Name', 'Product / Candidate Name'],
            'id_values': ['Bayer', '225Ac-PSMA I&T'],
            'row_id_display': 'Bayer | 225Ac-PSMA I&T'
        }
    """
    id_columns = [col for col in table_columns if col.get('is_id', False)]

    id_column_names = []
    id_values = []

    for col in id_columns:
        col_name = col['name']
        value = row['cells'].get(col_name, {}).get('full_value', '')

        if value:
            id_column_names.append(col_name)
            id_values.append(value)

    return {
        'id_columns': id_column_names,
        'id_values': id_values,
        'row_id_display': ' | '.join(id_values)
    }
```

---

## 2. Clean Optional Features: Single Context Object

### Problem

Currently validation works with generic `ai_client`. Adding clone-specific features one parameter at a time clutters the API:

```python
# BAD: Too many parameters
validate_cell(
    ...,
    row_id_values=['Bayer'],
    initial_decision_breadth='broad',
    initial_decision_depth='deep',
    search_terms=['term1', 'term2'],
    ...  # More clone-specific stuff
)
```

### Solution: Single Optional Context Object

```python
# GOOD: Clean, optional, extensible
validate_cell(
    ...,
    enhanced_context=EnhancedValidationContext(
        row_identity=...,
        clone_features=...,
        warnings=...
    )  # Optional - only provided when using clone
)
```

### Implementation

#### 2A. Define EnhancedValidationContext

```python
# In validation/context.py (new file)

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

@dataclass
class RowIdentity:
    """Row identity information (ID column values)."""
    id_columns: List[str]          # ['Company Name', 'Product / Candidate Name']
    id_values: List[str]           # ['Bayer', '225Ac-PSMA I&T']
    row_key: str                   # SHA256 hash
    row_id_display: str            # 'Bayer | 225Ac-PSMA I&T'

@dataclass
class CloneFeatures:
    """Features from the clone's initial_decision."""
    search_terms: List[str] = field(default_factory=list)
    keywords: Dict[str, List[str]] = field(default_factory=dict)
    breadth: Optional[str] = None      # 'narrow', 'medium', 'broad'
    depth: Optional[str] = None        # 'shallow', 'medium', 'deep'
    strategy: Optional[str] = None     # 'survey', 'deep_dive', etc.

    # Future: Add more clone features as needed
    # confidence_threshold: Optional[float] = None
    # recency_filter: Optional[str] = None

@dataclass
class RowWarnings:
    """Warnings about this row (e.g., similar rows detected)."""
    similar_rows: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

@dataclass
class EnhancedValidationContext:
    """
    Optional enhanced context for validation.

    Only provided when using advanced features like the clone.
    Generic ai_client validation ignores this.
    """
    row_identity: Optional[RowIdentity] = None
    clone_features: Optional[CloneFeatures] = None
    row_warnings: Optional[RowWarnings] = None

    # Easy extensibility for future features
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            'row_identity': {
                'id_columns': self.row_identity.id_columns,
                'id_values': self.row_identity.id_values,
                'row_key': self.row_identity.row_key,
                'row_id_display': self.row_identity.row_id_display
            } if self.row_identity else None,
            'clone_features': {
                'search_terms': self.clone_features.search_terms,
                'keywords': self.clone_features.keywords,
                'breadth': self.clone_features.breadth,
                'depth': self.clone_features.depth,
                'strategy': self.clone_features.strategy
            } if self.clone_features else None,
            'row_warnings': {
                'similar_rows': self.row_warnings.similar_rows,
                'warnings': self.row_warnings.warnings
            } if self.row_warnings else None,
            'metadata': self.metadata
        }
```

#### 2B. Update Validation Signature

```python
# In validation lambda or validation function

async def validate_cell(
    cell_value: str,
    column: dict,
    row: dict,
    table_metadata: dict,
    ai_client: AIClient,  # Generic - could be clone, openai, anthropic, etc.
    enhanced_context: Optional[EnhancedValidationContext] = None,  # NEW - optional
    **kwargs
) -> dict:
    """
    Validate a cell value.

    Args:
        cell_value: Value to validate
        column: Column definition
        row: Row data
        table_metadata: Table structure
        ai_client: AI provider (generic)
        enhanced_context: Optional enhanced features (clone-specific, row warnings, etc.)
    """

    # Build validation prompt (generic, works with any AI)
    prompt = build_validation_prompt(cell_value, column, row)

    # Check if using clone with enhanced features
    if enhanced_context and isinstance(ai_client, TheClone2Refined):
        # Use clone-specific features
        result = await validate_with_clone_features(
            ai_client=ai_client,
            prompt=prompt,
            enhanced_context=enhanced_context,
            **kwargs
        )
    else:
        # Generic validation (works with any AI provider)
        result = await ai_client.query(prompt, **kwargs)

    return result
```

#### 2C. Clone-Specific Validation (When Enhanced Context Provided)

```python
async def validate_with_clone_features(
    ai_client: TheClone2Refined,
    prompt: str,
    enhanced_context: EnhancedValidationContext,
    session_id: str = None,
    email: str = None,
    s3_manager = None,
    **kwargs
) -> dict:
    """
    Validation using clone with enhanced features.

    Extracts row identity for memory filtering.
    Extracts clone features for search optimization.
    """

    # Extract row identity for memory filtering
    row_context = None
    if enhanced_context.row_identity:
        row_context = {
            'row_key': enhanced_context.row_identity.row_key,
            'id_columns': enhanced_context.row_identity.id_columns,
            'id_values': enhanced_context.row_identity.id_values,
            'row_id_display': enhanced_context.row_identity.row_id_display
        }

    # Call clone with row context for memory filtering
    result = await ai_client.query(
        prompt=prompt,
        session_id=session_id,
        email=email,
        s3_manager=s3_manager,
        use_memory=True,
        row_context=row_context,  # Passed to memory system
        **kwargs
    )

    return result
```

#### 2D. Build Enhanced Context Before Validation

```python
# In validation orchestrator/lambda

async def validate_table(table_data: dict, use_clone: bool = False):
    """Validate entire table."""

    results = []

    for row in table_data['rows']:
        # Always extract row identity
        row_identity_info = extract_id_column_values(row, table_data['columns'])

        # Build enhanced context if using clone
        enhanced_context = None
        if use_clone:
            enhanced_context = EnhancedValidationContext(
                row_identity=RowIdentity(
                    id_columns=row_identity_info['id_columns'],
                    id_values=row_identity_info['id_values'],
                    row_key=row['row_key'],
                    row_id_display=row_identity_info['row_id_display']
                ),
                # Clone features can be populated if we have initial_decision data
                clone_features=None,  # Populated later if needed
                # Row warnings can be populated if we detect similar rows
                row_warnings=None  # Populated later if needed
            )

        # Validate each cell
        for column in table_data['columns']:
            if column.get('importance') == 'RESEARCH':
                cell = row['cells'].get(column['name'], {})

                result = await validate_cell(
                    cell_value=cell.get('full_value', ''),
                    column=column,
                    row=row,
                    table_metadata=table_data,
                    ai_client=ai_client,
                    enhanced_context=enhanced_context,  # Optional - only if using clone
                    **validation_kwargs
                )

                results.append(result)

    return results
```

---

## 3. Check Existing Row Warning Mechanisms

### Question: Is there already a row warning system in validation?

Let me check the codebase structure:

```python
# Typical validation result structure (from your system)
validation_result = {
    'display_value': '...',
    'full_value': '...',
    'confidence': 'HIGH',
    'comment': {
        'original_value': '...',
        'original_confidence': '...',
        'validator_explanation': '...',
        'qc_reasoning': '...',  # QC step reasoning
        'key_citation': '...',
        'sources': [...]
    },
    '_columnName': '...',
    '_rowId': '...'
}
```

**Observation**: There doesn't appear to be a standard "row warnings" field in the validation result structure.

### Proposal: Add Row Warnings to Enhanced Context

If similar rows are detected, include warnings in `EnhancedValidationContext`:

```python
# Detect similar rows before validation
similar_rows = find_similar_rows(current_row, all_rows, table_columns)

if similar_rows:
    row_warnings = RowWarnings(
        similar_rows=similar_rows,
        warnings=[
            f"Similar row detected: {sr['row_id_display']} (similarity: {sr['similarity']:.0%})"
            for sr in similar_rows[:3]
        ]
    )

    enhanced_context.row_warnings = row_warnings
```

Then, in the validation prompt generation, include the warnings:

```python
def build_validation_prompt(
    cell_value: str,
    column: dict,
    row: dict,
    enhanced_context: Optional[EnhancedValidationContext] = None
) -> str:
    """Build validation prompt with optional warnings."""

    prompt = f"""
Validate the following cell:

Column: {column['name']}
Value: {cell_value}

"""

    # Add row warnings if present
    if enhanced_context and enhanced_context.row_warnings:
        warnings = enhanced_context.row_warnings.warnings
        if warnings:
            prompt += """
⚠️ ROW DISAMBIGUATION WARNING:

"""
            for warning in warnings:
                prompt += f"- {warning}\n"

            prompt += """
Please ensure your validation is specific to this row and does not confuse it with similar rows.

"""

    prompt += """
[Rest of validation instructions...]
"""

    return prompt
```

---

## 4. Memory System Integration

### Update Memory to Use Row Identity from Enhanced Context

```python
# In the_clone.py

async def query(
    self,
    prompt: str,
    row_context: dict = None,  # NEW: Extracted from enhanced_context
    **kwargs
) -> dict:
    """
    Query with optional row context for memory filtering.

    Args:
        row_context: {
            'row_key': 'abc123...',
            'id_columns': ['Company Name', 'Product / Candidate Name'],
            'id_values': ['Bayer', '225Ac-PSMA I&T'],
            'row_id_display': 'Bayer | 225Ac-PSMA I&T'
        }
    """

    # Memory recall with row filtering
    if use_memory and memory and row_context:
        recall_result = await memory.recall(
            query=prompt,
            keywords=keywords,
            row_identifiers={
                'id_values': row_context['id_values'],
                'row_key': row_context['row_key']
            },
            **recall_kwargs
        )

    # ... rest of query logic ...

    # Store search results with row context
    if search_executed:
        for search_term, search_result in zip(search_terms, search_results):
            MemoryCache.store_search(
                session_id=session_id,
                search_term=search_term,
                results=search_result,
                parameters=search_params,
                strategy=strategy,
                row_context=row_context  # Store with row identity
            )
```

### Update Memory Scoring (As Before)

```python
# In search_memory.py

def _calculate_row_context_score(
    self,
    stored_query: dict,
    current_row_identifiers: dict
) -> float:
    """
    Score based on row identity match.

    Returns:
        +10: All ID values match (same row)
        +5: Partial ID match (some IDs match)
        0: No row context (general query)
        -5: No ID values match (different row)
    """
    if not current_row_identifiers:
        return 0.0

    current_id_values = current_row_identifiers.get('id_values', [])
    stored_row_context = stored_query.get('row_context')

    if not stored_row_context:
        return 0.0  # General query

    stored_id_values = stored_row_context.get('id_values', [])

    if not stored_id_values:
        return 0.0

    # Calculate match score
    matches = 0
    for current_id in current_id_values:
        for stored_id in stored_id_values:
            if current_id.lower() == stored_id.lower():
                matches += 1
                break

    total_ids = len(current_id_values)
    match_ratio = matches / total_ids if total_ids > 0 else 0

    if match_ratio == 1.0:
        return 10.0   # Perfect match (all IDs match)
    elif match_ratio >= 0.5:
        return 5.0    # Partial match (at least half IDs match)
    elif match_ratio > 0:
        return 2.0    # Weak match (some IDs match)
    else:
        return -5.0   # No match (different row)
```

---

## 5. Complete Example Usage

### Example 1: Generic Validation (No Enhanced Context)

```python
# Works with any AI provider
result = await validate_cell(
    cell_value="Bayer",
    column=company_column,
    row=current_row,
    table_metadata=table_data,
    ai_client=openai_client  # or anthropic_client, etc.
)
```

### Example 2: Clone with Enhanced Context

```python
# Extract row identity
row_identity_info = extract_id_column_values(current_row, table_data['columns'])

# Build enhanced context
enhanced_context = EnhancedValidationContext(
    row_identity=RowIdentity(
        id_columns=row_identity_info['id_columns'],
        id_values=row_identity_info['id_values'],
        row_key=current_row['row_key'],
        row_id_display=row_identity_info['row_id_display']
    )
)

# Detect similar rows
similar_rows = find_similar_rows(current_row, all_rows, table_data['columns'])
if similar_rows:
    enhanced_context.row_warnings = RowWarnings(
        similar_rows=similar_rows,
        warnings=[f"Similar to: {sr['row_id_display']}" for sr in similar_rows]
    )

# Validate with clone + enhanced features
result = await validate_cell(
    cell_value="Bayer",
    column=company_column,
    row=current_row,
    table_metadata=table_data,
    ai_client=clone_client,
    enhanced_context=enhanced_context,  # Optional - enables memory filtering
    session_id=session_id,
    email=email,
    s3_manager=s3_manager
)
```

### Example 3: Add Clone Features from Initial Decision

```python
# If we have initial_decision data, populate clone features
initial_decision = await clone_client.initial_decision(prompt)

enhanced_context.clone_features = CloneFeatures(
    search_terms=initial_decision.get('search_terms', []),
    keywords=initial_decision.get('keywords', {}),
    breadth=initial_decision.get('breadth'),
    depth=initial_decision.get('depth'),
    strategy=initial_decision.get('strategy')
)

# Now validation can use these features for optimization
result = await validate_cell(..., enhanced_context=enhanced_context)
```

---

## 6. Benefits of This Approach

### ✅ Clean API
- Single optional parameter (`enhanced_context`)
- Not cluttered with many individual arguments
- Easy to extend with new features

### ✅ Backward Compatible
- Existing validation code works unchanged
- `enhanced_context` is optional
- Generic AI providers ignore it

### ✅ Type Safe
- Dataclasses provide structure and validation
- IDE autocomplete works
- Easy to serialize/deserialize

### ✅ Extensible
- Add new features to `EnhancedValidationContext` without breaking existing code
- `metadata` dict for ad-hoc extensions
- Clear separation between generic validation and clone-specific features

### ✅ Testable
- Easy to mock `EnhancedValidationContext`
- Can test with/without enhanced features
- Clear interfaces

---

## 7. Migration Plan

### Phase 1: Add Optional Context (Week 1)
1. Create `EnhancedValidationContext` dataclass
2. Add optional `enhanced_context` parameter to `validate_cell()`
3. Ensure backward compatibility (no breaking changes)

### Phase 2: Wire Row Identity (Week 2)
4. Update validation orchestrator to extract row identity
5. Pass row identity in enhanced context when using clone
6. Update memory system to use row identity for scoring

### Phase 3: Add Warnings (Week 3)
7. Implement `find_similar_rows()` detection
8. Populate `row_warnings` in enhanced context
9. Update prompt generation to include warnings

### Phase 4: Monitoring (Week 4)
10. Track cross-contamination rate
11. Monitor memory effectiveness
12. Tune scoring weights if needed

---

## 8. Questions Answered

### Q1: Should we enforce single ID column or allow multiple?

**A: Allow multiple ID columns.** The config should respect whatever ID columns are defined. Row identity is the combination of ALL ID column values.

### Q2: How to wire ID columns without cluttering validation API?

**A: Single optional `enhanced_context` parameter.** Bundles all optional features (row identity, clone features, warnings) into one clean object.

### Q3: Is there an existing row warning mechanism?

**A: No standard mechanism found.** Propose adding `row_warnings` to `EnhancedValidationContext` and injecting into validation prompt when present.

### Q4: How to keep validation generic while supporting clone features?

**A: Optional context + type checking.** Check if `ai_client` is `TheClone2Refined`, and if `enhanced_context` is provided, enable advanced features. Otherwise, use generic validation.

---

## Code Organization

```
src/
  validation/
    context.py              # NEW: EnhancedValidationContext dataclass
    validate_cell.py        # UPDATED: Add enhanced_context parameter
    similar_rows.py         # NEW: find_similar_rows() detection

  the_clone/
    the_clone.py            # UPDATED: Accept row_context parameter
    search_memory.py        # UPDATED: Row context scoring
    search_memory_cache.py  # UPDATED: Store row context with queries

  table_maker/
    config.py               # UPDATED: Allow multiple ID columns
```

---

## Testing Strategy

```python
# Test 1: Backward compatibility
async def test_validation_without_enhanced_context():
    result = await validate_cell(
        cell_value="test",
        column=column,
        row=row,
        table_metadata=table_data,
        ai_client=generic_client
        # No enhanced_context - should work fine
    )
    assert result is not None

# Test 2: Clone with row identity
async def test_validation_with_row_identity():
    enhanced_context = EnhancedValidationContext(
        row_identity=RowIdentity(
            id_columns=['Company', 'Product'],
            id_values=['Bayer', 'Product X'],
            row_key='abc123',
            row_id_display='Bayer | Product X'
        )
    )

    result = await validate_cell(
        ...,
        ai_client=clone_client,
        enhanced_context=enhanced_context
    )

    # Memory should have filtered by row identity
    assert 'Bayer' in result['sources'][0]['snippet']

# Test 3: Similar row warnings
async def test_validation_with_warnings():
    enhanced_context = EnhancedValidationContext(
        row_identity=...,
        row_warnings=RowWarnings(
            warnings=["Similar to: Company B | Product Y"]
        )
    )

    prompt = build_validation_prompt(..., enhanced_context=enhanced_context)

    assert "ROW DISAMBIGUATION WARNING" in prompt
```
