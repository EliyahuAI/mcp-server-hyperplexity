# Null Confidence - Comprehensive Guide

**Date**: 2025-11-11
**Status**: Active

---

## Overview

This document explains how null/blank confidence values work throughout the validation system, including the critical distinction between "absence of evidence" and "evidence of absence."

### The Core Principle

**Null confidence is a special form of LOW confidence reserved exclusively for blank cells.**

This design choice allows us to:
- **Track missing information separately** from errors/low-quality data
- **Distinguish "no data" from "bad data"** in statistics and reporting
- **Prevent degradation** from real content to blank (except when removing false data)
- **Measure completeness** via Populated % metrics

In essence: **Blank = NULL = "We have nothing" ≠ LOW = "We have something unreliable"**

---

## Core Concepts

### Two Different "None" Values

1. **CONFIDENCE = None/null** (Confidence field)
   - Python `None` or JSON `null`
   - Means: "No confidence rating because no content exists"
   - Used when: Cell is blank/empty

2. **CELL VALUE = "None"** (Cell content)
   - String text: "None", "N/A", "Not applicable"
   - Means: Confident statement that field is not applicable
   - Can have: HIGH, MEDIUM, or LOW confidence

### Evidence of Absence vs Absence of Evidence

**Absence of Evidence** (Blank with null confidence):
- "I searched and found nothing"
- "No data is available"
- Cell is blank/empty
- Confidence = null
- Example: Looking for revenue data but company hasn't reported it yet

**Evidence of Absence** (Text with confidence):
- "I'm confident this doesn't apply"
- "This is definitively not applicable"
- Cell contains text: "N/A", "Not applicable", "No revenue (nonprofit)"
- Confidence = HIGH/MEDIUM/LOW
- Example: Asking for revenue from a nonprofit organization → "N/A - nonprofit" with HIGH confidence

---

## Confidence Hierarchy

**Standard hierarchy**: HIGH > MEDIUM > LOW > Blank/null

### Hierarchy Enforcement Rules

**Can upgrade**:
- null → LOW/MEDIUM/HIGH ✓ (adding data where there was none)
- LOW → MEDIUM/HIGH ✓ (improving data quality)
- MEDIUM → HIGH ✓ (improving data quality)

**Cannot degrade** (generally):
- HIGH → MEDIUM/LOW/Blank ✗ (losing good data)
- MEDIUM → LOW/Blank ✗ (losing decent data)

**Exception - Removing false data**:
- LOW (clearly false) → Blank ✓ (removing bad data when no replacement exists)
- This is the ONLY acceptable degradation to blank

**Better alternative to blank**:
- LOW (unverified/inapplicable) → "N/A" with MEDIUM ✓ (confident statement of non-applicability)

---

## How Null is Represented

### In JSON/Python Code

**Valid null representations**:
```python
None                    # Python None object
null                    # JSON null
''                      # Empty string
'-'                     # Dash (rare)
'null'                  # Lowercase string (AI sometimes returns this)
'None'                  # Capitalized string (AI mistake for None)
```

### In AI Responses

**Schema definition** (perplexity_schema.py):
```json
{
  "confidence": {
    "enum": ["HIGH", "MEDIUM", "LOW", null]  // Python None, not string
  }
}
```

**What AI should return**:
```json
{
  "confidence": null,           // Python None
  "original_confidence": null
}
```

**What AI sometimes mistakenly returns**:
```json
{
  "confidence": "None",         // String - treated as null by our code
  "original_confidence": "null" // String - treated as null by our code
}
```

---

## Code Enforcement

### Automatic Null Assignment

**lambda_function.py:4635-4640**
```python
# ENFORCE: Blank original values must have null confidence (don't rely on AI)
original_value = row.get(target.column, '')
if original_value is None or str(original_value).strip() == '':
    row_results[target.column]['original_confidence'] = None
```

**When this runs**:
- After AI returns validation results
- Checks if original cell VALUE was blank
- Overrides any confidence AI assigned
- Ensures blank cells → null confidence

### Null Detection Functions

