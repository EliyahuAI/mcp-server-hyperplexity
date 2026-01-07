# Citation System Documentation

## Overview

The Perplexity Validator system maintains comprehensive citation tracking throughout the validation lifecycle. Citations are preserved with full text, including source titles, URLs, and quoted snippets, ensuring complete traceability of validated information.

**Note on Anthropic Citations**: Anthropic's web search API returns encrypted content that cannot be used. Therefore, Anthropic citations only include:
- Page title
- URL
- Page age (when available)

To compensate, the system includes a `supporting_quotes` field where the AI extracts key quotes and data points from the sources it accessed, providing context even when full citation snippets are not available from the API.

## Citation Flow

### 1. Initial Validation
When the validation lambda calls AI APIs (Perplexity, Claude, etc.), citations are captured in two forms:

- **Structured Citations**: Returned by the AI API with fields:
  - `title`: Source document title
  - `url`: Full URL to the source
  - `cited_text`: Quoted snippet from the source
  - `date`: Publication date (if available)

- **Source URLs**: Simple list of URLs for backward compatibility

### 2. Storage in Excel
After validation, citations are stored in Excel cell comments with full text:

```
Original Value: Amazon (HIGH Confidence)

Key Citation: Amazon Q3 2024 Earnings Report - "Sales increased 11% to $158.9 billion..."

Sources:
[1] Amazon Q3 2024 Earnings Report: "Sales increased 11% to $158.9 billion in the third quarter, compared with $143.1 billion in third quarter 2023..." (https://ir.aboutamazon.com/...)
[2] Another Source: "Full quote text here..." (https://...)
```

### 3. Validation History Extraction
When processing previously validated files, the system extracts:

- `original_sources`: List of URLs only (backward compatibility)
- `original_sources_full`: Complete citation strings with full text

### 4. QC System Display
The QC module displays citations for three value levels:

#### Prior Value (oldest validation)
- Shows value from a previous validation run
- Displays confidence level only
- No citations (this is historical context)

#### Original/Current Value (input being validated)
- Shows the current cell value with its validation context
- Displays full citations from `original_sources_full`:
  ```
  * **Sources:**
    - [1] Amazon Q3 2024 Earnings Report: "Sales increased 11%..." (https://...)
    - [2] SEC Filing: "Company reported revenue of..." (https://...)
  ```

#### Updated Value (proposed by current validation)
- Shows newly proposed value with full citation details
- Formats structured citations from the API:
  ```
  * **Citations:**
    - [1] Latest Report: "New data shows..." (https://...)
    - [2] Press Release: "Company announced..." (https://...)
  ```

## Data Structures

### Validation History Format
```python
{
    'row_key': {
        'column_name': {
            'prior_value': 'Previous validated value',
            'prior_confidence': 'HIGH',
            'prior_timestamp': '2024-01-15T10:30:00',
            'original_value': 'Value from Updated Values sheet cell (current INPUT)',
            'original_confidence': 'MEDIUM',
            'original_key_citation': 'Primary source citation',
            'original_sources': ['url1', 'url2'],  # URLs only
            'original_sources_full': [  # Full citation text
                '[1] Title: "quote" (URL)',
                '[2] Title: "quote" (URL)'
            ],
            'original_timestamp': '2024-02-20T14:15:00'
        }
    }
}
```

### Multiplex Result Format
```python
{
    'column': 'Field Name',
    'answer': 'Validated value',
    'confidence': 'HIGH',
    'original_confidence': 'MEDIUM',
    'reasoning': 'Validation reasoning',
    'sources': ['url1', 'url2'],  # URLs only
    'supporting_quotes': 'Key excerpts: "specific data" and "important statement"',  # NEW: Key quotes from sources
    'citations': [  # Structured citation objects
        {
            'title': 'Source Title',
            'url': 'https://...',
            'cited_text': 'Quoted snippet from source',
            'date': '2024-03-01'
        }
    ],
    'explanation': 'Additional context'
}
```

