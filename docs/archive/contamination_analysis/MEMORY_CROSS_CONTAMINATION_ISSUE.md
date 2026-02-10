# Search Memory Cross-Contamination Issue

## Problem Statement

The Search Memory System is causing **cross-contamination** where information about one company's product appears in validation results for a different company's product. This results in factually incorrect data in the validated table, with information from Row A bleeding into Row B.

### Severity

**Critical** - This issue compromises data integrity and defeats the purpose of validation. Users receive mixed information where Company A's trial data, partnerships, and product details appear in Company B's row.

---

## Observed Examples

### Example 1: PharmaLogic Holdings Corp. Row (Most Severe)

**Expected**: Information about PharmaLogic's own radiopharmaceutical products

**Actual**: Every column contaminated with Ratio Therapeutics information

| Column | Contaminated Content |
|--------|---------------------|
| Target / Indication | "Ratio Therapeutics press releases specify FAP as the target for imaging agent RTX-1363S and therapeutic RTX-2358" |
| Therapeutic Agent | "Ratio's lead therapeutic is [Ac-225]-RTX-2358, an alpha-emitting radiotherapeutic targeting FAP" |
| Diagnostic/Theranostic | "Ratio's platform accommodates imaging and therapeutic isotopes... The diagnostic agent is Copper-64-labeled RTX-1363S" |
| Specific Biochemistry | "Ratio's proprietary platforms are Trillium™ for PK modulation via reversible albumin binding and Macropa™ for chelating actinium-225" |
| Development Stage | "Therapeutic [Ac-225]-RTX-2358 is in a Phase 1/2 trial (ATLAS) for sarcomas" |
| Latest News | All news items about Ratio's ATLAS trial and RTX products |
| Key Partnerships | "Ratio is the development partner, Lantheus for imaging, Nusano for isotope supply, and PharmaLogic for manufacturing" |

**Root Cause for This Case**: PharmaLogic is a *manufacturing partner* for Ratio Therapeutics. The memory system recalled Ratio-related sources when validating PharmaLogic, and the validator filled PharmaLogic's row with Ratio's information instead of PharmaLogic's own pipeline.

---

### Example 2: Curium Row

**Expected**: Information about Curium's [^177Lu]Lu-PSMA-I&T product

**Actual**: Product name cell states: "The product name is consistently documented across high-authority sources and is also referred to as **PNT2002** in the context of **Point Biopharma's pipeline**"

- PNT2002 is POINT Biopharma's product, NOT Curium's
- Source #3 discusses "Lilly acquiring Point Biopharma" - completely irrelevant to Curium
- Both companies have 177Lu-PSMA-I&T products, but they are **separate, competing products**

---

### Example 3: Perspective Therapeutics Products

**Expected**: Separate information for [203Pb]VMT01 and [212Pb]VMT01

**Actual**: Multiple cells reference **Ratio Therapeutics' [68Ga]VMT02** product incorrectly across both Perspective Therapeutics rows

---

## Root Cause Analysis

### 1. **Memory Recall Over-Matching** (Primary Cause)

The Search Memory System is designed to avoid redundant searches by recalling previously fetched sources. However, the recall mechanism is **too broad**:

**Problem Flow**:
```
Validation Run 1: Validate Ratio Therapeutics, RTX-2358
  ↓
Search for "FAP-targeted radiopharmaceutical, actinium-225, sarcoma"
  ↓
Store results in memory with these keywords
  ↓
Validation Run 2: Validate PharmaLogic Holdings Corp., [unknown product]
  ↓
Memory recall: "FAP", "actinium-225" → Returns Ratio sources
  ↓
Validator uses Ratio sources to fill PharmaLogic row ❌
```

**Current Recall Logic** (from `SEARCH_MEMORY_SYSTEM.md`):

- **Stage 1**: Keyword pre-filter matches on query + all snippets
- **Stage 2**: Gemini selects most relevant sources
- **Stage 3**: Extract-then-verify assesses confidence

**Missing**: No company name/entity filtering in recall stage. The system recalls sources based on:
- Drug target (e.g., "PSMA", "FAP", "SSTR2")
- Drug mechanism (e.g., "alpha-emitter", "beta-emitter")
- Indication (e.g., "prostate cancer", "NETs")

But **not** by:
- Company name
- Specific product identifier
- Trial NCT number

---

### 2. **Row Identity Instability** (Contributing Cause)

**Historical Issue**: Table Maker previously allowed **all ID columns to change**, meaning:

```
Initial Table:
Row 1: Company A, Product X → Row ID: "Company A, Product X"

User modifies ID columns:
Row 1: Company B, Product Y → Row ID: "Company B, Product Y"

But memory still stores:
  row_key: "original_hash_for_Company_A"
  Validation sources from Company A's research
```

**Current State**:
- ✅ **Fixed**: At least one column must remain an ID column
- ⚠️ **Insufficient**: Even with one ID column fixed, if the *wrong* column is fixed (e.g., "Target / Indication" instead of "Company Name"), rows can still drift

**Risk**: If row identities change between validation runs, memory sources from the old row identity can pollute the new row.

---

### 3. **Citation-Aware Memory Accumulation** (Amplifying Factor)

From `SEARCH_MEMORY_SYSTEM.md`:

