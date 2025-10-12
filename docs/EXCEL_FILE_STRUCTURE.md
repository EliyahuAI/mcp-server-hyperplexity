# Excel File Structure Documentation

## Overview

Hyperplexity generates enhanced Excel files with validation results, confidence levels, QC (Quality Control) modifications, and detailed metadata. This document describes the complete structure of these Excel files.

## File Versions

There are **two versions** of each Excel file generated:

### 1. **Full Version** (S3 Storage Only)
- **Location**: Stored in S3 results folders for audit trail
- **Sheets**: Updated Values, Original Values, Details, Validation Record
- **Purpose**: Complete validation history and internal processing details
- **Access**: Internal use only, not sent to customers

### 2. **Customer Version** (Email & Downloads)
- **Location**: Email attachments and download links
- **Sheets**: Updated Values, Original Values, Validation Record
- **Purpose**: Clean results without internal processing details
- **Access**: Customer-facing

## Sheet Structure

### Sheet 1: Updated Values

**Purpose**: Contains the final, validated data with QC modifications applied where appropriate.

**Content**:
- All original columns from the input table
- Values are updated based on validation and QC results
- Color-coded by confidence level (see Color Coding section)
- Cell comments with validation details (see Cell Comments section)

**Data Priority** (highest to lowest):
1. **QC Value** (if QC applied): Human-audited correction
2. **Validation Value** (if confidence improved): AI-validated value
3. **Original Value** (if no update needed): Unchanged from input

**Color Coding**:
- 🟢 **Green (High Confidence)**: Value validated with high confidence
- 🟡 **Yellow (Medium Confidence)**: Value validated with medium confidence
- 🔴 **Red (Low Confidence)**: Value validated with low confidence or requires review
- **No Color**: Original value unchanged (validation confidence not higher than original)

**Example**:
```
Conference Name          | Start Date  | Location
Neural Info Proc Sys 2025| 2025-12-02  | Vancouver, Canada
Int'l Conf Learning 2026 | 2026-04-23  | Vienna, Austria
```

### Sheet 2: Original Values

**Purpose**: Contains the original input data with fact-checking applied, but **no QC modifications**.

**Content**:
- All original columns from the input table
- Values show validation results WITHOUT QC changes
- Color-coded by confidence level (same as Updated Values)
- Cell comments with validation details

**Key Difference from Updated Values**:
- This sheet shows what the AI validator determined BEFORE human QC review
- Useful for understanding what changed during QC process
- Comments show the confidence assessments and citations

**Data Priority** (highest to lowest):
1. **Validation Value** (if confidence improved): AI-validated value
2. **Original Value** (if no update needed): Unchanged from input

**Color Coding**: Same as Updated Values sheet

### Sheet 3: Details (Full Version Only)

**Purpose**: Internal processing details for each validated field.

**Content**: Row-by-row, field-by-field validation details including:

**Columns**:
- `Row Key`: Unique identifier for the row (hash of ID fields)
- `Identifier`: Human-readable row identifier (e.g., "Conference: NeurIPS 2025")
- `[ID Fields]`: Values of fields marked as ID fields in config
- `Column`: Field name being validated
- `Original Value`: Value from input table
- `Updated Value`: Value after validation (before QC)
- `QC Value`: Value after QC review (if QC applied)
- `QC Applied`: Yes/No indicator
- `QC Action`: Type of QC modification (Keep/Update/No Change)
- `QC Reasoning`: Why QC made this decision
- `Final Confidence`: Confidence level after QC (HIGH/MEDIUM/LOW)
- `Original Confidence`: Confidence level before validation
- `Quote`: Key excerpt from validation source
- `Sources`: Comma-separated list of source URLs
- `Explanation`: Validation reasoning
- `Update Required`: Whether value differs from original
- `Substantially Different`: Whether QC value differs significantly from validation
- `Consistent with Model`: Whether QC agrees with validation
- `Model`: AI model used (e.g., "claude-3-5-sonnet-20241022")
- `Timestamp`: When validation occurred (UTC)

**Access**: Internal use only, not included in customer version

**Example Row**:
```
Row Key: 50ad1eff...
Identifier: Conference: NeurIPS 2025
Conference: Neural Information Processing Systems
Column: Start Date
Original Value: 2025-11-30
Updated Value: 2025-11-30
QC Value: 2025-12-02
QC Applied: Yes
QC Action: Update
QC Reasoning: Official website shows December 2, 2025 as correct start date
Final Confidence: HIGH
Original Confidence: MEDIUM
Quote: "Conference dates: December 2-8, 2025"
Sources: https://neurips.cc/Conferences/2025
Explanation: Validated against official conference website
Update Required: No
Substantially Different: Yes
Consistent with Model: No
Model: claude-3-5-sonnet-20241022
Timestamp: 2025-10-10 14:25:26
```

