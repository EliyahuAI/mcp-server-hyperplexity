# History Handling System Specification

## Overview

The history handling system tracks validation runs and provides historical context for subsequent validations. It consists of three components:

1. **Validation Record Sheet** - Run-level metadata in Excel output
2. **Cell Comments** - Field-level historical values embedded in Updated/Original sheets
3. **Session Info Storage** - Run records stored in `session_info.json`

This system replaces the fragile Details-sheet-based approach with a cleaner, more maintainable design.

---

## 1. Validation Record Sheet

### Purpose
Track validation runs at a high level with metadata and aggregate statistics.

### Sheet Structure

| Column Name | Type | Description | Source |
|------------|------|-------------|--------|
| Run_Number | Integer | Sequential run number (1, 2, 3...) | Auto-increment |
| Run_Time | ISO Timestamp | When validation was performed | `datetime.now(timezone.utc).isoformat()` |
| Session_ID | String | Clean session ID | From session context |
| Configuration_ID | String | Config file hash or S3 key | Config S3 key or hash |
| Run_Key | String | Unique identifier for this run | `{session_id}_{timestamp}` |
| Rows | Integer | Total rows processed | `len(rows_data)` |
| Columns | Integer | Total columns validated | `len(column_names)` |
| Original_Confidences | String | Distribution of original confidences | "L: 15%, M: 45%, H: 40%" |
| Updated_Confidences | String | Distribution of updated confidences | "L: 5%, M: 35%, H: 60%" |

### Confidence Calculation

```python
def calculate_confidence_distribution(validation_results, qc_results):
    """
    Calculate percentage distribution of confidence levels.
    Uses QC-adjusted confidences when QC was applied.
    """
    original_counts = {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0}
    updated_counts = {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0}
    total_fields = 0

    for row_key, row_results in validation_results.items():
        for field, field_data in row_results.items():
            total_fields += 1

            # Use QC-adjusted confidence if available
            if qc_results and row_key in qc_results and field in qc_results[row_key]:
                qc_field = qc_results[row_key][field]
                original_conf = qc_field.get('qc_original_confidence', field_data.get('original_confidence'))
                updated_conf = qc_field.get('qc_confidence', field_data.get('confidence_level'))
            else:
                original_conf = field_data.get('original_confidence')
                updated_conf = field_data.get('confidence_level')

            if original_conf in original_counts:
                original_counts[original_conf] += 1
            if updated_conf in updated_counts:
                updated_counts[updated_conf] += 1

    # Format as percentages
    original_str = f"L: {original_counts['LOW']/total_fields*100:.0f}%, M: {original_counts['MEDIUM']/total_fields*100:.0f}%, H: {original_counts['HIGH']/total_fields*100:.0f}%"
    updated_str = f"L: {updated_counts['LOW']/total_fields*100:.0f}%, M: {updated_counts['MEDIUM']/total_fields*100:.0f}%, H: {updated_counts['HIGH']/total_fields*100:.0f}%"

    return original_str, updated_str
```

### Preview vs Full Validation Handling

- **Preview**: Creates initial Validation Record entry with Run_Number = 1
- **Full Validation (same session_id)**:
  - If Validation Record exists with same Session_ID and Run_Number = 1, overwrite that row
  - Otherwise, append as new run (Run_Number = max + 1)

### Location in Excel Output

- **Sheet Name**: "Validation Record"
- **Position**: After Original Values sheet, before Details sheet (internal only)
- **Included In**: All Excel outputs (user downloads and internal storage)

---

## 2. Cell Comments Format

### Purpose
Embed validation history directly in cell comments for easy parsing in subsequent validations.

### Updated Values Sheet Comments

**Format**:
```
Original Value: {original_value} ({original_confidence} Confidence)

Key Citation: {citation_text} ({url})

Sources:
[1] {title} ({url}): "{snippet}"
[2] {title} ({url}): "{snippet}"
```

**Example**:
```
Original Value: ABC Corp (MEDIUM Confidence)

Key Citation: Per company website dated 2024-01-15 (https://example.com/about)

Sources:
[1] Company Website (https://example.com/about): "ABC Corp was founded in..."
[2] SEC Filing (https://sec.gov/filing): "ABC Corp (formerly ABC Corporation)..."
```

