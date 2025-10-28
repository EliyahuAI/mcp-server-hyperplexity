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

**CRITICAL: You MUST provide FULL QC RESPONSE for ALL FIELDS - not just fields that need changes. Every field gets a complete QC entry with answer, confidence, original_confidence, updated_confidence, qc_reasoning, and qc_citations.**

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
- **original_confidence**: YOUR assessment of confidence in the Original/Current input value
- **updated_confidence**: YOUR assessment of the validator's Updated Value confidence
- **qc_reasoning**: Explain your QC decision and any changes you made
- **qc_citations**: Provide citations supporting your QC decision
- **update_importance**: Rate the importance of changes from Original to your QC answer (0-5 scale with explanation)

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

- **LOW**: Weak/conflicting sources, uncertainty, no information available, or that does not match the guidance provided - if you cannot verify a value- it is low confidence

- **None**: For blank values that should remain blank (no confidence assignment needed). If the orignal valie is blank, and you have nothing to add, provied a null confidence.

---

═══════════════════════════════════════════════════════════════
## 📝 QC RESPONSES
═══════════════════════════════════════════════════════════════

**YOU MUST PROVIDE QC OUTPUT FOR EVERY SINGLE FIELD** - no exceptions. For each field:

1. **Always provide your QC answer** - either confirm the orignal or updated value or provide a replacement
2. **Always assign your QC confidence** - your confidence in the QC answer
3. **Always review and confirm/adjust original_confidence** - ensure hierarchy compliance
4. **Always provide qc_reasoning** - explain your QC assessment
5. **Always provide qc_citations** - support your QC decision
6. **Always provide key_citation** - provide a targeted excerpt or reasoning for your answer.

---

═══════════════════════════════════════════════════════════════
## 📤 JSON SCHEMA EXAMPLE
═══════════════════════════════════════════════════════════════

{json_schema_example}

---

═══════════════════════════════════════════════════════════════
## ✅ QC GUIDELINES
═══════════════════════════════════════════════════════════════

### Core Principles

* **CONFIDENCE HIERARCHY ENFORCEMENT:** original_confidence ≤ confidence
  - You MUST ensure: Original Confidence ≤ QC Confidence
  - If this hierarchy is violated, you MUST adjust the confidence levels to maintain this order
  - Example: If Original=HIGH, QC Confidence=MEDIUM, you MUST lower Original to MEDIUM or raise QC Confidence to HIGH. Generally lower confidences when you are not sure about the inconsistency.

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
* `qc_reasoning`: Your detailed QC assessment
* `qc_citations`: Supporting citation for your QC decision

### Response Requirements

* Include exact column name as defined in FIELD input
* Use complete ad real URLs in sources arrays (not reference numbers)
* Include direct quotes from citations in key_citation and reasoning when available
* Use proper newline formatting for Excel cells (bullets, lists, etc.)
* Assign **None confidence** for blank values that should remain blank
* Response must be valid JSON array with all required fields
* If you have access to web search and you dont have confidence in the current value, perform web search and provide a new citation. **This is critical when the value can be obtained from a web search.**
* Respect original entries when there is not evidence to change them. This is particularly true when you can't find evidence to confirm or reject the initial value - maintain the value and provide a low confidence.

### QC Response Fields - ALL MANDATORY FOR EVERY FIELD

* `column`: Field name being QC'd (required)
* `answer`: The QC Entry **MANDATORY FOR ALL QC RESPONSES**
* `qc_reasoning`: Detailed explanation of why QC revision was necessary (required)
* `confidence`: **MANDATORY FOR ALL QC RESPONSES** - the final confidence level for the QC Entry (must be higher than or equal to the original confidence)
* `original_confidence`: **MANDATORY FOR ALL QC RESPONSES** - the final confidence level for the original value (must be lower than or equal to the QC confidence).
* `updated_confidence`: **MANDATORY FOR ALL QC RESPONSES** - the final confidence level for the updated value
* `qc_citations`: Key supporting citation - **ABSOLUTELY REQUIRED for EVERY SINGLE FIELD** regardless of whether QC changes are made or not (see formatting below). This field is mandatory for all responses.
* `update_importance`: **MANDATORY FOR ALL QC RESPONSES** - A 0-5 scale rating that measures the NET CHANGE from the original input value to the final QC answer, considering both the significance of the change AND your confidence in it. This is NOT about the QC process itself - it's about the overall impact of the change from what was originally provided to what you're now concluding. High scores require BOTH importance AND confidence. Format: "N - Explanation text" where N is 0-5. Score 0 requires no explanation.