### Sheet 4: Validation Record

**Purpose**: Tracks validation run metadata and history for cache management and re-validation scenarios.

**Content**: Run-level metadata for each validation

**Columns**:
- `Run_Number`: Sequential run number (1 = first run, 2 = second run, etc.)
- `Run_Time`: ISO 8601 timestamp of validation (UTC)
- `Session_ID`: Unique session identifier
- `Configuration_ID`: S3 key or hash of configuration used
- `Run_Key`: Unique key for this run (session_id + timestamp)
- `Rows`: Total number of rows processed
- `Columns`: Total number of columns validated
- `Original_Confidences`: Distribution of original confidence levels (e.g., "HIGH: 10, MEDIUM: 5, LOW: 2")
- `Updated_Confidences`: Distribution of updated confidence levels after validation

**Run Number Logic**:
- **Run 1**: First validation (or preview)
- **Run 2+**: Subsequent validations (full validation after preview, or re-validation)
- **Overwrite Rule**: Full validation following a preview will overwrite Run 1

**Example**:
```
Run_Number | Run_Time                  | Session_ID | Configuration_ID | Run_Key           | Rows | Columns | Original_Confidences      | Updated_Confidences
1          | 2025-10-10T14:25:26+00:00| abc123     | config_v5.json   | abc123_1728573926 | 3    | 4       | HIGH: 2, MEDIUM: 8, LOW: 2| HIGH: 8, MEDIUM: 3, LOW: 1
```

**Use Cases**:
- **Cache Management**: Timestamps determine if re-validation is needed
- **History Tracking**: Shows all validation runs performed on this table
- **Re-validation**: Provides context about previous validation results
- **Audit Trail**: Complete record of when and how table was validated

## Cell Comments

Cell comments provide detailed validation context for each field. Comments appear on **both Updated Values and Original Values sheets**.

### Comment Structure

Comments follow this format:

```
Original Value: [value] ([confidence] Confidence)

Key Citation: [source title] - [excerpt] (URL)

Sources:
[1] [Source Title]: "[quoted text]" (URL)
[2] [Source Title]: "[quoted text]" (URL)
...
```

### Comment Components

#### 1. Original Value Section
- **Format**: `Original Value: [value] ([confidence] Confidence)`
- **Purpose**: Shows the original input value and its assessed confidence
- **Confidence Levels**: HIGH, MEDIUM, LOW, or UNKNOWN
- **Example**: `Original Value: 2025-11-30 (MEDIUM Confidence)`

**Note**: If QC review adjusted the original confidence, the QC-adjusted confidence is shown.

#### 2. Key Citation Section
- **Format**: `Key Citation: [title] - [excerpt] (URL)`
- **Purpose**: Highlights the most important source for this validation
- **Priority**: QC citation (if available) > First validation citation
- **Example**: `Key Citation: NeurIPS 2025 Official Schedule - Conference begins December 2, 2025 (https://neurips.cc/Conferences/2025)`

#### 3. Sources Section
- **Format**: Numbered list of all sources used
- **Each Source Includes**:
  - Number: `[1]`, `[2]`, etc.
  - Title: Source document or webpage title
  - Quoted Text: Relevant excerpt that supports the validation
  - URL: Direct link to the source
- **Example**:
```
Sources:
[1] NeurIPS 2025 Official Website: "The conference will take place December 2-8, 2025 in Vancouver" (https://neurips.cc/Conferences/2025)
[2] IEEE Calendar: "NeurIPS 2025: December 2-8" (https://ieee.org/calendar)
```

### Comment Display Behavior

**Size**: Comments are displayed with a default size of 300x150 pixels

**Visibility**:
- Comments appear as small red triangles in the upper-right corner of cells
- Hovering over the cell displays the full comment
- Comments are read-only for customers

**Generation Logic**:
- Comments are only added to cells that have validation data
- If a field has no validation result, no comment is added
- Comments are generated using xlsxwriter's `write_comment()` method

### Comment Examples

#### Example 1: High Confidence Validation
```
Original Value: Vancouver, BC (HIGH Confidence)

Key Citation: NeurIPS 2025 Venue Information - The 2025 conference will be held at the Vancouver Convention Centre (https://neurips.cc/venue)

Sources:
[1] NeurIPS 2025 Official Website: "Join us at the Vancouver Convention Centre for NeurIPS 2025" (https://neurips.cc/Conferences/2025)
```

