# Table Entry Validation and Research

You are validating and updating several field values for a single row in a research table.

═══════════════════════════════════════════════════════════════
## 🎯 FOCUSED TASK
═══════════════════════════════════════════════════════════════

{search_instruction}

{research_questions}

═══════════════════════════════════════════════════════════════

---

═══════════════════════════════════════════════════════════════
## 📋 WHAT YOU'LL FIND BELOW
═══════════════════════════════════════════════════════════════

The sections below provide detailed context for **synthesizing your search results** into validated answers:

- **GENERAL NOTES**: Validation context for the broader research effort this subtask falls within
- **CONTEXT & PREVIOUS DATA**: Other fields from this row and prior validations for reference
- **FIELD DETAILS**: Detailed requirements, format, notes, and examples for each field
- **CONFIDENCE LEVELS**: How to assign confidence ratings to your findings
- **RESPONSE FORMAT**: Required JSON structure and critical validation rules

═══════════════════════════════════════════════════════════════

---

═══════════════════════════════════════════════════════════════
## 📋 GENERAL NOTES
═══════════════════════════════════════════════════════════════

{general_notes}

---

═══════════════════════════════════════════════════════════════
## 📊 CONTEXT & PREVIOUS DATA
═══════════════════════════════════════════════════════════════

**Context for this row:**

{context}

**Other fields from this row (unvalidated - for reference only):**

{original_row_context}

**Previous validations for this row:**

{previous_results}

---

═══════════════════════════════════════════════════════════════
## 📝 FIELD DETAILS - Format Requirements and Examples
═══════════════════════════════════════════════════════════════

**For each field you will receive:**

- **Field Name**: (This is the name of the field)
- **Description**: (What this field represents)
- **Format**: (How to format your answer)
- **Notes**: (Quality standards for this specific field)
- **Examples**: (Sample formatting)

**VALUES TO CONSIDER:**
- **Current Value** (to be validated/updated): The value that needs validation/updating in this run
- **Previous Value** (from Original Values sheet): The historical validated value from a prior validation run (if available)

**YOUR TASK**: Validate and update the **Current Value** using web search and the guidance provided. Compare it to the **Previous Value** (if available) to understand what has changed.

{fields_to_validate}

---

═══════════════════════════════════════════════════════════════
## ⭐ CONFIDENCE LEVELS
═══════════════════════════════════════════════════════════════

Assign confidence levels to both original and updated values:

- **HIGH**: Claim is a widely accepted fact, directly verified by authoritative source, or straightforward calculation that matches the guidance provided, without cause for pause. Claim matches the guidance provided.

- **MEDIUM**: Good estimates, confident projections, or respectable but not definitive sources that are consistent with the guidance provided.

- **LOW**: Weak/conflicting sources, uncertainty, no information available, or that does not match the guidance provided - if you cannot verify a value it is low confidence.
  - **Only LOW confidence answers may be blank.** If no data was found, use null for answer with LOW confidence.
  - **Confident absence is NOT blank** — if you are confident something does not exist or is not applicable, say so explicitly with language appropriate to the measure (e.g., "N/A", "Not applicable", "No website", "Not publicly traded") and assign an appropriate confidence level. Do not leave it blank.
  - **Blank originals**: Assign LOW for `original_confidence` when the original value was blank/empty (the system will reclassify).
  - **Removing false data**: If original has LOW confidence false data and no reliable replacement exists, you CAN go to blank with LOW confidence (removing bad data is acceptable).

---

═══════════════════════════════════════════════════════════════
## 📤 RESPONSE FORMAT
═══════════════════════════════════════════════════════════════

Return a JSON array where each item is a cell array with 6 elements:

```
[column, answer, confidence, original_confidence, consistent, explanation]
```

- **column**: Exact field name from FIELD DETAILS
- **answer**: The validated value (string or null for blank)
- **confidence**: H (HIGH), M (MEDIUM), or L (LOW)
- **original_confidence**: H, M, or L (for the original value)
- **consistent**: T (consistent with model knowledge), F (not consistent), or null
- **explanation**: Succinct reason you believe the answer is correct

**Example:**
```json
[
  ["Revenue", "$158.9B", "H", "M", "T", "Q3 2024 earnings report confirmed"],
  ["CEO", "Andy Jassy", "H", "H", "T", "Official Amazon leadership page"],
  ["Founded", null, "L", "L", null, "No reliable data found"]
]
```

### CRITICAL REQUIREMENTS

- **Do not use quotation marks around your responses** (except in JSON structure itself)
- **Assess both confidences**: Rate the quality of your updated answer (confidence) AND the quality of the original value (original_confidence) using H/M/L
- **CRITICAL - Blank original values**: If the original value was blank/empty, set `original_confidence` to `L` (LOW). Blank originals get LOW original_confidence.
- **Only update if significantly better**: Only provide a different validated value if you can improve significantly on the original value
- **Generally don't degrade confidence**:
  - If original has H/M confidence, don't degrade to L or blank without strong justification
  - If original has L confidence false data and no reliable replacement: You CAN leave blank (removing bad data is acceptable)
  - Hierarchy: H > M > L
  - **Confident absence**: Use language appropriate to the measure (e.g., "N/A", "Not applicable", "No website") with confidence — blank means you have no information, not that the value doesn't exist
- **Use exact column names**: Include the exact column name in each cell array - exactly as defined in the FIELD DETAILS above
- **Provide explanation**: Always include the explanation with succinct reasoning for your answer
- **Handle blanks appropriately**: If you cannot find or determine information for a field, use null for answer and L for confidence. Only LOW confidence answers may be truly blank.
- **Use examples as guides**: Use provided examples to guide your update format and expected values
- **Format for Excel**: Use newline characters correctly so that they are formatted in an Excel cell, particularly for bullets, lists, and other formatted text
- **Stay focused**: Do not research the context and guidance - focus only on the fields listed above
- **Double check everything**: Double check your updated response and confidence - speak precisely, there is no room for error
- **Valid JSON required**: The response MUST be valid JSON array format

---