**CRITICAL CONFIDENCE RULE: When there is no meaningful change between the final answer and the original value, OR when update_importance is 0 or 1, the QC original confidence (original_confidence) MUST be identical to the final QC confidence (confidence). This is NON-NEGOTIABLE.**

### Update Importance Scale

- **0**: No meaningful net change from original to final answer (no explanation needed). Original value confirmed or trivial formatting adjustments.
- **1**: Minor change from original with low confidence OR minor clarification with limited impact. Small net difference with limited decision-making impact.
- **2**: Moderate net change with medium confidence. Notable difference from original but not critical to core purpose, OR uncertain adjustment.
- **3**: Significant net change with medium-to-high confidence. Important difference from original that affects understanding but not immediately actionable.
- **4**: Major net change with high confidence. Critical difference from original that directly impacts decision-making or core table purpose.
- **5**: Critical net change with very high confidence. Essential difference from original requiring immediate attention and fundamentally changing interpretation or action items.

**Examples:**
- "0" (no explanation)
- "1 - Minor formatting correction to match style guide"
- "2 - Updated revenue estimate based on limited data"
- "3 - Corrected product category affecting market segmentation"
- "4 - Volatility in market price for Amazon results in hold investment recommendation"
- "5 - Company bankruptcy filing changes investment status to immediate sell"

### Key Citation Formatting (`qc_citations`)

Provide the most relevant citation that supports the Updated or, if QCed, the QC Entry. This is expected for all fields. You have two options:

**Option 1: Reference existing validation citations (greatly preferred):**
* Use the existing citation number (e.g., [1], [2], [3]) from the validation sources shown above

**Option 2: Create a new citation from web search (when web search is available and critically needed):**
* Perform web search to find more authoritative or recent sources, indicate that this a QC citation using the prefix [QC]

**Key Citation Formatting:**
* Format: [Citation No / QC Citation No] Source Title - [Additional context if needed]... "Key excerpt from the citation that supports your final answer" ... (URL)
* Extract the most relevant 1-2 sentences and put them in for emphasis
* Use "..." to show truncation of longer quotes or to connect key excerpts
* Include the full URL in parentheses at the end
* Keep the entire citation as a single line for Excel cell comments

**Key Citation Requirements - MANDATORY FOR ALL FIELDS:**
* **Fields WITHOUT useful citations**: MUST still provide `qc_citations` and either:
  - If consistent with your training knowledge, Reference general knowledge source with format "[KNOWLEDGE]  Key supporting fact (your model name, training date)
  - If unverifiable and not consistent with your training knowledge, state "[UNVERIFIED] No authoritative source found: reasoning for uncertainty (requires verification)
* **Fields requiring no QC changes**: MUST still provide `qc_citations` confirming the accuracy of existing values

**Key Citation Examples:**
* **Using existing or QC citation:** [QC 1] Amazon Q2 2025 Earnings Report - [including AWS]... "Net sales increased 13% to $167.7 billion ... confirming the market cap calculation" (https://ir.aboutamazon.com/2025_Earnings_Results)
* **Using model knowledge:** [KNOWLEDGE] Amazon provides a range of services including AWS. (Claude 4 Sonnet, Training date: 2025-01-01)
* **Unverifyable:** [UNVERIFIED] No authoritative source found: It is not clear that Amazon has a special local market in Uganda, leaving original value as is. (requires verification)

---

**Final Value ('answer') Priority:** QC Value > Updated Value > Original Value
