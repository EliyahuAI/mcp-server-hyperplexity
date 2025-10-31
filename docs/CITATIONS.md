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