**is_null_confidence()** (excel_report_qc_unified.py:124-129):
```python
def is_null_confidence(confidence):
    if confidence is None:
        return True
    confidence_str = str(confidence).strip()
    return confidence_str == '' or confidence_str == '-' or confidence_str.lower() == 'null'
```

**Note**: This checks for 'null' (lowercase) but NOT 'None' (capitalized)

**Counting logic** (background_handler.py):
```python
# Treats both 'null' and 'None' as null
if conf_level is None or str(conf_level).strip() in ('', '-', 'null', 'None'):
    confidence_counts['NULL'] += 1
```

**Why check for 'None' string?**
- AI sometimes returns string "None" instead of Python None
- This is technically invalid per schema
- But we handle it gracefully to count it as null

---

## When to Use Blank vs Text

### Use Blank (null confidence)

**Scenarios**:
1. Original cell was blank - keep original_confidence as null
2. No information found during validation - leave blank
3. Removing clearly false LOW confidence data with no replacement

**Example**:
- Field: "Market Share"
- Original: blank
- Validation: Searched but found no market share data
- Result: Leave blank, confidence = null

### Use "N/A" Text (with confidence)

**Scenarios**:
1. Confident field doesn't apply to this row
2. Confident something is definitively absent
3. Want to explicitly document why field is empty

**Examples**:
- Field: "Revenue"
- Original: blank
- Validation: This is a nonprofit organization
- Result: "N/A - nonprofit organization", confidence = HIGH

---

## Statistics and Reporting

### Confidence Distribution

**Example output**:
```
Original_Confidences: L: 10%, M: 20%, H: 30%, Blank: 40%
Updated_Confidences: L: 5%, M: 35%, H: 58%, Blank: 2%
Original_Populated_%: 60%
Updated_Populated_%: 98%
```

**Calculation**:
- Blank = NULL count
- Populated = Total - NULL
- Populated % = (Total - NULL) / Total × 100

### Where Null Counts Appear

**✓ Validation Record sheet** (Excel):
- Original_Confidences column: includes "Blank: X%"
- Updated_Confidences column: includes "Blank: X%"
- Original_Populated_% column
- Updated_Populated_% column

**✓ Email summary**:
- 🟢 HIGH: X% (Original) → Y% (Updated)
- 🟡 MEDIUM: X% (Original) → Y% (Updated)
- 🔴 LOW: X% (Original) → Y% (Updated)
- ⭕ Blank: X% (Original) → Y% (Updated)

**✓ Markdown preview**:
- Legend: "🔵 ID/Skipped • 🟢 High • 🟡 Medium • 🔴 Low • ⭕ Blank"
- Cells with null confidence show ⭕ emoji

---

## QC Handling of Null

### QC Receives Null from Validation

**Scenario**: Original was blank, validator added content

**Validation output**:
```json
{
  "column": "Revenue",
  "answer": "$5.2M",
  "confidence": "HIGH",
  "original_confidence": null  // Was blank originally
}
```