**Implementation** (`excel_report_qc_unified.py:619-716`):

```python
comment_parts = []

# Lead with Original Value and confidence
if validated_value != original_value:
    # Use QC-adjusted original confidence if available
    original_conf_display = original_confidence
    if qc_applied and qc_original_confidence:
        original_conf_display = qc_original_confidence

    comment_parts.append(f'Original Value: {original_value} ({original_conf_display} Confidence)')

# Add Key Citation
if key_citation:
    clean_citation = key_citation.replace('\n', ' ').replace('\r', ' ')
    comment_parts.append(f'Key Citation: {clean_citation}')

# Add Sources
if citation_texts:
    comment_parts.append(f"Sources:\n" + "\n".join(citation_texts))

comment_text = '\n\n'.join(comment_parts)
```

### Original Values Sheet Comments

**Format**:
```
Updated Value: {updated_value} ({updated_confidence} Confidence)

Key Citation: {citation_text} ({url})

Sources:
[1] {title} ({url}): "{snippet}"
[2] {title} ({url}): "{snippet}"
```

**Example**:
```
Updated Value: ABC Corporation (HIGH Confidence)

Key Citation: Press release confirms name change (https://example.com/press)

Sources:
[1] Press Release (https://example.com/press): "ABC Corp announces rebrand to ABC Corporation..."
[2] LinkedIn (https://linkedin.com/company/abc): "ABC Corporation (formerly ABC Corp)..."
```

**Implementation** (same location, different logic):

```python
comment_parts = []

# Lead with Updated Value and confidence
if validated_value != original_value:
    # Use QC-adjusted updated confidence if available
    updated_conf_display = validation_confidence
    if qc_applied and qc_confidence:
        updated_conf_display = qc_confidence

    comment_parts.append(f'Updated Value: {validated_value} ({updated_conf_display} Confidence)')

# Add Key Citation and Sources (same as Updated sheet)
```

---

## 3. History Extraction

### Single Source of Truth

**`shared_table_parser.py`** is the ONLY location where validation history is loaded.

### Method: `extract_validation_history()`

**Signature**:
```python
def extract_validation_history(self, bucket: str, key: str) -> Dict:
    """
    Extract validation history from Updated Values sheet + Validation Record.

    Returns:
        {
            'validation_history': {
                row_key: {
                    column: {
                        'prior_value': str,
                        'prior_confidence': str,
                        'prior_timestamp': str,
                        'original_value': str,
                        'original_confidence': str,
                        'original_key_citation': str,
                        'original_sources': list[str],
                        'original_timestamp': str
                    }
                }
            },
            'file_timestamp': str
        }
    """
```

### History Mapping Logic

When reading Updated Values sheet from a previously validated file:

1. **Prior Value** = Cell value from Updated Values sheet
2. **Prior Confidence** = Extracted from comment ("Original Value: X (MEDIUM Confidence)")
3. **Prior Timestamp** = Most recent run timestamp from Validation Record
4. **Original Value** = Extracted from comment ("Original Value: ...")
5. **Original Confidence** = Extracted from comment confidence
6. **Original Key Citation** = Extracted from comment
7. **Original Sources** = Parsed from Sources section in comment
8. **Original Timestamp** = First run timestamp from Validation Record

### Timestamp Resolution

- **Original Timestamp**: Validation Record Run_Number = 1, Run_Time field
- **Prior Timestamp**: Validation Record last run, Run_Time field
- **Fallback**: If no Validation Record, use S3 file `LastModified` timestamp

### Comment Parsing