> Citations accumulate over time for the same source. Different validation runs with different entities add new citations:
> 1. **First validation** (Wyoming population): Extracts and stores citation with `hit_keywords: ["Wyoming", "population"]`
> 2. **Second validation** (Montana population): Same source, extracts and stores citation with `hit_keywords: ["Montana", "population"]`
> 3. **Third validation** (Wyoming population again): **Recalls cached citation** - no extraction needed

**Problem**: If a source URL is shared across multiple companies (e.g., a clinical trial registry page mentioning multiple competitors), the citation metadata doesn't track which *company* the citation belongs to—only which *keywords* matched.

**Example**:
```
URL: clinicaltrials.gov/search?term=PSMA
  Contains mentions of: Novartis, Bayer, Fusion Pharma, Curium

Memory stores:
  citations: [
    {quote: "Novartis 177Lu-PSMA-617", hit_keywords: ["PSMA", "prostate"]},
    {quote: "Bayer 225Ac-PSMA I&T", hit_keywords: ["PSMA", "prostate"]},
    ...
  ]

Later validation for Curium (PSMA product):
  recall_citations(url, required_keywords=["PSMA", "prostate"])
  → Returns ALL citations, including Novartis and Bayer quotes ❌
```

---

### 4. **URL-Based Recall Without Entity Context**

From `SEARCH_MEMORY_SYSTEM.md`:

> **URL-Based Recall** (`recall_by_urls(urls, required_keywords)`)
> - Direct URL lookup with keyword validation
> - Searches both `snippet` and `title` (case-insensitive)
> - Returns **ALL snippets** for each URL

**Problem**: If a URL contains information about multiple companies (common in industry overviews, acquisition news, competitive analyses), the memory returns *all* snippets from that URL without filtering by company.

**Example**:
```
URL: "Radiopharmaceutical Pipeline 2025 Overview"
  Contains:
    - Novartis Pluvicto
    - Bayer PSMA I&T
    - Point Biopharma PNT2002
    - Curium PSMA I&T

Memory stores all as separate snippets with _source_url pointing to same URL

Validation for Curium:
  recall_by_urls([overview_url], keywords=["PSMA"])
  → Returns snippets about ALL four companies ❌
```

---

### 5. **Fuzzy Row Matching Not Detected**

When rows are highly similar (same drug target, similar company names, overlapping indications), the validation system doesn't warn about potential confusion.

**Example**:
```
Row 1: Bayer, 225Ac-PSMA I&T
Row 2: Fusion Pharmaceuticals, FPI-2265 (225Ac-PSMA I&T)
Row 3: Curium, [^177Lu]Lu-PSMA-I&T
```

All three share:
- Same biological target (PSMA)
- Same indication (prostate cancer)
- Similar product chemistry

The validator doesn't receive any warning that these rows are easily confused, so memory sources from one can bleed into another.

---

## Design Principle: Table-Agnostic Solutions

**Critical Requirement**: All solutions must be **table-agnostic** and work with ANY table structure. The system cannot hardcode entity types like "company" or "product."

**How It Works**:

1. **ID Columns Define Row Identity**: The table metadata specifies which columns are ID columns (`is_id: true`). These columns uniquely identify each row.

2. **Extract ID Values from Row Context**: When validating a row, extract values from ALL ID columns. These become the row's identifying information.

3. **Filter Memory by ID Values**: Memory recall filters sources to only those mentioning the current row's ID values (not other rows' ID values).

4. **Detect Similar Rows by ID + Context**: Compare ID column values (should differ) and non-ID column values (may be similar) to detect confusable rows.

**Example**:

```python
# Radiopharmaceutical table
id_columns = ["Company Name", "Product / Candidate Name"]
row_1_id_values = ["Bayer", "225Ac-PSMA I&T"]
row_2_id_values = ["Curium", "[^177Lu]Lu-PSMA-I&T"]

# Finance table
id_columns = ["Ticker", "Company"]
row_1_id_values = ["AAPL", "Apple Inc."]
row_2_id_values = ["MSFT", "Microsoft Corp."]

# People table
id_columns = ["First Name", "Last Name", "Birth Year"]
row_1_id_values = ["John", "Smith", "1980"]
row_2_id_values = ["Jane", "Smith", "1980"]
```

In all cases, the system uses `id_values` to filter memory, regardless of what those values represent.

---

## Proposed Solutions

### Solution 1: ID-Column-Based Memory Filtering ⭐ **High Priority**

**Description**: Filter memory recall based on ID column values from the current row

**Key Principle**: This solution is **table-agnostic**. It works with ANY table structure by using the ID columns defined in the table metadata.

**Implementation**:

#### 1A. Extract ID Column Values from Row Context

```python
# In the_clone.py, before memory recall
def extract_row_identifiers(row: dict, table_columns: list) -> dict:
    """
    Extract ID column values from the current row.
    Works with any table structure - uses column metadata to identify IDs.

    Args:
        row: The row being validated
        table_columns: Column definitions with 'is_id' flags

    Returns:
        {
            'id_values': ['Bayer', '225Ac-PSMA I&T'],  # Values from ID columns
            'id_column_names': ['Company Name', 'Product / Candidate Name'],
            'row_id': 'Bayer, 225Ac-PSMA I&T'  # Combined for display
        }
    """
    identifiers = {
        'id_values': [],
        'id_column_names': [],
        'row_id': None
    }

    # Find ID columns from table metadata
    id_columns = [col for col in table_columns if col.get('is_id', False)]

    for col in id_columns:
        col_name = col['name']
        cell = row['cells'].get(col_name, {})
        value = cell.get('full_value', '')

        if value:
            identifiers['id_values'].append(value)
            identifiers['id_column_names'].append(col_name)

    # Build combined row_id for display
    identifiers['row_id'] = ', '.join(identifiers['id_values'])

    return identifiers
```