**QC rules**:
1. **Preserve null**: Keep original_confidence as null (don't convert to "LOW")
2. **No hierarchy violation**: null ≤ anything (upgrading is always allowed)
3. **Exception to equal confidence rule**: When original was blank, confidences don't need to match

### QC Can Blank Fields

**Allowed scenarios**:
1. **Original = LOW (false data)** → Blank ✓
   - Removing clearly false data is acceptable
   - Better than keeping false information

2. **Original = MEDIUM/HIGH** → Blank ✗
   - Should use "N/A" text with confidence instead
   - Don't remove good/decent data without strong reason

---

## Prompt Guidance

### Validation Prompt (multiplex_validation.md)

**Key points**:
- Blank original values → `original_confidence: null`
- No data found → Leave blank with `confidence: null`
- Confident non-applicability → Text "N/A" with confidence level
- Can remove LOW confidence false data → Go to blank acceptable

### QC Prompt (qc_validation.md)

**Key points**:
- Preserve null when original was blank
- Can blank LOW confidence false data
- Cannot blank MEDIUM/HIGH without strong reason
- Use "N/A" text for confident absence

---

## Common Scenarios

### Scenario 1: Originally Blank, Adding Data

**Input**:
- Original VALUE: (blank)
- Original confidence: Should be null

**Validation**:
```json
{
  "answer": "New validated data",
  "confidence": "HIGH",
  "original_confidence": null  // Enforced by code even if AI returns HIGH
}
```

**QC**:
```json
{
  "answer": "QC confirmed data",
  "confidence": "HIGH",
  "original_confidence": null,  // Preserved from validation
  "qc_reasoning": "Validated data confirmed..."
}
```

### Scenario 2: False Data, Removing It

**Input**:
- Original VALUE: "Revenue: $10B"
- Original confidence: LOW (unverified claim)

**Validation**:
```json
{
  "answer": "",  // Blank - no reliable data found
  "confidence": null,
  "original_confidence": "LOW"
}
```

**QC** (acceptable):
```json
{
  "answer": "",  // Keep blank - removing false data
  "confidence": null,
  "original_confidence": "LOW",
  "qc_reasoning": "Original data was false claim with no reliable source. Removing is better than keeping false information."
}
```

### Scenario 3: Not Applicable Field

**Input**:
- Original VALUE: (blank)
- Original confidence: null

**Validation** (GOOD):
```json
{
  "answer": "N/A - nonprofit organization",
  "confidence": "HIGH",
  "original_confidence": null
}
```

**Validation** (BAD - don't do this):
```json
{
  "answer": "",  // Should use "N/A" text instead
  "confidence": null,
  "original_confidence": null
}
```

### Scenario 4: String "None" in Confidence Field

**AI returns** (invalid per schema):
```json
{
  "confidence": "None",  // String, should be Python None
  "original_confidence": "None"
}
```

**System handles it**:
- Treats string 'None' as null
- Counts as NULL in statistics
- Works but technically incorrect

---

## Best Practices

### For Validation Prompts

1. **Blank originals**: Always null original_confidence
2. **No data found**: Blank cell with null confidence
3. **Confident non-applicability**: "N/A" text with confidence
4. **Can't verify but might be true**: Keep with LOW confidence
5. **Clearly false**: Can remove (blank) if no replacement

### For QC Prompts

1. **Preserve null**: Don't convert to "LOW"
2. **Don't degrade unnecessarily**: MEDIUM → Blank needs strong justification
3. **Can remove false data**: LOW → Blank acceptable for clearly false data
4. **Use "N/A" for confident absence**: Better than blank when you know it doesn't apply

### For Code

1. **Enforce null for blanks**: Don't rely on AI
2. **Check multiple representations**: None, '', 'null', 'None' (for confidence field)
3. **Distinguish**: confidence vs value checking
4. **Track NULL separately**: Include in all statistics

---

## Files Reference

**Enforcement**:
- `src/lambdas/validation/lambda_function.py:4635-4640` - Forces null for blank originals

**Detection**:
- `src/shared/excel_report_qc_unified.py:124-129` - is_null_confidence()
- `src/lambdas/interface/handlers/background_handler.py:2248, 4543` - Counting logic

**Prompts**:
- `src/shared/prompts/multiplex_validation.md:93-99` - Validation guidance
- `src/shared/prompts/qc_validation.md:126-132` - QC guidance

**Statistics**:
- `src/shared/excel_report_qc_unified.py:180-265` - calculate_confidence_distribution()
- `src/shared/email_sender.py:883-916` - Email confidence display
- `src/lambdas/interface/reporting/markdown_report.py:29-41` - Markdown emoji mapping

---

## Summary

**Blank cells** = Null confidence = Absence of evidence = ⭕

**Text "N/A"** = HIGH/MEDIUM/LOW confidence = Evidence of absence = 🟢🟡🔴

**Removing false data** = LOW → Blank is acceptable (only valid degradation to blank)

**Code enforcement** = Blank originals automatically get null confidence (don't trust AI)

**Hierarchy** = Generally can't degrade, except LOW false data → Blank
