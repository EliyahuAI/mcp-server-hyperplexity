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
## 📝 QC RESPONSES
═══════════════════════════════════════════════════════════════

**YOU MUST PROVIDE QC OUTPUT FOR EVERY SINGLE FIELD** - no exceptions. For each field:

1. **Always provide your QC answer** - either confirm the original or updated value or provide a replacement
2. **Always assign your QC confidence** - H (HIGH), M (MEDIUM), or L (LOW)
3. **Always review and confirm/adjust original_confidence** - ensure hierarchy compliance (H/M/L)
4. **Always provide updated_confidence** - your assessment of the validator's proposed value (H/M/L)
5. **Always provide key_citation** - reference validation citations using [V*] format (e.g., [V1], [V2])
6. **Always provide update_importance** - rate the importance of changes (0-5 scale)

---

═══════════════════════════════════════════════════════════════
## 📤 JSON SCHEMA EXAMPLE
═══════════════════════════════════════════════════════════════

Return a JSON array where each item is a cell array with 8 elements:

```
[column, answer, confidence, original_confidence, updated_confidence, key_citation, update_importance, qc_reasoning]
```

- **column**: Exact field name
- **answer**: Your final QC value. Use `=` if accepting the Updated Value unchanged (saves tokens). Use string value for corrections, or null for blank.
- **confidence**: H (HIGH), M (MEDIUM), or L (LOW) - YOUR confidence in the QC value
- **original_confidence**: H, M, or L - YOUR assessment of the original value
- **updated_confidence**: H, M, or L - YOUR assessment of the validator's proposed value
- **key_citation**: Use `=` to accept the validator's first citation [V1] unchanged. Or use [V*] reference (e.g., [V1], [V2]), [KNOWLEDGE], or [UNVERIFIED].
- **update_importance**: Integer 0-5 rating the net change importance
- **qc_reasoning**: Use `=` if the validator's explanation is adequate (will be left blank). Only provide reasoning when you change a value or need to correct the explanation.

**TOKEN-SAVING CODEWORD `=`:**
- Use `=` for **answer** when accepting the Updated Value unchanged (update_importance 0 or 1)
- Use `=` for **key_citation** when the validator's first citation [V1] is the best supporting evidence
- Use `=` for **qc_reasoning** when the validator's explanation is adequate (leaves field blank)
- This saves output tokens by not repeating long values, citations, or explanations
- Only provide actual qc_reasoning text when you change a value or correct the explanation

**Example:**
```json
[
  ["Revenue", "$158.9B", "H", "M", "H", "[V1] Amazon IR: \"Net sales $158.9B\"", 2, "Corrected from validator's estimate"],
  ["Market Cap", "=", "H", "H", "H", "=", 0, "="],
  ["Sector", "=", "H", "H", "H", "=", 0, "="],
  ["PE_Ratio", "34.18", "M", "M", "M", "[V5]", 1, "Updated to more recent value from MarketBeat"]
]
```

---

═══════════════════════════════════════════════════════════════
## ✅ QC GUIDELINES
═══════════════════════════════════════════════════════════════

### Core Principles

* **CONFIDENCE HIERARCHY ENFORCEMENT:** original_confidence ≤ confidence
  - You MUST ensure: Original Confidence ≤ QC Confidence (generally cannot degrade confidence)
  - **Hierarchy Scale:** HIGH > MEDIUM > LOW (LOW and null are treated as equivalent by the system)
  - If original was HIGH/MEDIUM: QC cannot be LOW (no degrading without strong reason)
  - If original was LOW: QC can go to blank with LOW only if data is clearly false/harmful and no reliable alternative exists
  - **CONFIDENT ABSENCE**: If you're confident something should be absent/not applicable, use language appropriate to the measure (e.g., "N/A", "Not applicable", "No website", "Not publicly traded") with HIGH/MEDIUM confidence, NOT blank. Only LOW confidence answers may be truly blank.
  - If hierarchy is violated, you MUST adjust confidence levels or explain in qc_reasoning
  - Examples:
    - Original=MEDIUM, Updated=Blank → INVALID (use measure-appropriate text with MEDIUM confidence if not applicable, or keep MEDIUM if just unverified)
    - Original=LOW (false data), Updated=Blank with LOW → ACCEPTABLE (removing harmful false data when no replacement exists)
    - Original=LOW, Updated="Not applicable" with HIGH → VALID (confident statement of non-applicability)
    - Original=LOW, Updated=HIGH → VALID (adding reliable data)
    - Original=HIGH, Updated=MEDIUM → INVALID → Must adjust to maintain hierarchy

* **CRITICAL EQUAL CONFIDENCE RULE:**
  - When final answer equals original value (no meaningful change), original_confidence MUST equal confidence
  - When update_importance is 0 or 1, original_confidence MUST equal confidence
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
* Assign **LOW confidence** for blank values that should remain blank (system reclassifies blank+LOW to null)
* Response must be valid JSON array with all required fields
* Respect original entries when there is not evidence to change them - maintain the value and provide a low confidence

### QC Response Fields - ALL MANDATORY FOR EVERY FIELD

* `column`: Field name being QC'd (required)
* `answer`: The QC Entry **MANDATORY FOR ALL QC RESPONSES**
* `confidence`: **MANDATORY** - H/M/L for the QC Entry (must be >= original confidence)
* `original_confidence`: **MANDATORY** - H/M/L for the original value (LOW if original was blank)
* `updated_confidence`: **MANDATORY** - H/M/L for the validator's proposed value
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
