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

⚠️ **CRITICAL - ROW CONTEXT SCOPE CONSTRAINT:**
All validation results must be about the SPECIFIC ENTITY identified by the context above.

**Common scope errors to AVOID:**
- Validating a different entity with a similar name
- Using general information when specific information is required
- Example: When validating news for "Product X by Company Y", reject news that only mentions "Company Y" without mentioning "Product X"
- Example: When validating a company associated with a product, verify the company OWNS/DEVELOPS that specific product, not just that the company exists

**Scope validation checklist:**
1. Do sources explicitly mention ALL identifying information from context above?
2. Is information contemporary with the entity (not before it existed)?
3. Have you cross-referenced to confirm entity identity?
4. When in doubt, mark confidence as MEDIUM or LOW

**Other fields from this row (unvalidated - for reference only):**

{original_row_context}

**Previous validations for this row:**

{previous_results}

⚠️ **CRITICAL - INHERENT SUSPICION OF PREVIOUS RESULTS:**

Previous values shown above may be INCORRECT. Do NOT assume they are correct.

**Mandatory verification requirements:**
- Treat previous values as HYPOTHESES to be tested, not FACTS
- Every previous claim must be verified against current authoritative sources
- Do NOT copy previous values without independent verification
- Well-formatted previous answers with citations can still be wrong
- High confidence scores from past validations don't guarantee truth

**If current sources conflict with previous values:**
1. Prioritize DIRECT QUOTES from HIGH-AUTHORITY sources (see confidence criteria)
2. Check publication dates - newer authoritative sources may supersede old data
3. If conflict unresolved, mark confidence as MEDIUM or LOW
4. Document the conflict in your explanation

**Truth Standard:** Direct quotes from authoritative sources determine truth,
NOT how confident, well-cited, or professionally formatted previous results appear.

Your task: Use previous results as a STARTING POINT, then independently verify/correct with current sources.

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

Confidence measures the likelihood that the facts stated in the cell are precisely accurate:

- **HIGH (H)**: 85%+ likelihood that the facts are precisely accurate
  - Multiple facts: average likelihood ≥ 85%
  - Source: Authoritative, directly verifiable, widely accepted

- **MEDIUM (M)**: 65%-85% likelihood that the facts are precisely accurate
  - Multiple facts: average likelihood 65%-85%
  - Source: Respectable but not definitive, good estimates, confident projections

- **LOW (L)**: <65% likelihood that the facts are precisely accurate
  - Weak/conflicting sources, uncertainty, no authoritative verification
  - **Only LOW confidence answers may be blank (null)**
  - **Blank originals**: Assign LOW for `original_confidence` when the original value was blank/empty
  - **Removing false data**: If original has LOW confidence false data and no reliable replacement exists, you CAN go to blank with LOW confidence (removing bad data is acceptable)

**SPECIAL CASE - Expressing Doubt:**
When the value itself expresses uncertainty (e.g., "Rumors suggest...", "Unconfirmed reports say...", "Less reliable sources claim..."), confidence measures whether the SOURCES say it, NOT whether it's true.

Example:
- Value: "Rumors suggest launch in Q3 2025"
- HIGH confidence: Multiple sources confirm rumors exist
- The confidence is about the rumors existing, not about the launch happening

**Confident Absence:**
If you are confident something does not exist or is not applicable, say so explicitly with language appropriate to the measure (e.g., "N/A", "Not applicable", "No website", "Not publicly traded") and assign an appropriate confidence level (H/M). Do not leave it blank - blank means you have no information.

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
