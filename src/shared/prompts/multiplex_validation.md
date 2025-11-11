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

- **None/null**:
  - For `confidence`: Use when a field should remain blank (you have nothing to add)
  - For `original_confidence`: **ALWAYS use null when the original value was blank/empty**, regardless of whether you're now adding content. The original had no content, so it gets no confidence rating.

---

═══════════════════════════════════════════════════════════════
## 📤 RESPONSE FORMAT
═══════════════════════════════════════════════════════════════

Return a JSON array with one object per field:

```json
{json_schema_example}
```

### REQUIRED FIELDS

Each object in the response array MUST include:
- **column**: Exact field name from FIELD DETAILS
- **answer**: The validated value
- **confidence**: HIGH, MEDIUM, LOW, or None
- **original_confidence**: HIGH, MEDIUM, LOW, or None (for the original value)
- **sources**: Array of source URLs
- **explanation**: Succinct reason you believe the answer is correct

Optional fields:
- **supporting_quotes**: Direct quotes from sources with citation format '[1] "exact quote"'
- **consistent_with_model_knowledge**: Whether answer aligns with general knowledge

### CRITICAL REQUIREMENTS

- **Do not use quotation marks around your responses** (except in JSON structure itself)
- **Assess both confidences**: Rate the quality of your updated answer (confidence) AND the quality of the original value (original_confidence) using the same confidence rubric
- **CRITICAL - Blank original values**: If the original value was blank/empty, set `original_confidence` to `null`. You are assessing what WAS there originally, not what you're adding. Even if you're providing excellent new content with HIGH confidence, the original blank gets `null` confidence.
- **Only update if significantly better**: Only provide a different validated value if you can improve significantly on the original value
- **NEVER replace with lower confidence**: If you are more confident in the original value, why would you update it with a value that you are less confident in?
- **Use exact column names**: Include the exact column name in each object - exactly as defined in the FIELD DETAILS above
- **Include sources**: If you used web search, place actual URLs in the sources array. If using knowledge, cite your knowledge cutoff limitations where relevant
- **Include quotes/evidence**: If you have direct quotes from sources, use the supporting_quotes field with citation format: '[1] "exact quote from source" - context' where [1] refers to the citation number from sources array
- **Provide explanation**: Always include the explanation field with succinct reasoning for your answer
- **Handle blanks appropriately**: If you cannot find or determine information for a field that was originally blank, assign None confidence if the field should remain blank
- **Use examples as guides**: Use provided examples to guide your update format and expected values
- **Format for Excel**: Use newline characters correctly so that they are formatted in an Excel cell, particularly for bullets, lists, and other formatted text
- **Stay focused**: Do not research the context and guidance - focus only on the fields listed above
- **Double check everything**: Double check your updated response and confidence - speak precisely, there is no room for error
- **Valid JSON required**: The response MUST be valid JSON array format

---