```python
def _parse_validation_comment(self, comment_text: str) -> Dict:
    """
    Parse structured validation comment from Updated Values sheet.

    Example input:
        Original Value: ABC Corp (MEDIUM Confidence)

        Key Citation: Company website (https://...)

        Sources:
        [1] Title (URL): "snippet"
        [2] Title (URL): "snippet"

    Returns:
        {
            'original_value': 'ABC Corp',
            'original_confidence': 'MEDIUM',
            'key_citation': 'Company website (https://...)',
            'sources': ['https://...', 'https://...']
        }
    """
    result = {}
    lines = comment_text.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Parse Original Value with confidence
        if line.startswith('Original Value:'):
            # Extract: "Original Value: ABC Corp (MEDIUM Confidence)"
            content = line.replace('Original Value:', '').strip()
            if '(' in content and content.endswith('Confidence)'):
                # Split by last occurrence of '('
                last_paren = content.rfind('(')
                value = content[:last_paren].strip()
                conf = content[last_paren+1:].replace('Confidence)', '').strip()
                result['original_value'] = value
                result['original_confidence'] = conf
            else:
                result['original_value'] = content

        # Parse Key Citation
        elif line.startswith('Key Citation:'):
            result['key_citation'] = line.replace('Key Citation:', '').strip()

        # Parse Sources section
        elif line.startswith('Sources:'):
            sources = []
            i += 1
            while i < len(lines):
                source_line = lines[i].strip()
                if not source_line:
                    break
                # Extract URL from "[1] Title (URL): "snippet""
                if '(' in source_line and ')' in source_line:
                    url_start = source_line.find('(')
                    url_end = source_line.find(')', url_start)
                    url = source_line[url_start+1:url_end]
                    sources.append(url)
                i += 1
            result['sources'] = sources
            continue

        i += 1

    return result
```

---

## 4. Validation Prompt Format

### Location
`schema_validator_simplified.py:348-379` in `generate_multiplex_prompt()`

### Format in Prompt

**Important Schema Note**: In the validation response schema, "Original Value" refers to the "Current Value" shown in the prompt. This is the value from the input file that is being validated.

```
----- FIELD: {field_name} -----
Current Value: {current_value}
Description: {description}
Format: {format}
Importance: {importance}

Examples:
  - {example1}
  - {example2}

Current Value validation context (from validation on {current_timestamp}):
  Confidence: {current_confidence}
  Key Citation: {current_key_citation}
  Sources: {current_source1}, {current_source2}, ...

Prior Value (from Original Values sheet): {prior_value}
```

### Example in Prompt

```
----- FIELD 1: Company Name -----
Current Value: ABC Corporation
Description: Official company name
Format: String
Importance: CRITICAL

Examples:
  - ACME Corporation
  - Beta Industries

Current Value validation context (from validation on 2024-02-20):
  Confidence: HIGH
  Key Citation: Press release confirms name (https://example.com/press)
  Sources: https://example.com/press, https://linkedin.com/company/abc

Prior Value (from Original Values sheet): ABC Corp
```

### Implementation

```python
# Build field prompt section
field_parts = []
field_parts.append(f"----- FIELD {i}: {target.column} -----")
field_parts.append(f"Current Value: {row.get(target.column, '')}")
field_parts.append(f"Description: {target.description}")

if target.format:
    field_parts.append(f"Format: {target.format}")

field_parts.append(f"Importance: {target.importance}")

# Add examples after importance
if target.examples:
    field_parts.append("\nExamples:")
    for example in target.examples:
        field_parts.append(f"  - {example}")

# Include current value validation context if available
if validation_history and target.column in validation_history:
    field_history = validation_history[target.column]

    # Current value validation context (from most recent validation)
    if field_history.get('prior_value'):  # 'prior' in history = current in prompt
        prior_ts = field_history.get('prior_timestamp', 'unknown')
        field_parts.append(f"\nCurrent Value validation context (from validation on {prior_ts}):")

        if field_history.get('prior_confidence'):
            field_parts.append(f"  Confidence: {field_history['prior_confidence']}")

        if field_history.get('original_key_citation'):
            field_parts.append(f"  Key Citation: {field_history['original_key_citation']}")

        if field_history.get('original_sources'):
            sources_str = ', '.join(field_history['original_sources'])
            field_parts.append(f"  Sources: {sources_str}")

    # Prior value (from Original Values sheet - older validation)
    if field_history.get('original_value'):
        field_parts.append(f"\nPrior Value (from Original Values sheet): {field_history['original_value']}")

if target.notes:
    field_parts.append(f"\nNotes: {target.notes}")
```

---

## 5. Session Info Storage

### Location
`sessions/{email}/{session_id}/session_info.json`