#### 1B. Filter Memory Sources by ID Column Values

```python
# In search_memory.py, modify recall()
async def recall(
    self,
    query: str,
    keywords: dict,
    row_identifiers: dict = None,  # NEW PARAMETER - ID column values
    **kwargs
) -> dict:
    """
    Recall memories with ID-based filtering.

    Args:
        row_identifiers: {
            'id_values': ['Bayer', '225Ac-PSMA I&T'],
            'id_column_names': ['Company Name', 'Product / Candidate Name'],
            'row_id': 'Bayer, 225Ac-PSMA I&T'
        }
    """
    # Stage 1: Keyword filter (existing)
    candidate_queries = self._keyword_filter(query, keywords)

    # Stage 1.5: ID-based filter (NEW)
    if row_identifiers and row_identifiers.get('id_values'):
        candidate_queries = self._id_based_filter(
            candidate_queries,
            row_identifiers
        )

    # Stage 2: Gemini selection (existing)
    selected_sources = await self._gemini_selection(candidate_queries)

    return selected_sources

def _id_based_filter(self, queries: list, row_identifiers: dict) -> list:
    """
    Filter queries to only those mentioning the current row's ID values.
    Table-agnostic: works with any ID columns.
    """
    filtered = []
    id_values = row_identifiers.get('id_values', [])

    if not id_values:
        return queries  # No filtering if no ID values

    for query_data in queries:
        # Aggregate all text from query and results
        text = f"{query_data['query_text']} {query_data['search_term']}"
        for result in query_data.get('results', []):
            text += f" {result.get('title', '')} {result.get('snippet', '')}"

        text_lower = text.lower()

        # Count how many ID values appear in the text
        matches = 0
        for id_value in id_values:
            if self._fuzzy_match(id_value, text_lower):
                matches += 1

        # Require at least one ID value to match (flexible threshold)
        # For stricter filtering, require ALL ID values: matches == len(id_values)
        if matches >= 1:
            # Store match score for ranking
            query_data['_id_match_score'] = matches / len(id_values)
            filtered.append(query_data)

    # Sort by ID match score (descending)
    filtered.sort(key=lambda q: q.get('_id_match_score', 0), reverse=True)

    return filtered

def _fuzzy_match(self, value: str, text: str) -> bool:
    """
    Check if ID value appears in text with fuzzy matching.
    Handles common variations: punctuation, formatting, case.
    """
    # Direct match
    if value.lower() in text:
        return True

    # Normalized match (remove special chars, extra spaces)
    normalized_value = re.sub(r'[^\w\s]', '', value.lower())
    normalized_value = re.sub(r'\s+', ' ', normalized_value).strip()

    normalized_text = re.sub(r'[^\w\s]', '', text)
    normalized_text = re.sub(r'\s+', ' ', normalized_text).strip()

    if normalized_value in normalized_text:
        return True

    # Token-based match (for multi-word IDs)
    # e.g., "Bayer AG" matches if both "bayer" and "ag" appear
    tokens = normalized_value.split()
    if len(tokens) > 1:
        # All significant tokens must appear
        significant_tokens = [t for t in tokens if len(t) > 2]  # Ignore short words
        if significant_tokens:
            return all(token in normalized_text for token in significant_tokens)

    return False
```

#### 1C. Update Citation Storage to Include Row Context

```python
# In search_memory_cache.py
@classmethod
def store_citations(
    cls,
    session_id: str,
    url: str,
    content: str,
    title: str,
    search_term: str,
    citations: list,
    source_type: str = "search",
    row_context: dict = None  # NEW PARAMETER - ID column values
):
    """
    Store citations with row context (ID column values).

    Args:
        row_context: {
            'id_values': ['Bayer', '225Ac-PSMA I&T'],
            'id_column_names': ['Company Name', 'Product / Candidate Name'],
            'row_id': 'Bayer, 225Ac-PSMA I&T'
        }
    """
    # ... existing storage logic ...

    # Add row context to each citation
    for citation in citations:
        if row_context:
            citation['_row_context'] = row_context

    # Store in memory structure
    # ...
```

#### 1D. Filter Citations by Row Context on Recall