## Implementation Files

### Core Citation Processing

1. **`src/shared/ai_api_client.py`**
   - Extracts citations from API responses
   - Formats structured citation objects
   - Lines 2350-2377: Citation extraction logic

2. **`src/shared/shared_table_parser.py`**
   - Parses citations from Excel cell comments
   - Preserves full citation text in `sources_full`
   - Lines 1276-1296: Source parsing with full text preservation

3. **`src/shared/qc_module.py`**
   - Displays citations in QC prompts
   - Formats both structured and text citations
   - Lines 355-398: Citation display logic

4. **`src/lambdas/validation/lambda_function.py`**
   - Passes citations through validation pipeline
   - Line 3933: Adds citations to formatted results
   - Line 4575: Attaches citations to field results

### Citation Display Formatting

#### For Structured Citations (Updated Values)
```python
# qc_module.py lines 378-392
if isinstance(citation, dict):
    title = citation.get('title', 'Untitled')
    url = citation.get('url', '')
    cited_text = citation.get('cited_text', '')

    if cited_text:
        citation_text = f"[{i}] {title}: \"{cited_text}\" ({url})"
    else:
        citation_text = f"[{i}] {title} ({url})"
```

#### For Text Citations (Original/Current Values)
```python
# qc_module.py lines 360-363
if field_history.get('original_sources_full'):
    field_output.append(f"* **Sources:**")
    for source in field_history['original_sources_full']:
        field_output.append(f"  - {source}")
```

## Key Features

### Complete Citation Preservation
- No truncation of citation text
- Full quotes and snippets maintained
- Source titles and URLs preserved

### Supporting Quotes Field
- **Purpose**: Provides key excerpts when full citation snippets are unavailable (e.g., Anthropic API)
- **Content**: AI extracts important quotes, data points, dates, and statements from sources
- **Location**: Appears in:
  - QC prompt (so reviewer sees the quotes)
  - Details sheet "Supporting Quotes" column
  - Cell comments (indirectly through QC citations)
- **Use Case**: Particularly valuable for Anthropic validations where citation snippets are encrypted

### Backward Compatibility
- Maintains URL-only lists for legacy code
- Gracefully handles both structured and text citations
- Falls back to URL display when full citations unavailable

### QC Integration
- QC system sees full citation context
- Supporting quotes provide additional context for sources
- Can evaluate source quality and relevance
- Makes informed decisions about validation accuracy

### Audit Trail
- Complete citation history in Excel comments
- Timestamps for each validation run
- Clear progression: Prior → Original/Current → Updated

## Best Practices

1. **Always Preserve Full Text**: Never truncate citation snippets
2. **Maintain Structure**: Keep citations structured when possible
3. **Fallback Gracefully**: Handle missing citation data without errors
4. **Display Consistently**: Use same format across all displays
5. **Track Sources**: Maintain both URLs and full citations

## Citation Format Examples

### Good Citation Format
```
[1] Amazon Q3 2024 Earnings Report: "Net sales increased 11% to $158.9 billion in the third quarter, compared with $143.1 billion in third quarter 2023. Excluding the $1.4 billion unfavorable impact from year-over-year changes in foreign exchange rates throughout the quarter, net sales increased 12%" (https://ir.aboutamazon.com/quarterly-results/2024/Q3/)
```

### Components
- `[1]` - Citation number for reference
- `Amazon Q3 2024 Earnings Report` - Source title
- `: "..."` - Colon followed by quoted snippet
- `(https://...)` - Full URL in parentheses at the end

## QC Citation Disambiguation

### The Problem

When the QC module reviews validation results, it needs to reference citations from two different sources:
1. **Validation citations**: Sources from the original validation run (shown in the QC prompt)
2. **QC's own citations**: New sources from QC's web search (if available)

Both use numbered format `[1]`, `[2]`, etc., creating ambiguity. Additionally, when using the_clone snippets, citations are converted to numbers in code, so the AI doesn't know what numbers will be assigned.

