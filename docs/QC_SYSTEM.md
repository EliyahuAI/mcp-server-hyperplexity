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

### 3. QC Citations and Sources

QC provides enhanced citation tracking using the same architecture as validation:

**QC Citations (`qc_citations`)**:
- Provided by AI in JSON response (like validation `answer`, `confidence`)
- Can reference existing validation citations: `"[1] Amazon Report - [key excerpt]..."`
- Can create new citations from web search: `"[NEW] SEC Filing - [key excerpt]..."`
- Used for "Key Citation:" section in Excel cell comments
- Required for fields with citations

**QC Sources (`qc_sources`)**:
- Extracted from AI API client metadata (like validation `citations` field)
- Contains URLs from QC web searches
- Added automatically to all QC results
- Populated in QC Sources column in Excel Details sheet

### 4. QC Actions

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

**Value Replaced**: Provide better value with reasoning and citations
```json
{
  "column": "Company",
  "answer": "Pfizer Inc.",
  "confidence": "HIGH",
  "qc_action_taken": "value_replaced",
  "qc_reasoning": "Corrected to official company name with proper formatting",
  "qc_citations": "[1] SEC Filing Form 10-K - [Official company name is Pfizer Inc.] ... registered in Delaware (https://sec.gov/...)"
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
- **Web searches**: Disabled by default (cost efficiency)
  - Enable for better QC citations when accuracy is critical
  - QC can create new citations: `"[NEW] Source - [excerpt] (URL)"`
  - QC sources automatically extracted from web search metadata

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
   - QC Confidence: QC confidence level
   - QC Reasoning: Explanation of revision
   - QC Sources: Source URLs from QC web search
   - QC Citations: Key citation for cell comments
   - Final Value: Ultimate output value

### Visual Example
```
Original Value: "Pfizer"
Validated Value: "pfizer" (Medium confidence, yellow)
QC Value: "Pfizer Inc." (High confidence, italic green)
Final Value: "Pfizer Inc."
```

### Enhanced Cell Comments
QC-enabled validation includes "Key Citation:" in Excel cell comments:
```
Original Value: Pfizer

Supporting Information: Company name standardization based on official records

