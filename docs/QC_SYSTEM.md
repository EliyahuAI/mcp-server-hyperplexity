# Quality Control (QC) System

**Purpose**: Automated quality control review of validation outputs to improve accuracy and consistency.

## Overview

The QC system provides automated review of multiplex validation results. It operates per-row after all field groups complete, evaluating validation outputs and applying corrections when needed.

### Key Capabilities
- **Confidence Adjustment**: Lower confidence levels when appropriate
- **Value Replacement**: Replace validation outputs with improved values
- **Complete Traceability**: Track Original → Updated → QC value chains
- **Cost Efficiency**: Configurable models and token limits
- **Excel Integration**: QC values displayed in italics for clear identification

## How QC Works

### 1. Processing Flow
```
Row Data → Multiplex Validation → QC Review → Final Output
```

1. **Multiplex validation** processes all field groups for a row
2. **QC module** reviews complete validation outputs
3. **QC decisions** are made:
   - Lower confidence if validation seems uncertain
   - Replace value if better alternative found
   - No change if validation is acceptable
4. **Final outputs** combine validation and QC results

### 2. QC Review Process

QC receives:
- **Field guidance**: Description, format, notes, examples from config
- **Context**: ID fields for row context (not QC'd themselves)
- **Validation results**: Complete outputs from all field groups
- **Original values**: Raw data for comparison

QC evaluates each field using the same confidence rubric as validation:
- **HIGH**: Widely accepted fact, directly verified by authoritative source
- **MEDIUM**: Good estimates, respectable sources, not definitive
- **LOW**: Weak/conflicting sources, uncertainty, unverifiable

### 3. QC Actions

**Confidence Lowered**: Keep same value but reduce confidence level
```json
{
  "column": "Age",
  "answer": "45",
  "confidence": "MEDIUM",
  "qc_action_taken": "confidence_lowered",
  "qc_reasoning": "Source reliability concerns, lowered from HIGH to MEDIUM"
}
```

**Value Replaced**: Provide better value with reasoning
```json
{
  "column": "Company",
  "answer": "Pfizer Inc.",
  "confidence": "HIGH",
  "qc_action_taken": "value_replaced",
  "qc_reasoning": "Corrected to official company name with proper formatting"
}
```

**No Change**: Field passes QC review (not included in QC output)

## Configuration

### Enable/Disable QC
```json
{
  "qc_settings": {
    "enable_qc": true
  }
}
```

### Model Configuration
```json
{
  "qc_settings": {
    "model": ["claude-sonnet-4-0", "claude-opus-4-1"],
    "max_tokens_default": 8000,
    "tokens_per_validated_column_default": 4000,
    "anthropic_max_web_searches": 0
  }
}
```

**Default Settings**:
- **Model**: `claude-sonnet-4-0` (same as validation)
- **Tokens**: 8K baseline + 4K per field
- **Web searches**: Disabled (cost efficiency)

## Excel Output

### QC Indicators
- **QC values**: Displayed in *italics* with confidence colors
- **Non-QC values**: Standard formatting
- **Confidence colors**: GREEN (High), YELLOW (Medium), RED (Low)

### Sheet Structure
1. **Updated Values**: Final values (QC if applied, otherwise validation)
2. **Original Values**: Raw data values (unchanged)
3. **Details**: Complete audit trail with QC columns:
   - QC Applied: Yes/No
   - QC Value: QC-proposed value
   - QC Reasoning: Explanation of revision
   - Final Value: Ultimate output value

### Visual Example
```
Original Value: "Pfizer"
Validated Value: "pfizer" (Medium confidence, yellow)
QC Value: "Pfizer Inc." (High confidence, italic green)
Final Value: "Pfizer Inc."
```

## Field Processing

### ID Fields
- **Purpose**: Provide context for QC decisions
- **Processing**: Included in context section, not QC'd themselves
- **Example**: Developer, Study ID, Compound Name

### Validation Fields
- **Purpose**: Data to be validated and potentially QC'd
- **Processing**: Full QC review with field-specific guidance
- **Guidance includes**: Description, format requirements, examples, notes

### Field Guidance Example
```
FIELD: Market_Cap
* Description: Company market capitalization
* Format: Dollar amount with units (e.g., $5.2B, $340M)
* Notes: Use most recent available data
* Examples:
  - $150.5B
  - $2.3M
  - $45.7B
```

## Cost Tracking

### QC Metrics
- **Fields reviewed**: Total fields processed by QC
- **Fields modified**: Fields where QC made changes
- **Confidence lowered**: Count of confidence reductions
- **Values replaced**: Count of value replacements
- **Cost breakdown**: Tokens, API costs, timing data

### Integration
- QC costs aggregate with validation costs in preview entry
- Separate QC metrics tracked in provider_metrics
- Revision percentages calculated per column

## Implementation Details

### Core Components
- **`qc_module.py`**: Primary QC logic and API integration
- **`qc_integration.py`**: Clean interface for validation lambda
- **`qc_cost_tracker.py`**: Cost and metrics tracking
- **`excel_report_qc_unified.py`**: Excel creation with QC formatting

### API Integration
- Uses same `ai_api_client.call_structured_api` as validation
- Follows `MULTIPLEX_RESPONSE_SCHEMA` with QC extensions
- Scrubs encrypted content from citations
- Aggregates citations between validation and QC runs

### Error Handling
- Graceful fallback if QC disabled or fails
- Standard Excel creation if QC Excel unavailable
- Comprehensive logging and error tracking

## Key Benefits

1. **Improved Accuracy**: Catches validation errors and inconsistencies
2. **Consistency**: Applies uniform quality standards across all data
3. **Traceability**: Complete audit trail of all changes
4. **Efficiency**: Automated review at scale
5. **Transparency**: Clear indicators of QC-applied changes
6. **Flexibility**: Configurable models and thresholds

## When QC is Most Valuable

- **Complex data**: Multiple related fields requiring consistency
- **High-stakes validation**: Critical data requiring extra review
- **Uncertain sources**: When validation confidence is mixed
- **Format standardization**: Ensuring consistent output formatting
- **Cross-field validation**: Checking logical consistency across fields

---

*For technical implementation details, see the QC module source code in `src/shared/qc_*.py`*