### The Solution: Prefixed Citation References

#### Validation Citations: `[V*]` Prefix
Validation citations shown in the QC prompt use `[V1]`, `[V2]`, etc.:
```
* **Citations:**
  - [V1] Amazon Q3 2024 Earnings Report (p95): "Sales increased 11%..." (https://ir.aboutamazon.com/...)
  - [V2] SEC Filing (p85): "Company reported revenue of..." (https://sec.gov/...)
```

The AI references these using the exact `[V*]` format in its `key_citation` field.

#### QC Web Search Citations: `[QC*]` Transformation
If QC performs its own web search and references new sources with bare `[1]`, `[2]` format, these are automatically transformed to `[QC1]`, `[QC2]` in post-processing.

#### Special Citation Markers
When no validation citation applies, the AI uses:
- `[KNOWLEDGE]` - For facts based on model knowledge (e.g., `[KNOWLEDGE] Amazon is classified as Consumer Discretionary under GICS`)
- `[UNVERIFIED]` - When uncertain and no authoritative source found

### QC Response Format (7 Elements)

The compact QC response format:
```
[column, answer, confidence, original_confidence, updated_confidence, key_citation, update_importance]
```

Example:
```json
[
  ["Revenue", "$158.9B", "H", "M", "H", "[V1] Amazon IR (p95): \"Net sales $158.9B\" (https://ir.aboutamazon.com/...)", 2],
  ["Market Cap", "$2.1T", "H", "H", "H", "[V1] Yahoo Finance: current value (https://finance.yahoo.com/...)", 0],
  ["Sector", "Consumer Discretionary", "H", "H", "H", "[KNOWLEDGE] Amazon is classified as Consumer Discretionary under GICS (model knowledge)", 0]
]
```

### Source Reliability Indicator (p)

When available, citations include a probability score indicating expected accuracy:
- `p95` = Very reliable (authoritative sources like official filings)
- `p65-p85` = Reliable
- `p50` = Moderate
- `p15-p30` = Lower reliability
- `p05` = Low reliability

Format in citations: `[V1] Title (p85): "quote" (URL)`

### Implementation Files

**Citation Formatting for QC:**
- `src/shared/qc_module.py`:
  - `_format_citations_for_qc()` - Adds `[V*]` prefix to validation citations
  - `format_all_multiplex_outputs_for_qc()` - Formats citations with `[V{i}]` prefix
  - `_transform_qc_citation_refs()` - Transforms `[1]` to `[QC1]` for QC's own citations
  - `parse_compact_qc_response()` - Parses 7-element format with citation handling

**QC Prompt:**
- `src/shared/prompts/qc_validation.md` - Documents `[V*]` format and special markers

**QC Schema:**
- `src/shared/perplexity_schema.py` - `get_qc_response_format_schema()` defines 7-element format

### Citation Flow in QC

1. **Validation runs** - Citations captured from AI API response metadata
2. **QC prompt built** - Citations formatted with `[V*]` prefix
3. **QC AI responds** - References `[V1]`, `[KNOWLEDGE]`, or uses bare `[1]` for new searches
4. **Post-processing** - Bare `[1]` references transformed to `[QC1]`
5. **Excel report** - `key_citation` field shows final disambiguated citation

## Troubleshooting

### Missing Citations
- Check if API returned citations in response
- Verify citation extraction in ai_api_client.py
- Ensure citations field passed through validation pipeline

### Truncated Citations
- Check for substring operations in display code
- Verify no length limits in formatting functions
- Ensure full text preserved in parsing

### Citation Mismatch
- Verify row keys match between validation and QC
- Check citation parsing from Excel comments
- Ensure proper field mapping in results

### QC Citation Issues
- If QC references `[1]` instead of `[V1]`, check prompt formatting in `qc_module.py`
- If `[QC*]` transformation not working, check `_transform_qc_citation_refs()`
- If model fabricates citations, verify it has actual web search access (DeepSeek does not)