Key Citation: [1] SEC Form 10-K - [Official registered name is Pfizer Inc.] ... Delaware corporation (https://sec.gov/...)

Sources:
[1] SEC Filing Form 10-K (https://sec.gov/...): "Official company name and registration details"
[2] Company Website About Page (https://pfizer.com/...): "Corporate information and structure"
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

## Cost & Time Tracking System

The QC system implements comprehensive cost, time, and results tracking that integrates with the main validation metrics pipeline. This section details the current implementation and data flows.

### QC Metrics Overview
- **Fields reviewed**: Total fields processed by QC across all rows
- **Fields modified**: Fields where QC made changes (confidence lowered + values replaced)
- **Confidence lowered**: Count of confidence reductions without value changes
- **Values replaced**: Count of complete value replacements
- **Cost breakdown**: Actual vs estimated costs, tokens, timing data
- **Per-column tracking**: QC modification rates by individual columns

### Cost Integration Architecture

#### 1. QC Cost Collection (`qc_cost_tracker.py`)

**Primary Metrics Container:**
```python
qc_metrics = {
    'total_qc_calls': 0,          # API calls made for QC
    'total_qc_tokens': 0,         # Total tokens consumed
    'total_qc_cost': 0.0,         # Actual cost paid (with cache benefits)
    'total_qc_estimated_cost': 0.0, # Estimated cost without cache
    'total_qc_time_actual': 0.0,  # Actual time spent (with cache)
    'total_qc_time_estimated': 0.0, # Estimated time without cache
    'total_fields_reviewed': 0,   # Fields processed by QC
    'total_fields_modified': 0,   # Fields changed by QC
    'confidence_lowered_count': 0, # Confidence reductions
    'values_replaced_count': 0,   # Value replacements
    'qc_models_used': set(),      # Models used for QC
    'qc_by_column': {}            # Per-column modification tracking
}
```

**Per-Column QC Tracking:**
```python
qc_by_column[column_name] = {
    'reviewed': 5,              # Times this column was QC'd
    'modified': 2,              # Times this column was changed
    'confidence_lowered': 1,    # Confidence reductions for this column
    'values_replaced': 1        # Value replacements for this column
}
```

#### 2. Provider Metrics Integration

**QC costs are integrated into provider metrics using a dual approach:**

```python
# 1. QC costs added to anthropic provider totals (for aggregation)
anthropic_provider['tokens'] += qc_tracker_metrics.get('total_qc_tokens', 0)
anthropic_provider['cost_actual'] += qc_tracker_metrics.get('total_qc_cost', 0.0)
anthropic_provider['cost_estimated'] += qc_tracker_metrics.get('total_qc_estimated_cost', 0.0)
# NOTE: QC calls are NOT added to validation call counts to avoid double-counting

# 2. Separate QC_Costs provider entry for tracking/display
providers['QC_Costs'] = {
    'calls': qc_tracker_metrics.get('total_qc_calls', 0),
    'tokens': qc_tracker_metrics.get('total_qc_tokens', 0),
    'cost_actual': qc_tracker_metrics.get('total_qc_cost', 0.0),
    'cost_estimated': qc_tracker_metrics.get('total_qc_estimated_cost', 0.0),
    'is_metadata_only': True    # Excluded from total call counts
}
```

**Key Integration Principle**: QC costs/tokens/time are included in totals, but QC calls are tracked separately to avoid double-counting in validation estimates.

#### 3. Data Flow Through System

```
QC Module (per row) → QC Integration Manager → Validation Lambda → Background Handler → DynamoDB
     ↓                        ↓                      ↓                   ↓              ↓
  Individual QC           Aggregated QC         Enhanced Metrics     Frontend Data     Database
  Actions & Costs         Summary               Integration          Processing        Storage
```

**Stage 1: QC Module Processing**
- Processes complete rows after ALL field groups validated
- Generates structured QC actions: `confidence_lowered`, `value_replaced`, `no_change`
- Collects timing and cost data from Anthropic API responses
- Tracks per-field QC decisions

**Stage 2: QC Integration Manager**
- Aggregates QC metrics across all processed rows
- Merges QC results with validation results
- Builds comprehensive QC summary with cost tracking

**Stage 3: Validation Lambda Response**
- Separates QC metrics from validation provider metrics
- Includes QC costs in anthropic provider totals (but not calls)
- Sends both `qc_metrics` and enhanced `provider_metrics` to interface

**Stage 4: Background Handler Processing**
- Calculates total provider calls excluding QC_Costs metadata-only provider
- Adjusts frontend scaling to account for QC as separate Claude search group
- Stores comprehensive QC metrics in DynamoDB

### Time Tracking Implementation

#### Actual vs Estimated Time Pattern

QC follows the same actual/estimated time pattern as validation:

```python
# Actual time (with cache benefits)
'total_qc_time_actual': sum(api_response_times_with_cache)

# Estimated time (without cache, for scaling)
'total_qc_time_estimated': sum(original_processing_times_no_cache)
```

**Cache Efficiency Calculation:**
- When QC responses are cached: `time_actual = 0.001s`, `time_estimated = original_time`
- Time savings percentage: `((estimated - actual) / estimated) * 100`

#### QC Time Integration with Validation Estimates

**Preview Operations:**
- QC time included in `estimated_validation_time_minutes`
- QC calls included in `total_provider_calls` for frontend scaling
- QC costs included in `quoted_validation_cost` user billing

**Full Validation Operations:**
- QC time measured and compared to preview estimates
- Cache efficiency tracked for QC API calls
- Actual QC costs included in `eliyahu_cost`

### Results Tracking & Excel Integration

#### QC Result Fields (per field, per row)

```python
qc_result = {
    'qc_entry': 'Pfizer Inc.',           # Final QC value
    'qc_confidence': 'HIGH',             # QC confidence level
    'qc_action_taken': 'value_replaced', # Type of QC action
    'qc_reasoning': 'Corrected to official name',
    'qc_applied': True,                  # Boolean QC change indicator
    'qc_sources': ['https://sec.gov/...'], # URLs from AI API metadata
    'qc_citations': '[1] SEC Form 10-K - [Official name: Pfizer Inc.] (url)', # Key citation from AI

    # Original validation data preserved
    'updated_entry': 'pfizer',           # Original validation value
    'updated_confidence': 'MEDIUM',      # Original confidence
    'updated_reasoning': '...',          # Original reasoning
    'updated_sources': [...]             # Original sources
}
```

#### Excel Output Integration

**QC Visual Indicators:**
- QC-modified values displayed in *italics* with confidence colors
- QC action columns in Details sheet: QC Applied, QC Value, QC Reasoning
- Complete audit trail: Original → Validation → QC → Final

**Three-Sheet Structure:**
1. **Updated Values**: Final values (QC if applied, otherwise validation)
2. **Original Values**: Raw data values (unchanged)
3. **Details**: Complete audit trail with QC tracking columns

### DynamoDB Storage Structure

#### Runs Table QC Metrics

```json
{
  "session_id": "session_20250922_123456",
  "qc_metrics": {
    "enabled": true,
    "total_fields_reviewed": 18,        // Total fields processed by QC
    "total_fields_modified": 5,         // Fields where QC made changes
    "confidence_lowered_count": 3,      // Confidence reductions without value change
    "values_replaced_count": 2,         // Complete value replacements
    "total_qc_cost": 0.0,              // Actual cost (0 if cached)
    "total_qc_cost_estimated": 0.077319, // Estimated cost without cache
    "total_qc_calls": 3,               // API calls made for QC
    "total_qc_tokens": 15420,          // Total tokens consumed
    "qc_models_used": ["claude-sonnet-4-0"],
    "total_qc_time_actual": 0.003,     // Actual time (with cache)
    "total_qc_time_estimated": 4.67,   // Estimated time (without cache)
    "qc_by_column": {                  // Per-column tracking
      "Company": {
        "reviewed": 5,
        "modified": 2,
        "confidence_lowered": 1,
        "values_replaced": 1
      },
      "Market_Cap": {
        "reviewed": 5,
        "modified": 1,
        "confidence_lowered": 0,
        "values_replaced": 1
      }
    },
    "revision_percentages_by_column": {  // Calculated modification rates
      "Company": {
        "percentage": 40.0,
        "revised_rows": 2,
        "total_rows": 5
      }
    }
  },
  "provider_metrics": {
    "anthropic": {
      "calls": 0,                      // QC calls NOT included here
      "tokens": 15420,                 // QC tokens included
      "cost_actual": 0.0,              // QC actual cost included
      "cost_estimated": 0.077319,      // QC estimated cost included
      "time_actual": 0.003,            // QC actual time included
      "time_estimated": 4.67           // QC estimated time included
    },
    "QC_Costs": {                      // Metadata-only tracking
      "calls": 3,
      "tokens": 15420,
      "cost_actual": 0.0,
      "cost_estimated": 0.077319,
      "is_metadata_only": true         // Excluded from total call counts
    }
  }
}
```

### Current Implementation Issues & Future Refactoring

#### Known "Messy" Aspects

**1. Field Name Inconsistencies:**
```python
# Mixed usage throughout codebase
qc_result.get('qc_confidence')      # QC module produces this
qc_result.get('updated_confidence') # Lambda sometimes expects this
```

**2. Double Integration Points:**
- QC costs appear in anthropic provider AND separate QC_Costs entry
- QC metrics tracked in both `qc_metrics` and `provider_metrics.QC_Costs`
- Multiple aggregation paths for same data

**3. Call Count Complexity (CRITICAL REFACTORING NEEDED):**
- Validation calls: counted in provider metrics
- QC calls: tracked separately to avoid double-counting
- Frontend scaling: manual adjustment to treat QC as Claude search group

**4. Complex Call Counting Implementation (TO BE UNWOUND):**

The current implementation uses multiple workarounds to handle QC calls consistently across the system:

**Background Handler (Preview):**
```python
# Add fake QC group to total so frontend math works: perplexity = total - claude = 5 - 2 = 3
total_groups_for_frontend = total_search_groups + (1 if qc_has_calls else 0)  # Add fake QC group to total
claude_groups_for_frontend = base_claude_groups + (1 if qc_has_calls else 0)  # Include QC as fake Claude group
```

**Background Handler (Full Validation):**
```python
# Calculate total_provider_calls including QC calls (like preview does)
total_validation_calls = sum(provider_data.get('calls', 0) for provider_data in provider_metrics_for_db.values())
total_qc_calls = qc_metrics_data.get('total_qc_calls', 0) if qc_metrics_data else 0
total_provider_calls_override = total_validation_calls + total_qc_calls
```

**Receipt Generation:**
```python
# Extract QC call counts from validation results (if available)
qc_calls = 0
if validation_results:
    qc_metrics_data = validation_results.get('qc_metrics', {})
    qc_calls = qc_metrics_data.get('total_qc_calls', 0) if qc_metrics_data else 0

# Fold QC calls into Claude calls for receipt display
total_claude_calls = claude_calls + qc_calls
```

**Email Generation:**
```python
# Get QC calls from billing_info and fold into Claude calls
qc_calls = billing_info.get('qc_api_calls', 0) if billing_info else 0
total_claude_calls = claude_calls + qc_calls
```

**WHY THIS IS MESSY:**
- QC calls must be extracted separately and manually added to totals
- Frontend receives fake search groups to make call estimates work
- Receipts and emails manually fold QC calls into Claude calls
- Different parts of the system handle QC calls differently
- Call counting logic is scattered across multiple files
- Complex special-case handling throughout the codebase

#### Future Refactoring Vision: QC as Search Group

**Goal**: Treat QC as an additional search group that gets tracked naturally within the existing validation framework.

**Proposed Architecture:**
```python
# Instead of separate QC tracking, QC becomes a search group
search_groups = [
    'group_1_financial_data',    # Original validation groups
    'group_2_company_info',
    'group_3_market_data',
    'qc_review_group'            # QC as additional search group
]

# QC naturally integrates with existing metrics
provider_metrics['anthropic']['calls'] += qc_calls  # No special handling needed
```

**Benefits of Refactoring:**
- Eliminates dual tracking systems
- QC calls counted naturally in provider metrics
- Frontend scaling works without manual adjustments
- Simplified cost aggregation
- Unified timing and progress tracking
- **Removes all the messy call counting workarounds above**

**Migration Plan for Call Counting:**
1. **Create QC search group** in validation config
2. **Remove fake group logic** from background_handler.py
3. **Remove QC call extraction** from receipt/email generation
4. **Remove total_provider_calls_override** logic
5. **Clean up billing_info QC fields** (qc_api_calls becomes unnecessary)
6. **Update frontend** to handle QC as natural Claude search group
7. **Remove manual call folding** from all display logic

**Migration Considerations:**
- Preserve historical QC tracking data
- Maintain QC-specific result fields (qc_action_taken, qc_reasoning)
- Keep QC visual indicators in Excel
- Ensure backward compatibility with existing DynamoDB structure
- **Test call counting across all interfaces** (frontend, progress, receipts, emails)

### Integration Summary

The QC tracking system provides comprehensive cost, time, and results tracking that integrates with the validation pipeline while maintaining separation for analysis. Despite some implementation complexity, it successfully tracks:

✅ **Complete Cost Integration**: QC costs included in all user billing and internal accounting
✅ **Detailed Results Tracking**: Per-field QC actions with complete audit trail
✅ **Cache Efficiency**: Actual vs estimated cost/time tracking with cache benefits
✅ **Column-Level Analytics**: QC modification rates and patterns by field
✅ **Excel Integration**: Visual QC indicators and complete traceability
✅ **DynamoDB Storage**: Comprehensive QC metrics stored with validation session data

The system is functional and provides valuable QC insights, but would benefit from the proposed refactoring to treat QC as a natural search group within the existing validation framework.

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