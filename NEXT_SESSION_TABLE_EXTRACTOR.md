# Next Session: Standalone Table Extractor

## Goal

Build a standalone table extractor that can extract complete tables from URLs with:
- Iterative extraction when more rows are available
- Fallback strategies when extraction fails
- Citation quality from background research
- Full integration with tablemaker

## Requirements

### Core Functionality

1. **URL-based extraction**
   - Fetch HTML from specific URL
   - Parse for table structures (HTML tables, lists, divs)
   - Extract with Gemini 2.0 Flash (1M token input, 8K output)

2. **Iterative extraction for large tables**
   - Detect when table is incomplete (more_rows_available flag)
   - Provide already-extracted rows as context
   - Ask for remaining rows
   - Append to existing table
   - Continue until complete or max iterations

3. **Fallback strategies**
   - Strategy 1: Direct HTML extraction
   - Strategy 2: Search-based (the_clone findall)
   - Strategy 3: Pagination detection and multi-page extraction
   - Strategy 4: Partial extraction with "more_rows_available" flag

4. **Citation quality tracking**
   - URL citation quality from background research
   - Source-level p-scores based on domain authority
   - Preserve through tablemaker → validator
   - Excel comments with confidence levels

### Integration Points

**Tablemaker Flow:**
```
Background Research (the-clone)
  → Identifies URLs with tables
  → Provides URL quality assessment
         |
         v
Standalone Table Extractor (NEW)
  → Fetches URL
  → Extracts table iteratively
  → Returns with confidence/citations
         |
         v
Column Definition
  → Uses extracted tables
         |
         v
Row Discovery (the-clone + findall)
  → Fills gaps
         |
         v
Validator
  → Excel with comments (confidence + sources)
```

## Design Specifications

### File Structure

**New File:** `src/shared/table_extractor.py`

```python
class TableExtractor:
    """Standalone table extractor with iteration support."""

    async def extract_table(
        self,
        url: str,
        table_name: str,
        expected_columns: List[str],
        estimated_rows: int = None,
        url_quality: float = 0.85,  # From background research
        max_iterations: int = 5
    ) -> Dict:
        """
        Extract complete table from URL with iteration.

        Returns:
        {
            'success': bool,
            'url': str,
            'rows': List[Dict],  # Complete table
            'rows_extracted': int,
            'extraction_complete': bool,
            'iterations_used': int,
            'confidence': str,  # HIGH/MEDIUM/LOW (from url_quality)
            'citations': List[Dict],  # URL + snippets
            'strategy_used': str,  # 'html_direct', 'search_based', 'iterative'
            'error': Optional[str]
        }
        """
```

### Iteration Logic

```python
async def _extract_iteratively(self, url, schema, context_rows=None):
    """Extract table in iterations."""

    iteration = 1
    all_rows = context_rows or []

    while iteration <= max_iterations:
        # Build prompt with context
        if all_rows:
            prompt = f"""Continue extracting from {url}.

Already extracted {len(all_rows)} rows:
{json.dumps(all_rows[:5])}...

Extract the REMAINING rows not yet captured.
Start from row {len(all_rows) + 1}."""
        else:
            prompt = f"Extract complete table from {url}"

        # Extract
        result = await extract_with_gemini(prompt, schema)

        # Append new rows
        new_rows = result.get('rows', [])
        all_rows.extend(new_rows)

        # Check if complete
        if result.get('extraction_complete'):
            break

        if len(new_rows) == 0:
            break

        iteration += 1

    return all_rows
```

### Fallback Strategy Chain

```python
async def extract_table(self, url, ...):
    """Try strategies in order until success."""

    # Strategy 1: Direct HTML extraction
    result = await self._try_html_extraction(url, ...)
    if result['success'] and result['rows_extracted'] >= estimated_rows * 0.8:
        return result

    # Strategy 2: Iterative extraction (if partial success)
    if result['rows_extracted'] > 0:
        result = await self._extract_iteratively(url, ...)
        if result['extraction_complete']:
            return result

    # Strategy 3: Search-based extraction (the_clone findall)
    result = await self._try_search_extraction(url, ...)
    if result['success']:
        return result

    # Strategy 4: Return partial with flag
    return {
        'success': True,
        'rows': partial_rows,
        'extraction_complete': False,
        'more_rows_available': True,
        'strategy_used': 'partial_extraction'
    }
```

## Testing Plan

### Test Cases

1. **Wikipedia (static HTML, 241 rows)**
   - Test direct extraction
   - Test iteration for complete coverage
   - Verify all rows extracted

2. **Forbes (JavaScript, 50 rows)**
   - Test HTML extraction (expected to fail)
   - Test search-based fallback
   - Verify 49+ athletes found

3. **Paginated list (100+ rows)**
   - Test pagination detection
   - Test multi-page extraction
   - Verify all pages combined

4. **Citation quality integration**
   - Extract with url_quality=0.95
   - Verify confidence=HIGH
   - Verify Excel comments created

## Files to Create

1. `src/shared/table_extractor.py` - Main extractor class
2. `src/shared/html_table_parser.py` - HTML parsing utilities
3. `test_standalone_table_extractor.py` - Comprehensive tests

## Files to Modify

1. `src/lambdas/interface/actions/table_maker/table_maker_lib/table_extraction_handler.py`
   - Use TableExtractor instead of direct AI calls
   - Pass url_quality from background research
   - Preserve confidence through to validator

2. `src/shared/excel_report_qc_unified.py`
   - Use clone_to_validator_bridge for comments
   - Preserve citations after QC review

## Success Criteria

- ✓ Extract Wikipedia table (200+ rows) completely
- ✓ Handle Forbes-type JS sites gracefully (fallback)
- ✓ Iteration works (provide partial → get rest → append)
- ✓ Confidence levels correct (based on URL quality)
- ✓ Citations in Excel comments all the way through
- ✓ QC doesn't break confidence/citations

## Current Session Accomplishments

✅ Findall mode (49 athletes)
✅ Confidence mapping (p-scores → HIGH/MEDIUM/LOW)
✅ Tablemaker integration (findall enabled)
✅ HTML extraction proven (works for static tables)
✅ 3 commits made

## Starting Point for Next Session

```bash
# Test the standalone extractor
python.exe test_standalone_table_extractor.py

# Verify Wikipedia extraction (200+ rows)
# Verify iteration logic
# Verify confidence flow to Excel
```

**Ready for implementation in next session!**
