# Snippet Validation System (Betting-Based Quality Assessment)

## Overview

The snippet validation system has been integrated into The Clone's snippet extraction pipeline. Each extracted snippet now receives a **probability score (`p`)** representing the expected pass-rate for factual accuracy.

## How It Works

### 1. Extraction + Validation Flow

```
Source → Extract Snippets → Validate Each Snippet → Attach p + reason → Return Validated Snippets
```

Each snippet now contains:
- `p`: Probability score (0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95)
- `validation_reason`: Keyword explaining the score (PRIMARY, DOCUMENTED, STALE, etc.)
- `validation_claims`: Up to 2 atomic factual claims extracted from the snippet

### 2. Validation Criteria

The validator judges snippets based on:

#### Hard Rules (Automatic Low Scores)
- **CONTRADICTED**: Internal contradictions → p=0.05-0.10
- **PROMOTIONAL**: Marketing language → p=0.05-0.10
- **ANONYMOUS**: Anonymous sourcing → p=0.05-0.10
- **STALE**: Outdated for time-sensitive queries → p=0.05-0.10
- **UNSOURCED**: No factual claims (C=0) → p=0.20

#### Quality Gates (Required for High Scores)
To achieve p≥0.85, snippet must satisfy ONE of:
- **PRIMARY**: Official/primary source (e.g., company blog, government data)
- **DOCUMENTED**: Methods/data/denominators clearly shown
- **ATTRIBUTED**: Named accountable source with role and specifics

#### Claim Count Rules
- C=2 claims: cap p≤0.90 unless PRIMARY or DOCUMENTED
- C≥3 claims: cap p≤0.75 unless PRIMARY + quoted primary text

### 3. Probability Values

Only these values are allowed: **{0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95}**

- **0.95**: Highest quality (PRIMARY source with verifiable claims)
- **0.85**: High quality (DOCUMENTED or ATTRIBUTED)
- **0.65**: Above average quality
- **0.50**: Baseline quality
- **0.30**: Below average quality
- **0.15**: Low quality (weak sourcing)
- **0.05**: Very low quality (STALE, PROMOTIONAL, CONTRADICTED)

## Usage

### Basic Usage (Validation Enabled by Default)

```python
from the_clone.snippet_extractor_streamlined import SnippetExtractorStreamlined

extractor = SnippetExtractorStreamlined()

result = await extractor.extract_from_source(
    source=source_dict,
    query="What is DeepSeek V3's parameter count?",
    snippet_id_prefix="S1.1",
    all_search_terms=["DeepSeek V3 parameters"],
    primary_search_index=1
)

# Each snippet now has p, validation_reason, validation_claims
for snippet in result['snippets']:
    print(f"{snippet['id']}: p={snippet['p']}, reason={snippet['validation_reason']}")
    print(f"  Text: {snippet['text']}")
    print(f"  Claims: {snippet['validation_claims']}")
```

### Advanced Usage (Quality Filtering)

```python
# Only keep snippets with p >= 0.50
result = await extractor.extract_from_source(
    source=source_dict,
    query="What is DeepSeek V3's parameter count?",
    snippet_id_prefix="S1.1",
    all_search_terms=["DeepSeek V3 parameters"],
    primary_search_index=1,
    min_quality_threshold=0.50  # Filter out low-quality snippets
)
```

### Disable Validation (If Needed)

```python
# Disable validation for faster extraction
extractor = SnippetExtractorStreamlined(enable_validation=False)
```

### Custom Validation Model

```python
# Use a different model for validation (default: claude-haiku-4-5)
result = await extractor.extract_from_source(
    source=source_dict,
    query="What is DeepSeek V3's parameter count?",
    snippet_id_prefix="S1.1",
    all_search_terms=["DeepSeek V3 parameters"],
    primary_search_index=1,
    validation_model="claude-sonnet-4-5"  # More powerful model
)
```

## Testing

Run the test script to see validation in action:

```bash
python.exe src/the_clone/tests/test_snippet_validation.py
```

This will test the validator with:
- High quality snippets (PRIMARY, DOCUMENTED sources)
- Medium quality snippets
- Low quality snippets (STALE, PROMOTIONAL, UNSOURCED)

## Integration Points

### Files Modified
1. **snippet_extractor_streamlined.py**
   - Added `SnippetValidator` integration
   - Added `enable_validation`, `validation_model`, `min_quality_threshold` parameters
   - Snippets now include `p`, `validation_reason`, `validation_claims` fields

### Files Created
1. **snippet_validator.py**
   - Core validation logic
   - Batch validation support (parallel processing)
   - Probability calculation based on hard rules and quality gates

2. **prompts/snippet_validation.md**
   - Detailed validation prompt with rules and examples
   - Covers all quality levels and edge cases

3. **tests/test_snippet_validation.py**
   - Test suite demonstrating validation across quality levels

## Example Output

```json
{
  "snippets": [
    {
      "id": "S1.1.0-H",
      "text": "DeepSeek V3 uses 671 billion total parameters",
      "p": 0.95,
      "validation_reason": "PRIMARY",
      "validation_claims": [
        "DeepSeek V3 has 671B total parameters",
        "Uses Mixture-of-Experts architecture"
      ],
      "_source_url": "https://deepseek.ai/blog/deepseek-v3",
      "_source_date": "2024-12-26"
    },
    {
      "id": "S1.1.1-M",
      "text": "Early benchmarks show strong performance",
      "p": 0.30,
      "validation_reason": "OK",
      "validation_claims": [],
      "_source_url": "https://techblog.com/review",
      "_source_date": "2024-12-15"
    }
  ]
}
```

## Performance Considerations

- Validation runs in **parallel** for all snippets from a source (fast)
- Uses **Haiku by default** (cost-effective)
- Can be **disabled** if speed is critical
- Can **filter** low-quality snippets automatically with `min_quality_threshold`

## Benefits

1. **Quality Awareness**: Know which snippets are reliable before synthesis
2. **Automatic Filtering**: Remove low-quality snippets early
3. **Transparent Reasoning**: Each score comes with a reason keyword
4. **Claim Extraction**: See exactly what factual claims were validated
5. **Configurable**: Enable/disable, adjust thresholds, change models

## Next Steps

The validation system is now integrated and ready to use. Consider:

1. **Synthesis Integration**: Use `p` scores to weight snippets during synthesis
2. **Quality Thresholds**: Experiment with `min_quality_threshold` values
3. **Reporting**: Include validation stats in query results
4. **Caching**: Consider caching validation results for identical snippets