#### Example 2: QC-Modified Value
```
Original Value: 2025-11-30 (MEDIUM Confidence)

Key Citation: NeurIPS 2025 Official Schedule (Verified by QC) - Conference registration opens December 2, 2025 at 8:00 AM (https://neurips.cc/schedule)

Sources:
[1] NeurIPS 2025 Official Website: "Registration and opening ceremony: December 2, 2025" (https://neurips.cc/Conferences/2025)
[2] Conference Calendar: "NeurIPS 2025 begins Dec 2" (https://ai-conference-calendar.org/2025)
```

#### Example 3: Low Confidence Warning
```
Original Value: TBD (LOW Confidence)

Key Citation: Conference Announcement - Location to be determined, expected announcement in Q1 2025 (https://conf2026.example.com/news)

Sources:
[1] Initial Announcement: "Conference dates confirmed, venue selection in progress" (https://conf2026.example.com/news/2024-10-15)
```

## Confidence Levels

### Definitions

- **HIGH**: Information verified from authoritative sources with strong corroboration
- **MEDIUM**: Information found in reliable sources but with some uncertainty or limited corroboration
- **LOW**: Information uncertain, conflicting sources, or requires manual verification
- **UNKNOWN**: No validation performed or confidence level not determined

### Confidence Changes

Validation can change confidence levels in both directions:

**Confidence Increased**: Original data verified and upgraded
- Example: `MEDIUM → HIGH` (date confirmed on official website)

**Confidence Decreased**: Original data found to be uncertain
- Example: `HIGH → MEDIUM` (sources show conflicting information)

**Confidence Maintained**: Original assessment confirmed
- Example: `HIGH → HIGH` (authoritative source confirms data)

### QC Impact on Confidence

Quality Control review can adjust both the value AND the confidence:

- **QC Keep**: Maintains validation result and confidence
- **QC Update**: Changes value, usually increases confidence to HIGH
- **QC No Change**: Original value was best, may adjust confidence based on reasoning

## Color Coding Details

### Color Application Rules

Colors are applied based on the **final confidence level** after both validation and QC:

1. **QC Applied**: Use QC confidence level
2. **No QC**: Use validation confidence level
3. **No Validation**: No color (original value, not validated)

### Color Palette

The Excel files use xlsxwriter color codes:

- **High Confidence**: `#90EE90` (Light Green)
- **Medium Confidence**: `#FFFF99` (Light Yellow)
- **Low Confidence**: `#FFB6C1` (Light Red/Pink)
- **No Color**: White background (default)

### Special Cases

**ID Fields**: Often not colored even if validated, as they serve as row identifiers

**Empty Cells**: No color applied

**Non-Validated Fields**: Fields not in the validation config remain uncolored

## File Generation Process

### 1. Data Collection
- Parse original Excel file
- Load validation results from validation lambda
- Load QC results from QC process
- Load configuration data

### 2. Dual Generation
The system generates BOTH versions simultaneously using `qc_enhanced_excel_dual_generator.py`:

```python
def create_both_excel_versions(
    excel_file_content: bytes,
    validation_results: Dict[str, Any],
    qc_results: Optional[Dict[str, Dict[str, Any]]] = None,
    config_data: Dict[str, Any] = None,
    session_id: str = ""
) -> Tuple[bytes, bytes]:
    """
    Generate BOTH full and customer versions by calling generator twice.

    Returns:
        Tuple of (full_version_bytes, customer_version_bytes)
    """
    # Generate full version (with Details sheet)
    full_version = create_qc_enhanced_excel_with_validation(
        ...,
        include_details_sheet=True
    )

    # Generate customer version (without Details sheet)
    customer_version = create_qc_enhanced_excel_with_validation(
        ...,
        include_details_sheet=False
    )

    return (full_version, customer_version)
```

### 3. Sheet Creation Order
1. **Updated Values**: Final validated data with QC
2. **Original Values**: Validated data without QC
3. **Details** (full version only): Field-by-field processing details
4. **Validation Record**: Run metadata and history

### 4. Distribution
- **Full Version**: Stored to S3 at `s3://perplexity-cache/{email}/{session_id}/results/{filename}_full.xlsx`
- **Customer Version**:
  - Attached to validation results email
  - Made available via download link
  - Stored temporarily for download access

## File Naming Convention