```python
# In search_memory_cache.py, modify recall_citations()
@classmethod
def recall_citations(
    cls,
    session_id: str,
    url: str,
    required_keywords: list = None,
    row_identifiers: dict = None  # NEW PARAMETER - current row's ID values
) -> dict:
    """Recall cached citations with row-based filtering."""
    # ... existing lookup logic ...

    # Filter citations by row context match
    if row_identifiers and citations:
        filtered_citations = []
        id_values = row_identifiers.get('id_values', [])

        for citation in citations:
            row_ctx = citation.get('_row_context', {})
            stored_id_values = row_ctx.get('id_values', [])

            # Check if stored ID values match current row's ID values
            # Use fuzzy matching for flexibility
            match_score = cls._calculate_id_match_score(id_values, stored_id_values)

            # Accept if at least 50% of ID values match
            if match_score >= 0.5:
                citation['_match_score'] = match_score
                filtered_citations.append(citation)

        # Sort by match score
        filtered_citations.sort(key=lambda c: c.get('_match_score', 0), reverse=True)
        citations = filtered_citations

    return {
        'found': len(citations) > 0,
        'citations': citations,
        'needs_extraction': len(citations) == 0
    }

@classmethod
def _calculate_id_match_score(cls, current_ids: list, stored_ids: list) -> float:
    """
    Calculate similarity between two sets of ID values.
    Returns score from 0.0 (no match) to 1.0 (perfect match).
    """
    if not current_ids or not stored_ids:
        return 0.0

    matches = 0
    for current_id in current_ids:
        for stored_id in stored_ids:
            # Case-insensitive comparison
            if current_id.lower() == stored_id.lower():
                matches += 1
                break
            # Fuzzy match (e.g., "Bayer" matches "Bayer AG")
            elif current_id.lower() in stored_id.lower() or stored_id.lower() in current_id.lower():
                matches += 0.8  # Partial credit
                break

    # Normalize by the maximum possible matches
    return matches / len(current_ids)
```