### New Field: `validation_runs`

**Structure**:
```json
{
  "validation_runs": [
    {
      "run_number": 1,
      "run_time": "2024-01-15T10:30:00.000Z",
      "session_id": "clean_session_id",
      "configuration_id": "s3://bucket/path/to/config.json",
      "run_key": "session_id_20240115103000",
      "rows": 278,
      "columns": 15,
      "confidences_original": "L: 15%, M: 45%, H: 40%",
      "confidences_updated": "L: 5%, M: 35%, H: 60%",
      "is_preview": true
    },
    {
      "run_number": 2,
      "run_time": "2024-02-20T14:15:00.000Z",
      "session_id": "clean_session_id",
      "configuration_id": "s3://bucket/path/to/config.json",
      "run_key": "session_id_20240220141500",
      "rows": 278,
      "columns": 15,
      "confidences_original": "L: 5%, M: 35%, H: 60%",
      "confidences_updated": "L: 2%, M: 25%, H: 73%",
      "is_preview": false
    }
  ]
}
```

### Update Logic

**Preview Validation**:
```python
# Create or update first run entry
if 'validation_runs' not in session_info:
    session_info['validation_runs'] = []

# If preview, overwrite run_number 1 if it exists
if is_preview:
    # Remove any existing run_number 1
    session_info['validation_runs'] = [r for r in session_info['validation_runs'] if r.get('run_number') != 1]

    new_run = {
        'run_number': 1,
        'run_time': datetime.now(timezone.utc).isoformat(),
        'session_id': clean_session_id,
        'configuration_id': config_s3_key,
        'run_key': f"{clean_session_id}_{int(time.time())}",
        'rows': total_rows,
        'columns': total_columns,
        'confidences_original': original_confidences_str,
        'confidences_updated': updated_confidences_str,
        'is_preview': True
    }
    session_info['validation_runs'].insert(0, new_run)
```

**Full Validation**:
```python
# If full validation with same session_id, check if overwriting preview
if not is_preview:
    existing_runs = session_info.get('validation_runs', [])

    # If run_number 1 is a preview, overwrite it
    if existing_runs and existing_runs[0].get('is_preview') and existing_runs[0].get('run_number') == 1:
        session_info['validation_runs'][0] = {
            'run_number': 1,
            'run_time': datetime.now(timezone.utc).isoformat(),
            'session_id': clean_session_id,
            'configuration_id': config_s3_key,
            'run_key': f"{clean_session_id}_{int(time.time())}",
            'rows': total_rows,
            'columns': total_columns,
            'confidences_original': original_confidences_str,
            'confidences_updated': updated_confidences_str,
            'is_preview': False
        }
    else:
        # Append as new run
        next_run_number = max([r.get('run_number', 0) for r in existing_runs], default=0) + 1
        new_run = {
            'run_number': next_run_number,
            'run_time': datetime.now(timezone.utc).isoformat(),
            'session_id': clean_session_id,
            'configuration_id': config_s3_key,
            'run_key': f"{clean_session_id}_{int(time.time())}",
            'rows': total_rows,
            'columns': total_columns,
            'confidences_original': original_confidences_str,
            'confidences_updated': updated_confidences_str,
            'is_preview': False
        }
        session_info['validation_runs'].append(new_run)
```

---

## 6. DynamoDB Runs Table Updates

### New Fields

Add to `perplexity-validator-runs` table:

| Field Name | Type | Description |
|-----------|------|-------------|
| `confidences_original` | String | Original confidence distribution |
| `confidences_updated` | String | Updated confidence distribution |

### Example Record

```json
{
  "run_id": "user@example.com#session_id_timestamp",
  "email": "user@example.com",
  "session_id": "clean_session_id",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "status": "COMPLETED",
  "run_type": "Validation",
  "rows_processed": 278,
  "total_rows": 278,
  "confidences_original": "L: 15%, M: 45%, H: 40%",
  "confidences_updated": "L: 5%, M: 35%, H: 60%",
  ...
}
```

### Update Location

`src/lambdas/interface/handlers/background_handler.py` when updating run status:

```python
from ..core.run_tracking import update_run_status_for_session

# Calculate confidences
original_conf_str, updated_conf_str = calculate_confidence_distribution(
    validation_results,
    qc_results
)

# Update run status with confidence data
update_run_status_for_session(
    status='COMPLETED',
    run_type='Validation',
    confidences_original=original_conf_str,
    confidences_updated=updated_conf_str,
    ...
)
```

---

## 7. Implementation Checklist

### Phase 1: Excel Output Updates
- [ ] Update comment format in `excel_report_qc_unified.py` for Updated Values sheet
- [ ] Update comment format in `excel_report_qc_unified.py` for Original Values sheet
- [ ] Create `create_validation_record_sheet()` function
- [ ] Add confidence distribution calculation
- [ ] Integrate Validation Record into Excel creation workflow
- [ ] Test preview and full validation Validation Record updates

### Phase 2: History Extraction
- [ ] Implement `extract_validation_history()` in `shared_table_parser.py`
- [ ] Implement `_parse_validation_comment()` helper
- [ ] Implement `_load_validation_timestamps()` helper
- [ ] Add confidence extraction from cell colors (fallback)
- [ ] Test with new files (no history) and validated files (with history)

### Phase 3: Background Handler Integration
- [ ] Update `background_handler.py` to call `extract_validation_history()`
- [ ] Pass history data to validation lambda in payload
- [ ] Create session metadata structure
- [ ] Remove old `history_loader.py` import and calls

### Phase 4: Validation Prompt Updates
- [ ] Update prompt generation in `schema_validator_simplified.py`
- [ ] Format history with Prior and Original values
- [ ] Test prompts include correct historical context

### Phase 5: Session Info and Database
- [ ] Add `validation_runs` array to `session_info.json`
- [ ] Implement preview/full validation update logic
- [ ] Add `confidences_original` and `confidences_updated` to runs table schema
- [ ] Update `update_run_status_for_session()` to include confidence fields
- [ ] Test session_info persistence and retrieval

### Phase 6: Cleanup
- [ ] Remove Details sheet from user-facing downloads
- [ ] Keep Details sheet in internal S3 storage (debugging)
- [ ] Update email attachments to exclude Details
- [ ] Remove old `history_loader.py` (after transition period)
- [ ] Update documentation

---

## 8. Testing Scenarios

### Scenario 1: New File (No History)
**Input**: Fresh Excel file uploaded
**Expected**:
- No history extracted
- Validation Record sheet created with Run_Number = 1
- Comments added to Updated/Original sheets
- session_info.json includes first run

### Scenario 2: Preview Then Full Validation
**Input**: Preview run followed by full validation (same session_id)
**Expected**:
- Preview creates Run_Number = 1 with `is_preview: true`
- Full validation overwrites Run_Number = 1 with `is_preview: false`
- Validation Record sheet updated, not appended

### Scenario 3: Re-validation (With History)
**Input**: Previously validated file uploaded again
**Expected**:
- History extracted from Updated Values comments and Validation Record
- Prior Value = previous Updated Value
- Original Value = first validation's Original Value (unchanged)
- Validation Record appends as Run_Number = 2
- Prompt includes both Prior and Original context

### Scenario 4: Multiple Validations
**Input**: File validated 3+ times
**Expected**:
- Each validation adds new run to Validation Record
- History always shows Original (first) and Prior (most recent)
- session_info.json accumulates all runs
- DynamoDB runs table has separate entry for each validation

---

## 9. Migration Notes

### From Current System

**Old System**:
- Details sheet stores all field-level history
- Complex multi-level information (original + QC corrections)
- History loaded from Details sheet by `history_loader.py`

**New System**:
- Validation Record sheet for run-level metadata only
- History embedded in cell comments (Updated Values sheet)
- History extraction centralized in `shared_table_parser.py`

### Transition Plan

1. **No backward compatibility** - clean break from old system
2. Files with only Details sheet will have no history extracted (treated as new files)
3. Users re-validating old files will start fresh history tracking
4. Old Details sheet preserved in internal storage but not processed

### Data Preservation

- Old validation results remain in S3 JSON files
- Validation Record provides audit trail for all new validations
- session_info.json maintains complete run history per session