### S3 Storage (Full Version)
```
{original_filename}_v{config_version}_{type}_enhanced.xlsx

Examples:
- conference_schedule_v5_full_enhanced.xlsx
- conference_schedule_v5_preview_enhanced.xlsx
```

### Email Attachment (Customer Version)
```
{original_filename}_validated_{timestamp}.xlsx

Example:
- conference_schedule_validated_20251010_142526.xlsx
```

### Components
- `{original_filename}`: Original input file name (without extension)
- `{config_version}`: Configuration version number from config metadata
- `{type}`: "full" or "preview" validation type
- `{timestamp}`: ISO 8601 timestamp in YYYYMMDD_HHMMSS format

## Technical Implementation

### Libraries Used

- **xlsxwriter**: For creating Excel files (Updated Values, Original Values, Validation Record)
- **openpyxl**: For reading original Excel files and extracting data
- **Python datetime**: For timestamp generation in ISO 8601 format

**Important**: Never use openpyxl to modify xlsxwriter-generated files, as this causes data corruption due to library incompatibility.

### Key Files

- `src/shared/qc_enhanced_excel_report.py`: Core Excel generation with QC support
- `src/shared/qc_enhanced_excel_dual_generator.py`: Dual version generation
- `src/shared/excel_report_qc_unified.py`: Legacy Excel generation (being phased out)
- `src/lambdas/interface/reporting/interface_qc_excel_integration.py`: Integration point for interface lambda
- `src/shared/email_sender.py`: Email validation and attachment handling
- `src/lambdas/interface/handlers/background_handler.py`: Download link creation and S3 storage

### Validation Checks

Before sending email, the system validates that required sheets exist:

**Full Version** (for S3 storage):
- Updated Values ✓
- Original Values ✓
- Details ✓
- Validation Record ✓

**Customer Version** (for email/download):
- Updated Values ✓
- Original Values ✓
- Validation Record ✓

If validation fails, the email is NOT sent and the user is NOT charged.

## Common Issues and Troubleshooting

### Issue 1: Missing Sheets
**Symptom**: Excel file is missing one or more sheets
**Cause**: Generation error or validation failure
**Solution**: Check CloudWatch logs for Excel generation errors, ensure all required data is present

### Issue 2: Wrong Values in Comments
**Symptom**: Cell comments show incorrect validated values
**Cause**: Race condition in validation lambda (fixed in 2025-10-10)
**Solution**: Update to latest validation lambda with thread-safe validator instances

### Issue 3: Data Corruption in Original Values
**Symptom**: Original Values sheet missing columns or has corrupted data
**Cause**: Using openpyxl to modify xlsxwriter-generated files
**Solution**: Use dual generation approach (generate both versions natively with xlsxwriter)

### Issue 4: Colors Not Appearing
**Symptom**: Cells are not color-coded despite having validation data
**Cause**: Field not in validation config, or confidence level not determined
**Solution**: Check that field is enabled in configuration and validation completed successfully

### Issue 5: Missing Validation Record
**Symptom**: Validation Record sheet is missing
**Cause**: Using old Excel generation code or generation failed
**Solution**: Ensure using `qc_enhanced_excel_report.py` with Validation Record creation enabled

## Future Enhancements

Planned improvements to the Excel structure:

1. **Conditional Formatting**: Add Excel native conditional formatting for better compatibility
2. **Data Validation**: Add dropdown lists for fields with limited valid values
3. **Charts**: Include summary charts showing confidence distribution
4. **Filtering**: Enable Excel AutoFilter on Updated Values sheet
5. **Frozen Panes**: Freeze header row and ID columns for easier navigation
6. **Hyperlinks**: Make source URLs clickable hyperlinks instead of plain text

## Related Documentation

- `docs/QC_SYSTEM.md`: Quality Control system architecture
- `docs/CITATIONS.md`: Citation extraction and formatting
- `docs/BUG_INVESTIGATION_EXCEL_COMMENT_ROW_OFFSET.md`: Details on comment generation bug and fix
- `docs/HistoryHandling.md`: Validation history and cache management
- `docs/VALIDATION_OUTPUT_ENHANCEMENT_GUIDE.md`: Legacy enhancement documentation

## Version History

- **2025-10-12**: Added Validation Record sheet, corrected sheet names to Updated/Original Values, implemented dual generation
- **2025-10-10**: Fixed race condition causing wrong values in comments
- **2025-10-08**: Added QC integration to Excel generation
- **2025-09-15**: Initial enhanced Excel generation with color coding and comments