**Benefits**:
- ✅ **Table-agnostic**: Works with ANY table structure (pharma, finance, people, etc.)
- ✅ Prevents cross-row contamination by filtering on ID column values
- ✅ Preserves cost savings from memory (avoids re-fetching same row's data)
- ✅ Backwards compatible (optional parameter, defaults to no filtering)
- ✅ Flexible matching (exact, fuzzy, token-based)

**Estimated Effort**: 2-3 days

---

### Solution 2: Row Identity Hash Stability ⭐ **High Priority**

**Description**: Ensure row identity remains stable even when cell values change

**Implementation**:

#### 2A. Enforce Immutable ID Column Combination

```python
# In table_maker configuration
IMMUTABLE_ID_COLUMNS = [
    "Company Name",
    "Product / Candidate Name"
]

def validate_table_structure(table: dict) -> tuple[bool, str]:
    """
    Ensure ID columns cannot be modified once set.

    Returns:
        (is_valid, error_message)
    """
    current_id_cols = [col['name'] for col in table['columns'] if col.get('is_id', False)]

    # Check if immutable columns are still ID columns
    missing = [col for col in IMMUTABLE_ID_COLUMNS if col not in current_id_cols]

    if missing:
        return False, f"Required ID columns cannot be removed: {missing}"

    return True, ""
```

#### 2B. Generate Stable Row Keys from ID Columns Only

```python
# In validation code
def generate_row_key(row: dict, id_columns: list) -> str:
    """
    Generate stable row key from ID columns only.

    Only ID column values contribute to the hash, so changing
    non-ID columns doesn't change row identity.
    """
    id_values = []

    for col_name in sorted(id_columns):  # Sort for consistency
        cell = row['cells'].get(col_name, {})
        id_values.append(f"{col_name}:{cell.get('full_value', '')}")

    # Hash the ID values
    key_string = '|'.join(id_values)
    return hashlib.sha256(key_string.encode()).hexdigest()
```

#### 2C. Detect Row Identity Changes

```python
# In validation pipeline
def detect_row_identity_changes(old_table: dict, new_table: dict) -> list:
    """
    Detect if row identities have changed.

    Returns list of warnings about changed rows.
    """
    warnings = []

    old_id_cols = [col['name'] for col in old_table['columns'] if col.get('is_id')]
    new_id_cols = [col['name'] for col in new_table['columns'] if col.get('is_id')]

    if set(old_id_cols) != set(new_id_cols):
        warnings.append({
            'severity': 'ERROR',
            'message': f"ID columns changed: {old_id_cols} → {new_id_cols}",
            'impact': "Row identities will be regenerated, breaking memory linkage"
        })

    # Check if ID column values changed for existing rows
    for old_row in old_table['rows']:
        old_key = old_row['row_key']

        # Find matching row in new table by key
        new_row = next((r for r in new_table['rows'] if r['row_key'] == old_key), None)

        if new_row:
            # Check if ID column values changed
            for col_name in old_id_cols:
                old_val = old_row['cells'].get(col_name, {}).get('full_value')
                new_val = new_row['cells'].get(col_name, {}).get('full_value')

                if old_val != new_val:
                    warnings.append({
                        'severity': 'WARNING',
                        'row_key': old_key,
                        'message': f"ID column '{col_name}' changed: '{old_val}' → '{new_val}'",
                        'impact': "This row's identity has changed. Memory from previous identity may not be recalled."
                    })

    return warnings
```

**Benefits**:
- ✅ Prevents row identity drift over time
- ✅ Ensures memory is always associated with correct row
- ✅ Provides warnings when row structure changes

**Estimated Effort**: 1-2 days

---

### Solution 3: Fuzzy Match Deduplication Prompt ⭐ **Medium Priority**

**Description**: When validating a row, detect similar rows in the table and warn the validator to be careful about row disambiguation

**Key Principle**: **Table-agnostic** - compares rows based on ID column values and other column similarities, not hardcoded entity types.

**Implementation**:

#### 3A. Detect Similar Rows (General Purpose)

```python
# In validation pipeline
def find_similar_rows(
    target_row: dict,
    all_rows: list,
    table_columns: list,
    similarity_threshold: float = 0.7
) -> list:
    """
    Find rows similar to target row that could be confused.
    Works with any table structure by comparing ID and non-ID columns.

    Args:
        target_row: The row being validated
        all_rows: All rows in the table
        table_columns: Column definitions with 'is_id' flags
        similarity_threshold: Minimum similarity to flag (0.0-1.0)

    Returns:
        List of similar rows with similarity scores
    """
    from difflib import SequenceMatcher

    # Identify ID columns and non-ID columns
    id_columns = [col['name'] for col in table_columns if col.get('is_id', False)]
    non_id_columns = [col['name'] for col in table_columns if not col.get('is_id', False)]

    # Get target row's ID values
    target_id_values = [
        target_row['cells'].get(col, {}).get('full_value', '')
        for col in id_columns
    ]

    similar_rows = []

    for row in all_rows:
        if row['row_key'] == target_row['row_key']:
            continue  # Skip self

        # Get this row's ID values
        other_id_values = [
            row['cells'].get(col, {}).get('full_value', '')
            for col in id_columns
        ]

        # Calculate ID similarity
        id_similarities = []
        for i, col in enumerate(id_columns):
            target_val = target_id_values[i] if i < len(target_id_values) else ''
            other_val = other_id_values[i] if i < len(other_id_values) else ''

            if target_val and other_val:
                sim = SequenceMatcher(None, target_val, other_val).ratio()
                id_similarities.append((col, sim))

        # Calculate non-ID column similarity (contextual columns)
        context_similarities = []
        for col_name in non_id_columns[:5]:  # Check first 5 non-ID columns
            target_val = target_row['cells'].get(col_name, {}).get('full_value', '')
            other_val = row['cells'].get(col_name, {}).get('full_value', '')

            if target_val and other_val:
                sim = SequenceMatcher(None, target_val, other_val).ratio()
                context_similarities.append((col_name, sim))

        # Check if rows are confusable:
        # 1. ID columns are different (not exact match)
        # 2. But non-ID columns are similar (high contextual similarity)
        ids_different = not all(sim >= 0.95 for _, sim in id_similarities)
        context_similar = any(sim >= 0.7 for _, sim in context_similarities) if context_similarities else False

        if ids_different and context_similar:
            # Calculate overall similarity score
            avg_context_sim = sum(sim for _, sim in context_similarities) / len(context_similarities) if context_similarities else 0.0

            if avg_context_sim >= similarity_threshold:
                similar_rows.append({
                    'row_key': row['row_key'],
                    'id_values': other_id_values,
                    'id_columns': id_columns,
                    'id_similarities': id_similarities,
                    'context_similarities': context_similarities,
                    'overall_similarity': avg_context_sim
                })

    # Sort by overall similarity (descending)
    similar_rows.sort(key=lambda r: r['overall_similarity'], reverse=True)

    return similar_rows
```

#### 3B. Add Deduplication Warning to Validation Prompt (Generic)

```python
# In validation prompt generation
def generate_validation_prompt(
    row: dict,
    column: dict,
    all_rows: list,
    table_columns: list,
    **kwargs
) -> str:
    """Generate validation prompt with fuzzy match warning if needed."""

    # Get ID column values for this row
    id_columns = [col for col in table_columns if col.get('is_id', False)]
    row_id_display = ', '.join([
        f"{col['name']}: {row['cells'].get(col['name'], {}).get('full_value', 'N/A')}"
        for col in id_columns
    ])

    prompt = f"""
Validate the following cell value:

**Table Context (Row Identity)**:
{row_id_display}

**Column**: {column['name']}
**Current Value**: {row['cells'].get(column['name'], {}).get('full_value', '')}
**Validation Strategy**: {column['notes']}

"""

    # Check for similar rows
    similar_rows = find_similar_rows(
        row,
        all_rows,
        table_columns,
        similarity_threshold=0.7
    )

    if similar_rows:
        prompt += f"""
⚠️ **DEDUPLICATION WARNING**: This table contains {len(similar_rows)} other row(s) with similar characteristics but different identities:

"""
        for i, similar in enumerate(similar_rows[:3], 1):  # Show top 3
            # Display similar row's ID values
            similar_id_display = ' | '.join([
                f"{id_columns[j]['name']}: {similar['id_values'][j]}"
                for j in range(len(id_columns))
                if j < len(similar['id_values'])
            ])

            prompt += f"""
{i}. {similar_id_display}
   Overall Similarity: {similar['overall_similarity']:.0%}
"""

            # Show which columns are similar
            high_sim_cols = [col for col, sim in similar['context_similarities'] if sim >= 0.7]
            if high_sim_cols:
                prompt += f"   Similar columns: {', '.join(high_sim_cols)}\n"

            prompt += "\n"

        # Extract ID column names and values for current row
        id_requirements = []
        for col in id_columns:
            value = row['cells'].get(col['name'], {}).get('full_value', '')
            if value:
                id_requirements.append(f'"{value}"')

        prompt += f"""
⚠️ **CRITICAL**: When researching and validating this cell:
1. **Always specify the identifying information** ({', '.join(id_requirements)}) in your search queries
2. **Verify that sources explicitly mention** these specific identifiers
3. **Reject sources that discuss the similar rows listed above** unless they're discussing relationships/collaborations between them
4. **If unsure whether a source applies to this row or a similar row**, mark confidence as MEDIUM or LOW

Do NOT use information about the similar rows listed above unless it's explicitly stated to apply to this specific row.

"""

    prompt += """
Please provide your validation assessment.
"""

    return prompt
```

#### 3C. Add Similar Rows to Debug Metadata

```python
# In validation result metadata
validation_result = {
    'display_value': '...',
    'full_value': '...',
    'confidence': 'HIGH',
    'comment': {
        'validator_explanation': '...',
        'sources': [...],
        'similar_rows_detected': [  # NEW FIELD
            {
                'company': 'Competitor Corp',
                'product': 'Similar-Product-123',
                'similarity_score': 0.85,
                'warning_shown': True
            }
        ]
    }
}
```

**Benefits**:
- ✅ Explicitly warns validator about confusable rows
- ✅ Reduces false positive matches from memory
- ✅ Creates audit trail of similar rows for debugging
- ✅ Improves validation quality by prompting for company-specific verification

**Estimated Effort**: 2 days

---

### Solution 4: ID-Based Search Term Enhancement 🔵 **Medium Priority**

**Description**: Force all search queries to include ID column values as required terms

**Key Principle**: **Table-agnostic** - uses ID column values (whatever they are) to filter search results.

**Implementation**:

#### 4A. Inject ID Column Values into Search Terms

```python
# In the_clone.py, modify search execution
async def execute_search(
    search_terms: list,
    row_context: dict,
    table_columns: list,
    **kwargs
) -> dict:
    """
    Execute searches with ID-based filtering.
    Works with any table structure.
    """

    # Extract ID column values from row context
    id_columns = [col for col in table_columns if col.get('is_id', False)]
    id_values = []

    for col in id_columns:
        value = row_context.get('cells', {}).get(col['name'], {}).get('full_value', '')
        if value:
            id_values.append(value)

    if id_values:
        # Add ID values to each search term
        enhanced_terms = []
        for term in search_terms:
            # Add primary ID value (usually first ID column)
            primary_id = id_values[0]
            enhanced_term = f"{term} +\"{primary_id}\""
            enhanced_terms.append(enhanced_term)

        logger.info(f"[SEARCH] Enhanced search terms with ID filter: {enhanced_terms}")
        logger.info(f"[SEARCH] ID values for this row: {id_values}")
        search_terms = enhanced_terms

    # Execute searches
    results = await perplexity_search(search_terms, **kwargs)

    return results
```

#### 4B. Add ID Filter to Search API

```python
# In perplexity API wrapper
async def perplexity_search(
    query: str,
    required_terms: list = None,  # NEW PARAMETER - ID values
    **kwargs
) -> dict:
    """
    Search with required terms that must appear in results.

    Args:
        query: Search query
        required_terms: List of ID values that should appear in results
                       e.g., ['Bayer', '225Ac-PSMA I&T']
    """
    # Build query with required terms
    if required_terms:
        # Use quoted phrases for exact matching
        quoted_terms = [f'"{term}"' for term in required_terms]
        query = f"{query} {' '.join(quoted_terms)}"

    # Call Perplexity API
    response = await perplexity_client.search(query, **kwargs)

    # Post-filter results to ensure at least one required term present
    # (Flexible: don't require ALL terms, as some sources may use variations)
    if required_terms:
        filtered_results = []
        for result in response['results']:
            text = f"{result.get('snippet', '')} {result.get('title', '')}".lower()

            # Check if at least one ID value appears
            match_found = any(
                term.lower() in text
                for term in required_terms
            )

            if match_found:
                filtered_results.append(result)

        response['results'] = filtered_results

    return response
```

#### 4C. Configurable Strictness

```python
# In validation configuration
class IDFilterConfig:
    """Configuration for ID-based search filtering."""

    # How many ID values must match in search results?
    MATCH_STRATEGY = "at_least_one"  # Options: "all", "at_least_one", "primary_only"

    # Which ID columns to use for filtering?
    ID_PRIORITY = "first"  # Options: "first", "all", "most_specific"

    # Enable/disable ID filtering
    ENABLED = True

async def execute_search_with_config(search_terms: list, row_context: dict, config: IDFilterConfig):
    """Execute search with configurable ID filtering."""

    if not config.ENABLED:
        return await perplexity_search(search_terms)

    # Extract ID values based on priority
    id_values = extract_id_values(row_context, strategy=config.ID_PRIORITY)

    # Apply filtering based on match strategy
    required_terms = id_values if config.MATCH_STRATEGY == "all" else id_values[:1]

    return await perplexity_search(search_terms, required_terms=required_terms)
```

**Benefits**:
- ✅ **Table-agnostic**: Uses ID columns from any table structure
- ✅ Forces search results to be row-specific
- ✅ Reduces noise from similar rows
- ✅ Works at search time (before memory storage)
- ✅ Configurable strictness (can adjust filtering intensity)

**Drawbacks**:
- ⚠️ May reduce search result quantity (fewer matches)
- ⚠️ May miss valid sources that don't mention ID values explicitly (e.g., generic industry reports)

**Recommendation**: Start with flexible filtering ("at_least_one" strategy) and tighten if cross-contamination persists.

**Estimated Effort**: 1 day

---

### Solution 5: Memory Isolation by Row Context 🔵 **Low Priority**

**Description**: Create separate memory namespaces for different row contexts

**Implementation**:

```python
# In search_memory.py
class SearchMemory:
    def __init__(self, session_id: str, context_namespace: str = None):
        """
        Initialize memory with optional context namespace.

        Args:
            context_namespace: Isolate memory by context, e.g., "Bayer_225Ac-PSMA"
        """
        self.session_id = session_id
        self.context_namespace = context_namespace
        self.memory_key = self._build_memory_key()

    def _build_memory_key(self) -> str:
        """Build S3 key with namespace isolation."""
        if self.context_namespace:
            # Store in namespace-specific location
            return f"results/{domain}/{email}/{session_id}/memory_{self.context_namespace}.json"
        else:
            # Store in shared location
            return f"results/{domain}/{email}/{session_id}/agent_memory.json"

# Usage in validation
memory = SearchMemory(
    session_id=session_id,
    context_namespace=f"{company_name}_{product_name}".replace(' ', '_')
)
```

**Benefits**:
- ✅ Complete isolation between row contexts
- ✅ Zero cross-contamination risk

**Drawbacks**:
- ⚠️ Loses memory sharing benefits (same sources fetched multiple times)
- ⚠️ Increases storage costs (multiple memory files per session)
- ⚠️ Reduces cost savings from memory system

**Estimated Effort**: 1 day

**Recommendation**: Only implement if other solutions insufficient

---

## Implementation Priority

### Phase 1: Critical Fixes (Week 1)

1. **Solution 1A-1B**: Entity-aware memory filtering ⭐
   - Prevents immediate cross-contamination
   - Preserves memory benefits

2. **Solution 2A-2B**: Row identity stability ⭐
   - Fixes root cause of row drift
   - Prevents future contamination

### Phase 2: Prevention (Week 2)

3. **Solution 3**: Fuzzy match deduplication prompt ⭐
   - Improves validation quality
   - Reduces false positive recalls

4. **Solution 1C-1D**: Citation entity metadata
   - Enhances entity filtering
   - Improves long-term memory accuracy

### Phase 3: Hardening (Week 3+)

5. **Solution 4**: Company-specific search terms 🔵
   - Additional safety layer
   - Test impact on result quality first

6. **Solution 2C**: Row identity change detection
   - Monitoring and debugging
   - User warnings

### Phase 4: Nuclear Option (If Needed)

7. **Solution 5**: Memory isolation by row context
   - Only if other solutions insufficient
   - Evaluate cost/benefit tradeoff

---

## Testing Strategy

### Test Cases (Table-Agnostic)

#### Test 1: Similar Rows, Different ID Values

**Setup** (works with ANY table):
- **ID Columns**: Column A, Column B
- Row 1: ID values = ["Value1-A", "Value1-B"]
- Row 2: ID values = ["Value2-A", "Value2-B"]
- Row 3: ID values = ["Value3-A", "Value3-B"]
- **Non-ID Columns**: All three rows share similar values (e.g., same category, similar descriptions)

**Example (Radiopharmaceutical Table)**:
- Row 1: ["Bayer", "225Ac-PSMA I&T"]
- Row 2: ["Fusion Pharmaceuticals", "FPI-2265 (225Ac-PSMA I&T)"]
- Row 3: ["Curium", "[^177Lu]Lu-PSMA-I&T"]
- Common non-ID values: All target PSMA, all for prostate cancer

**Test**:
1. Validate Row 1 - store memory with row_context = ["Value1-A", "Value1-B"]
2. Validate Row 2 - should NOT recall Row 1's sources (ID values differ)
3. Validate Row 3 - should NOT recall Row 1 or Row 2's sources

**Expected Result**:
- Each row uses ID-specific sources only
- Memory filter: `row_identifiers['id_values'] must match`
- No cross-contamination in validation results

---

#### Test 2: Partner/Relationship Rows

**Setup**:
- Row 1: ID = ["Developer Corp", "Product X"]
- Row 2: ID = ["Manufacturing Partner Corp", "Product Y"]
- Row 2's "Partnerships" column mentions Developer Corp

**Test**:
1. Validate Row 1 (developer) - store memory
2. Validate Row 2 (partner) - should:
   - Use Row 2's own ID values for most columns
   - Only mention Row 1's ID values in relationship columns (e.g., "Partnerships")

**Expected Result**:
- Row 2's product description columns use Row 2-specific sources
- Row 2's partnership column can mention Row 1 (legitimate relationship)
- ID-based filtering distinguishes between "this row's data" vs "related row's data"

---

#### Test 3: Row Identity Change

**Setup**:
- **Initial**: Row with ID columns = ["Value-A", "Value-B"]
- **User modifies** ID column to = ["Value-C", "Value-D"]

**Test**:
1. Validate with original identity ["Value-A", "Value-B"]
2. User changes ID column values to ["Value-C", "Value-D"]
3. Re-validate with new identity

**Expected Result**:
- System detects identity change via row_key hash
- Warning shown to user: "Row identity changed, memory linkage broken"
- Memory from old identity (["Value-A", "Value-B"]) NOT used for new identity (["Value-C", "Value-D"])
- New validation fetches fresh sources for new identity

---

#### Test 4: Fuzzy Match Warning Trigger

**Setup**:
- Row 1: ID = ["EntityA", "Product-123"]
- Row 2: ID = ["EntityB", "Product-124"]
- Non-ID columns have 80% similarity (e.g., same category, similar descriptions)

**Test**:
1. Validate Row 2

**Expected Result**:
- Fuzzy match detection finds Row 1 as similar (80% similarity)
- Validation prompt includes warning:
  ```
  ⚠️ DEDUPLICATION WARNING: This table contains 1 other row with similar characteristics:
  1. EntityA | Product-123 (Overall Similarity: 80%)

  CRITICAL: Always specify "EntityB" and "Product-124" in your search queries.
  ```
- Validator is warned to be careful about row disambiguation

---

### Validation Metrics

Track these metrics to measure fix effectiveness:

```python
metrics = {
    'cross_contamination_rate': {
        'definition': 'Percentage of rows with sources mentioning wrong company',
        'target': '< 1%',
        'current': '~15%'  # Based on observed data
    },
    'entity_filter_effectiveness': {
        'definition': 'Percentage of recalled sources that match required entity',
        'target': '> 95%',
        'current': 'TBD'
    },
    'memory_hit_rate': {
        'definition': 'Percentage of validations that use memory successfully',
        'target': '> 40%',  # Should not decrease significantly
        'current': '~50%'
    },
    'false_positive_recalls': {
        'definition': 'Recalls that returned sources for wrong entity',
        'target': '< 5%',
        'current': 'TBD'
    }
}
```

---

## Monitoring and Alerts

### Add Contamination Detection

```python
# In validation metadata
def detect_cross_contamination(row: dict, validation_result: dict) -> dict:
    """Detect potential cross-contamination in validation result."""

    expected_company = row['cells'].get('Company Name', {}).get('full_value', '')

    warnings = []

    # Check all sources for mentions of other companies
    for source in validation_result.get('comment', {}).get('sources', []):
        text = f"{source.get('title', '')} {source.get('snippet', '')}"

        # Look for other company names in sources
        other_companies_mentioned = find_company_names_in_text(text)
        other_companies_mentioned = [c for c in other_companies_mentioned if c != expected_company]

        if other_companies_mentioned:
            warnings.append({
                'type': 'POTENTIAL_CONTAMINATION',
                'source_url': source.get('url'),
                'expected_company': expected_company,
                'mentioned_companies': other_companies_mentioned,
                'severity': 'HIGH' if len(other_companies_mentioned) > 2 else 'MEDIUM'
            })

    return {
        'contamination_detected': len(warnings) > 0,
        'warnings': warnings
    }
```

### CloudWatch Alerts

```python
# Add metric for contamination detection
cloudwatch.put_metric_data(
    Namespace='Validation/Quality',
    MetricData=[
        {
            'MetricName': 'CrossContaminationDetected',
            'Value': 1 if contamination_detected else 0,
            'Unit': 'Count',
            'Dimensions': [
                {'Name': 'SessionId', 'Value': session_id},
                {'Name': 'TableName', 'Value': table_name}
            ]
        }
    ]
)
```

---

## Rollout Plan

### Week 1: Entity Filtering + Row Stability

**Deploy**:
- Solution 1A-1B (entity-aware filtering)
- Solution 2A-2B (row identity stability)

**Test**:
- Run validation on known problematic cases
- Monitor contamination detection metrics

**Rollback Trigger**:
- Memory hit rate drops below 30%
- False negative rate increases significantly

---

### Week 2: Fuzzy Match Warning

**Deploy**:
- Solution 3 (fuzzy match deduplication prompt)

**Test**:
- Review validation quality on similar rows
- Check if validators follow deduplication warnings

**Rollback Trigger**:
- Validation costs increase > 20%
- User feedback indicates prompts too verbose

---

### Week 3: Citation Entity Metadata

**Deploy**:
- Solution 1C-1D (entity metadata in citations)

**Test**:
- Verify citation recalls are entity-specific
- Monitor false positive recall rate

---

### Week 4: Monitoring & Optional Hardening

**Deploy**:
- Solution 2C (row identity change detection)
- Solution 4 (company-specific search) - optional, test first

**Monitor**:
- All contamination metrics
- Memory effectiveness
- Cost impact

---

## Success Criteria

The issue is resolved when:

1. ✅ **Cross-contamination rate < 1%**: Less than 1% of validated rows contain information about wrong company
2. ✅ **Entity filter effectiveness > 95%**: Memory recalls return entity-specific sources > 95% of the time
3. ✅ **Memory hit rate > 40%**: Memory system still provides cost savings on > 40% of validations
4. ✅ **Zero critical contamination**: No cases like PharmaLogic/Ratio (entire row contaminated)
5. ✅ **Row identity stable**: Row keys don't change unless user explicitly modifies ID columns

---

## Appendix: Contamination Statistics

From analysis of `theranostic_CI_metadata.json`:

| Statistic | Value |
|-----------|-------|
| Total rows analyzed | ~100 |
| Rows with contamination detected | ~25 |
| Most severely contaminated row | PharmaLogic Holdings Corp. (10 columns) |
| Most common contamination pattern | PSMA-targeting products (16 companies, multiple cross-refs) |
| Average contamination per affected row | 3-4 columns |
| Companies most frequently confused | Novartis variants, PSMA product developers, Ratio/PharmaLogic |

---

## References

- `docs/SEARCH_MEMORY_SYSTEM.md` - Current memory system architecture
- `docs/CITATION_AWARE_MEMORY_PLAN.md` - Citation-aware memory design
- `theranostic_CI_metadata.json` - Contaminated validation output analyzed
- `src/the_clone/search_memory.py` - Memory recall implementation
- `src/the_clone/search_memory_cache.py` - Memory cache implementation
