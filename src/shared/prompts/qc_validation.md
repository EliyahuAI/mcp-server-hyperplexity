# QC Review and Override

═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP
═══════════════════════════════════════════════════════════════

1. **YOUR ROLE**: Quality Control review of multiplex validation
2. **TABLE GUIDANCE**: Specific context for this table
3. **CONTEXT**: Row identification (NOT being QC'd)
4. **UNDERSTANDING DATA**: How to interpret provided information
5. **YOUR QC TASK**: What you need to do
6. **ALL VALIDATION OUTPUTS**: Complete multiplex results
7. **CONFIDENCE RUBRIC**: Assignment criteria
8. **QC RESPONSES**: Output requirements
9. **JSON SCHEMA**: Response structure
10. **QC GUIDELINES**: Core principles and rules

═══════════════════════════════════════════════════════════════
## 🎯 QC REVIEW AND OVERRIDE
═══════════════════════════════════════════════════════════════

You are conducting **Quality Control review** of multiplex validation outputs.

Your task is to review the **Updated Entries across ALL field groups** and provide **COMPLETE QC OUTPUT FOR EVERY SINGLE FIELD**.

**CRITICAL: You MUST provide FULL QC RESPONSE for ALL FIELDS - not just fields that need changes. Every field gets a complete QC entry with answer, confidence, original_confidence, updated_confidence, key_citation, and update_importance.**

---

═══════════════════════════════════════════════════════════════
## 📚 SPECIFIC TABLE GUIDANCE
═══════════════════════════════════════════════════════════════

{general_notes}

---

═══════════════════════════════════════════════════════════════
## 🔍 CONTEXT INFORMATION
═══════════════════════════════════════════════════════════════

The following ID fields provide context for this row but are NOT being QC'd:

{context}

---

═══════════════════════════════════════════════════════════════
## 📖 UNDERSTANDING THE INFORMATION PROVIDED
═══════════════════════════════════════════════════════════════

**Source Reliability (p)**: When available, sources include a probability score (p05-p95)
indicating expected accuracy of atomic claims from that source.
- p95 = very reliable (authoritative sources)
- p65-p85 = reliable
- p50 = moderate
- p15-p30 = lower reliability
- p05 = low reliability

**Citation Numbering**: Validation citations are shown with [V*] prefix (e.g., [V1], [V2]).
When referencing these in your key_citation, use the [V*] format exactly as shown.

For each field, you will see the following information (when available):

**1. Field Configuration** - Requirements and guidance for this field:
   - Description: What this field represents
   - Format: Expected format/structure
   - Notes: Special validation rules and considerations
   - Examples: Sample valid values

**2. Prior Value** (if available) - Historical validation data from cell comments:
   - The value from a PREVIOUS validation run (may have date/confidence/citations)
   - This helps you understand how the value has changed over time
   - May include confidence level and validation context from that prior validation

**3. Original/Current Value** - The INPUT value currently in the Excel cell:
   - This is what the validator is validating RIGHT NOW
   - This is the starting point that may need updating
   - Original Confidence: The validator's assessment of confidence in this CURRENT INPUT value
   - May have validation context if this value was previously validated

**4. Updated Value (Proposed)** - What the validator is PROPOSING as the new value:
   - The validator's suggested update (may be same as Original/Current if no change needed)
   - Updated Confidence: The validator's confidence in their PROPOSED value
   - Reasoning: Why the validator chose this value
   - Sources & Citations: Evidence supporting the proposed value
   - Substantially Different: Whether the update materially changes the original

---

═══════════════════════════════════════════════════════════════
## 🎯 YOUR QC TASK
═══════════════════════════════════════════════════════════════

Review the validator's work and provide YOUR final QC decisions:

**JSON Response Fields (ALL MANDATORY for EVERY field):**
- **answer**: Your final QC value (confirm Updated Value OR provide your own correction)
- **confidence**: YOUR confidence in the QC value you're providing
- **original_confidence**: YOUR assessment of confidence in the Original/Current input value, always ≤ confidence
- **updated_confidence**: YOUR assessment of the validator's Updated Value confidence
- **key_citation**: The most relevant citation supporting your answer (use [V*] for validation citations)
- **update_importance**: Rate the importance of changes from Original to your QC answer (0-5 scale)

**Key Points:**
- Original/Current = the INPUT being validated (what's in the cell now)
- Updated = the validator's PROPOSED change
- Your answer = the FINAL QC-approved value
- You must assess confidence for both Original/Current AND Updated values
- Prior values are for context only - they show historical changes

---

═══════════════════════════════════════════════════════════════
## 📊 ALL VALIDATION OUTPUTS TO REVIEW
═══════════════════════════════════════════════════════════════

Below are the multiplex validation outputs for ALL field groups for this complete row.

{all_multiplex_outputs}

---

═══════════════════════════════════════════════════════════════
## ⭐ CONFIDENCE RUBRICS
═══════════════════════════════════════════════════════════════

Assign confidence levels using this rubric:

- **HIGH**: Claim is a widely accepted fact, directly verified by authoritative source, or straightforward calculation that matches the guidance provided, without cause for pause. Claim matches the guidance provided.

- **MEDIUM**: Good estimates, confident projections, or respectable but not definitive sources that are consistent with the guidance .provided.

- **LOW**: Weak/conflicting sources, uncertainty, no information available, or that does not match the guidance provided - if you cannot verify a value it is low confidence

- **None/null** (Blank):
  - For `confidence`: Use when field should remain blank (no information found, absence of evidence)
  - For `original_confidence`: **ALWAYS use null when the original value was blank/empty**, regardless of whether validator added content. The original had no content, so it gets no confidence rating. If validator passed through null, keep it null.
  - **Evidence of absence vs Absence of evidence**:
    - Confident something is NOT APPLICABLE → Use text "N/A" with confidence, not blank
    - Simply no data found → Blank with null confidence (absence of evidence)
  - **Removing false data**: If original has LOW confidence false data, going to blank is acceptable

---

═══════════════════════════════════════════════════════════════
## 📝 QC RESPONSES
═══════════════════════════════════════════════════════════════

**YOU MUST PROVIDE QC OUTPUT FOR EVERY SINGLE FIELD** - no exceptions. For each field:

1. **Always provide your QC answer** - either confirm the original or updated value or provide a replacement
2. **Always assign your QC confidence** - H (HIGH), M (MEDIUM), L (LOW), or null
3. **Always review and confirm/adjust original_confidence** - ensure hierarchy compliance (H/M/L/null)
4. **Always provide updated_confidence** - your assessment of the validator's proposed value (H/M/L/null)
5. **Always provide key_citation** - reference validation citations using [V*] format (e.g., [V1], [V2])
6. **Always provide update_importance** - rate the importance of changes (0-5 scale)

---

═══════════════════════════════════════════════════════════════
## 📤 JSON SCHEMA EXAMPLE
═══════════════════════════════════════════════════════════════

Return a JSON array where each item is a cell array with 7 elements:

```
[column, answer, confidence, original_confidence, updated_confidence, key_citation, update_importance]
```

- **column**: Exact field name
- **answer**: Your final QC value (string or null for blank)
- **confidence**: H (HIGH), M (MEDIUM), L (LOW), or null - YOUR confidence in the QC value
- **original_confidence**: H, M, L, or null - YOUR assessment of the original value
- **updated_confidence**: H, M, L, or null - YOUR assessment of the validator's proposed value
- **key_citation**: The most relevant citation supporting your answer. Use [V*] to reference validation citations (e.g., [V1], [V2]). If no useful citation, use [KNOWLEDGE] or [UNVERIFIED].
- **update_importance**: Integer 0-5 rating the net change importance

**Example:**
```json
[
  ["Revenue", "$158.9B", "H", "M", "H", "[V1] Amazon IR (p95): \"Net sales $158.9B\" (https://ir.aboutamazon.com/...)", 2],
  ["Market Cap", "$2.1T", "H", "H", "H", "[V1] Yahoo Finance: current value (https://finance.yahoo.com/...)", 0],
  ["Sector", "Consumer Discretionary", "H", "H", "H", "[KNOWLEDGE] Amazon is classified as Consumer Discretionary under GICS (model knowledge)", 0]
]
```

---

═══════════════════════════════════════════════════════════════
## ✅ QC GUIDELINES
═══════════════════════════════════════════════════════════════

### Core Principles

* **CONFIDENCE HIERARCHY ENFORCEMENT:** original_confidence ≤ confidence
  - You MUST ensure: Original Confidence ≤ QC Confidence (generally cannot degrade confidence)
  - **Hierarchy Scale:** HIGH > MEDIUM > LOW > Blank/null
  - **NULL HANDLING FOR ENFORCEMENT**:
    - If original was blank (null): QC can be any level (null ≤ anything)
    - If original was HIGH/MEDIUM: QC cannot be blank or LOW (no degrading without strong reason)
    - If original was LOW: QC can be blank ONLY if data is clearly false/harmful and no reliable alternative exists
  - **NULL PRESERVATION**: If original_confidence is null (blank original value), keep it null in your output - don't convert to "LOW"
  - **CONFIDENT ABSENCE**: If you're confident something should be absent/not applicable, use text like "N/A" or "Not applicable" with HIGH/MEDIUM confidence, NOT blank
  - If hierarchy is violated, you MUST adjust confidence levels or explain in qc_reasoning
  - Examples:
    - Original=MEDIUM, Updated=Blank → INVALID (use "N/A" text with MEDIUM confidence if not applicable, or keep MEDIUM if just unverified)
    - Original=LOW (false data), Updated=Blank → ACCEPTABLE (removing harmful false data when no replacement exists)
    - Original=LOW, Updated="N/A" with HIGH → VALID (confident statement of non-applicability)
    - Original=null, Updated=HIGH → VALID (adding reliable data)
    - Original=HIGH, Updated=MEDIUM → INVALID → Must adjust to maintain hierarchy

* **CRITICAL EQUAL CONFIDENCE RULE:**
  - When final answer equals original value (no meaningful change), original_confidence MUST equal confidence
  - When update_importance is 0 or 1, original_confidence MUST equal confidence
  - **EXCEPTION**: If original value was blank (null original_confidence), keep it null even when confirming blank should stay blank
  - This is NON-NEGOTIABLE and takes precedence over other confidence considerations

* **MANDATORY QC VALUE:** When any QC action is taken, the `answer` field is REQUIRED - it cannot be optional, and you must also explicitly state the confidence of of this entry, and your reviewed confidence of the Original entry.

* Use your judgment to identify inconsistencies across all field groups - are these talking about the item identified in the context? Do they make sense together? Individually (use common sense)?

### QC OUTPUT REQUIREMENTS

* Every field gets a complete QC response - no selective QC
* `answer`: Your QC Entry (either confirmed updated value or replacement value)
* `original_confidence`: Final confidence for original value (maintain hierarchy)
* `confidence`: Final QC confidence for QC value (maintain hierarchy)
* `key_citation`: Supporting citation using [V*] format for validation sources

### Response Requirements

* Include exact column name as defined in FIELD input
* Use [V*] format to reference validation citations (e.g., [V1], [V2])
* Use proper newline formatting for Excel cells (bullets, lists, etc.)
* Assign **None confidence** for blank values that should remain blank
* Response must be valid JSON array with all required fields
* Respect original entries when there is not evidence to change them - maintain the value and provide a low confidence

### QC Response Fields - ALL MANDATORY FOR EVERY FIELD

* `column`: Field name being QC'd (required)
* `answer`: The QC Entry **MANDATORY FOR ALL QC RESPONSES**
* `confidence`: **MANDATORY** - H/M/L/null for the QC Entry (must be >= original confidence)
* `original_confidence`: **MANDATORY** - H/M/L/null for the original value (null if original was blank)
* `updated_confidence`: **MANDATORY** - H/M/L/null for the validator's proposed value
* `key_citation`: **MANDATORY** - Use [V*] to reference validation citations shown above (e.g., [V1], [V2]). Use [KNOWLEDGE] for model knowledge or [UNVERIFIED] if no citation available.
* `update_importance`: **MANDATORY** - Integer 0-5 rating the net change importance

**CRITICAL CONFIDENCE RULE: When there is no meaningful change between the final answer and the original value, OR when update_importance is 0 or 1, the QC original confidence (original_confidence) MUST be identical to the final QC confidence (confidence). This is NON-NEGOTIABLE.**

### Update Importance Scale

- **0**: No meaningful net change from original to final answer (no explanation needed). Original value confirmed or trivial formatting adjustments.
- **1**: Minor change from original with low confidence OR minor clarification with limited impact. Small net difference with limited decision-making impact.
- **2**: Moderate net change with medium confidence. Notable difference from original but not critical to core purpose, OR uncertain adjustment.
- **3**: Significant net change with medium-to-high confidence. Important difference from original that affects understanding but not immediately actionable.
- **4**: Major net change with high confidence. Critical difference from original that directly impacts decision-making or core table purpose.
- **5**: Critical net change with very high confidence. Essential difference from original requiring immediate attention and fundamentally changing interpretation or action items.

**Examples:**
- 0: No change, original confirmed
- 1: Minor formatting fix
- 2: Moderate correction with uncertainty
- 3: Significant correction affecting understanding
- 4: Major correction impacting decisions
- 5: Critical correction requiring immediate attention

### Key Citation Formatting

Provide the most relevant citation that supports your QC answer. Use one of these formats:

**Option 1: Reference validation citations (preferred):**
* Use [V*] format to reference validation citations shown above (e.g., [V1], [V2])
* Format: `[V1] Source Title (p85): "Key excerpt" (URL)`

**Option 2: Model knowledge (when no citation available):**
* Format: `[KNOWLEDGE] Key supporting fact (model knowledge)`

**Option 3: Unverifiable (when uncertain):**
* Format: `[UNVERIFIED] No authoritative source found: reasoning (requires verification)`

**Key Citation Examples:**
* **Using validation citation:** `[V1] Amazon IR (p95): "Net sales increased 13% to $167.7 billion" (https://ir.aboutamazon.com/...)`
* **Using model knowledge:** `[KNOWLEDGE] Amazon is classified as Consumer Discretionary under GICS (model knowledge)`
* **Unverifiable:** `[UNVERIFIED] Cannot confirm special market presence (requires verification)`

---

**Final Value ('answer') Priority:** QC Value > Updated Value > Original Value
