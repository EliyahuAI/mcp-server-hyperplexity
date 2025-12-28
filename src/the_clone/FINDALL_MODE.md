# FindAll Mode Documentation

## Overview

Findall mode is a specialized search mode for **ENTITY IDENTIFICATION** - finding and listing as many distinct instances, examples, or entities as possible that match query criteria.

## Usage

```python
from the_clone.the_clone import TheClone2Refined

clone = TheClone2Refined()

# Explicit findall parameter
result = await clone.query(
    prompt="phase3 oncology drugs",
    findall=True,  # Enable findall mode
    schema=my_table_schema,  # Optional: structured output
    provider='deepseek'
)
```

## Architecture

### 1. Dedicated Prompt & Schema
- **Prompt:** `prompts/findall_decision.md` - Focused on entity identification
- **Schema:** `get_findall_schema()` - Simplified (no decision/breadth/depth fields)
- **Tier:** Always tier2 (forced, no expensive tier4)

### 2. Search Strategy: Independent Domains

**Key Principle:** 5 searches target DIFFERENT sources to minimize overlap and maximize entity coverage.

**Domain Independence Strategies:**

| Strategy | Description | Example (Oncology Drugs) |
|----------|-------------|--------------------------|
| **Subcategory** | Break into distinct subcategories | lung cancer, breast cancer, immunotherapy, targeted therapy, chemotherapy |
| **Temporal** | Split by time periods | 2024-2025, 2022-2023, 2020-2021, FDA approved 2024, clinical trials database |
| **Geographic** | Target different regions | US FDA, European EMA, Asian trials, global trials, Australia approvals |
| **Institutional** | Target specific databases/sources | ClinicalTrials.gov, FDA approvals, NIH trials, ASCO presentations, pharma pipelines |
| **Demographic** | Segment by population | pediatric, elderly, rare cancers, common cancers, biomarker-based |
| **Mixed** | Combine strategies | lung cancer 2024, breast cancer EMA 2023 |

### 3. Execution Flow

```
findall=True parameter
         |
         v
[Dedicated findall_decision.md prompt]
  "Generate 5 search terms for INDEPENDENT DOMAINS"
         |
         v
[LLM generates 5 diverse terms]
  Example: clinical trials, targeted therapy, patient assistance,
           immunotherapy pipeline, cost-effectiveness
         |
         v
[5 searches × 20 results = 100 sources]
  Search 1: 20 results → different sources
  Search 2: 20 results → different sources (minimal overlap)
  ...
         |
         v
[Triage all 5 searches in PARALLEL]
         |
         v
[Group sources by search index]
         |
         v
[5 parallel batch extractions]
  Each search: extract_from_sources_batch(all 20 sources)
  All quality levels accepted (min_p=0.65 warning only)
         |
         v
[~100-200 snippets total]
         |
         v
[Entity-focused synthesis with context='findall']
  "Extract ALL entities, create comprehensive table/list"
         |
         v
Structured output with maximum entity coverage
```

### 4. Synthesis: Entity Identification Mode

**Context:** `'findall'` triggers special synthesis guidance from `config.py`

**Synthesis Instructions:**
- Extract EVERY entity mentioned across all snippets
- Create comprehensive tables or lists
- Maximize entity count (not selective)
- Include ALL relevant instances from all 5 searches
- Use structured format (table preferred)
- Deduplicate identical entities
- Include specific details for each entity

**Source Handling:**
- Accepts ALL quality levels (p >= 0.0)
- Warning threshold at p < 0.65
- Cross-references entities across searches
- Uses all 5 independent domain searches

## Configuration

**Strategy:** `findall_breadth` in `strategy_config.json`
```json
{
  "breadth": "findall",
  "depth": "shallow",
  "sources_per_batch": 20,
  "max_results_per_search": 20,
  "min_p_threshold": 0.65,  // Warning level, not filter
  "accept_all_quality_levels": true,  // Disable quality filtering
  "bypass_global_source_limit": true,  // Allow 100 sources
  "batch_extraction": true
}
```

**Context Mapping:** `'findall_breadth'` → `context='findall'` for synthesis

## Example Results

**Query:** "phase3 oncology drugs"

**5 Diverse Search Terms Generated:**
1. phase 3 clinical trials oncology drugs ← Clinical trials domain
2. targeted therapy oncology drugs ← Mechanism-specific domain
3. oncology drugs patient assistance programs ← Access/cost domain
4. immunotherapy oncology drugs pipeline 2024 ← Innovation domain
5. cost-effectiveness analysis phase 3 oncology drugs ← Economics domain

**Execution:**
- 100 search results (5 × 20)
- 96 sources ranked
- 168 snippets extracted (all quality levels)
- 9 drugs identified in table format
- Cost: ~$0.15-0.25
- Time: ~90-120s

**Keywords Generated (domain-appropriate):**
- Positive: FDA approval, RCT, survival rate, ORR, biomarker, ASCO, ESMO
- Negative: alternative medicine, home remedies, cancer astrology, pet oncology
- Academic: true

## Key Features

✅ **Explicit parameter** - `findall=True` (not keyword detection)
✅ **Dedicated prompt & schema** - Optimized for entity identification
✅ **Domain independence** - 5 searches target different sources
✅ **LLM-driven diversity** - No hardcoded expansions
✅ **Entity-focused synthesis** - Maximize entity count, not narrative
✅ **All quality levels** - Maximum coverage (warning at p<0.65)
✅ **Forced tier2** - Cost-effective synthesis
✅ **Parallel execution** - All 5 searches process simultaneously
✅ **Structured output** - Tables/lists for scannability

## Files Modified

1. `initial_decision.py` - Added `findall_mode` parameter
2. `prompts/findall_decision.md` - New dedicated prompt
3. `initial_decision_schemas.py` - Added `get_findall_schema()`
4. `strategy_config.json` - Added `findall_breadth` strategy
5. `strategy_loader.py` - Mapped `('findall', 'shallow')` → `findall_breadth`
6. `the_clone.py` - Added `findall` parameter, parallel extraction logic
7. `snippet_extractor_streamlined.py` - Added `accept_all_quality_levels` parameter
8. `config.py` - Added `'findall'` synthesis context

## Testing

```bash
cd src/the_clone
python.exe test_findall_with_schema.py
```

Results saved to: `test_results/findall_oncology_TIMESTAMP/`
