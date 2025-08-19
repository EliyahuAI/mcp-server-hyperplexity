# Perplexity Validator Output Enhancement Guide

## Overview
This guide outlines the requirements for enhancing the validation output to provide more nuanced feedback on original entries and restructure the Excel output format.

## Key Changes

### 1. Enhanced Confidence Scoring
- [ ] Add RED/YELLOW/GREEN confidence scoring for original values
- [ ] Only assign confidence when making validation decisions (not for blanks staying blank)
- [ ] Hardcode confidence rubric in JSON schema/prompt

### 2. Excel Output Structure
The output Excel file will contain three sheets:

#### Sheet 1: "Original Values"
- [ ] Display original values with confidence-based color coding (RED/YELLOW/GREEN)
- [ ] Add updated values and supporting information in cell comments (not separate cells)
- [ ] Comments should include: updated value + supporting rationale/source

#### Sheet 2: "Updated Values"
- [ ] Display updated values (where changes were needed)
- [ ] Include original values for reference
- [ ] Replace "Quote" with "Supporting Information/Source"
- [ ] Provide rationale or general statements rather than just quotes

#### Sheet 3: "Details"
- [ ] Comprehensive view with all information
- [ ] Include original value confidence scores
- [ ] Maintain existing detailed format with enhancements

### 3. Email Changes
- [ ] Remove original table attachment from email
- [ ] Update email text to explain the three-sheet structure
- [ ] Clarify the purpose and content of each sheet

## Implementation Tasks

### Phase 1: Schema Updates
- [ ] Update JSON schema to include original_confidence field
- [ ] Add prompt updates to request original value assessment
- [ ] Implement RED/YELLOW/GREEN/null logic

### Phase 2: Lambda Updates
- [ ] Modify perplexity-validator lambda to return original confidence
- [ ] Update response structure to include new fields
- [ ] Change "quote" to "supporting_information" throughout

### Phase 3: Excel Generation
- [ ] Refactor Excel generation to create three sheets
- [ ] Implement color coding (RED=#FF0000, YELLOW=#FFFF00, GREEN=#00FF00)
- [ ] Add cell comments containing updated values and supporting information
- [ ] Handle null confidence (no color) for blanks staying blank

### Phase 4: Email Template
- [ ] Update email template to explain new structure
- [ ] Remove original file attachment logic
- [ ] Add clear descriptions of each sheet

## Comment Format for Sheet 1
```
Updated Value: [new value]
Supporting Information: [rationale/source]
```

## Color Mapping
```python
def get_confidence_color(confidence):
    if confidence == "GREEN": return "00FF00"
    elif confidence == "YELLOW": return "FFFF00"
    elif confidence == "RED": return "FF0000"
    else: return None  # No color for null confidence
```

## Progress Tracking
- [x] Requirements documented
- [ ] JSON schema updated
- [ ] Perplexity validator lambda modified
- [ ] Excel generation refactored
- [ ] Email template updated
- [ ] Testing completed
- [ ] Documentation updated