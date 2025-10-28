# Multiplex Field Validation

═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **YOUR RESEARCH GOAL**: The specific data points you need to look up for this entity
2. **HOW TO VERIFY**: Guidance on checking accuracy and assigning confidence
3. **CONTEXT**: Row identification information
4. **PREVIOUS RESULTS**: Other validated columns for this row
5. **FIELD GROUP**: Related fields being validated together
6. **DETAILED FIELD REQUIREMENTS**: Format, examples, and notes for each field
7. **CONFIDENCE RUBRIC**: How to assign confidence levels
8. **RESPONSE FORMAT**: JSON structure and requirements

═══════════════════════════════════════════════════════════════
## 🎯 YOUR RESEARCH GOAL - Fields to Research
═══════════════════════════════════════════════════════════════

**Your goal is to RESEARCH the following field(s) for this specific entity:**

{validation_intro}

**What to do**: Use web search to find current, authoritative information about these specific data points for this entity. Look up the actual values (prices, metrics, news, projections, etc.) from reliable sources.

---

═══════════════════════════════════════════════════════════════
## 📚 HOW TO VERIFY - Accuracy Standards and Preferred Sources
═══════════════════════════════════════════════════════════════

**Use these standards when checking the accuracy of the data you research:**

{general_notes}

**Remember**: Focus your web search on finding the actual data values for the entity above. These standards tell you HOW to assess accuracy and which sources to prefer, not WHAT to search for.

---

═══════════════════════════════════════════════════════════════
## 🔍 CONTEXT INFORMATION
═══════════════════════════════════════════════════════════════

Makes sure your response is within this context:

{context}

---

═══════════════════════════════════════════════════════════════
## 📊 CURRENT RESULTS FOR OTHER COLUMNS
═══════════════════════════════════════════════════════════════

Additional context come from validated entries for other columns (with their confidence levels):

{previous_results}

---

═══════════════════════════════════════════════════════════════
## 🔧 FIELD GROUP INFORMATION
═══════════════════════════════════════════════════════════════

This is the group of fields that you are reviewing and updating:

{group_name}

{group_description}

---

═══════════════════════════════════════════════════════════════
## 📝 FIELDS TO REVIEW AND UPDATE IF NEEDED
═══════════════════════════════════════════════════════════════

{fields_to_validate}

---

═══════════════════════════════════════════════════════════════
## ⭐ CONFIDENCE RUBRICS
═══════════════════════════════════════════════════════════════

Assign confidence levels to the original and updated values:

- **HIGH**: Claim is a widely accepted fact, directly verified by authoritative source, or straightforward calculation that matches the guidance provided, without cause for pause. Claim matches the guidance provided.

- **MEDIUM**: Good estimates, confident projections, or respectable but not definitive sources that are consistent with the guidance .provided.

- **LOW**: Weak/conflicting sources, uncertainty, no information available, or that does not match the guidance provided - if you cannot verify a value- it is low confidence

- **None**: For blank values that should remain blank (no confidence assignment needed). If the orignal valie is blank, and you have nothing to add, provied a null confidence.

---

═══════════════════════════════════════════════════════════════
## 📤 RESPONSE FORMAT
═══════════════════════════════════════════════════════════════

Please respond with a JSON array containing an object for each field.

### JSON SCHEMA EXAMPLE

{json_schema_example}

### IMPORTANT

- For each field, use the provided examples as guidance for expected formats and values.
- Do not use quotation marks around your responses.
- Assess both the quality of your updated answer (confidence) and the quality of the original value (original_confidence) using the same confidence rubric.
- Only provide a different validated value if you can achieve improve significantly on than the original value.
- NEVER replace an original value with an updated value in which you have lower confidence. If you are more confident in the Original value, why would you update it with a value that you are less confident in!!?
- The response MUST be valid JSON array format
- Each field must have its own object in the array
- Include the exact column name in each object - exactly as defined in the FIELD input
- Place actual URLs in the sources arrays, not reference numbers
- When web search is available, perform web search only when helpful and include direct quotes from web search results or authoritative sources in the reasoning field. When web search is not available, or not helpful, use your training knowledge and cite knowledge cutoff limitations where relevant.
- Extract specific text snippets that support your answer when available, include the source page title if it is available for context.
- If you cannot find information for a field that was originally blank, assign None confidence if the field should remain blank
- Use provided examples to guide your updates format and expected values
- Always include all required fields: column, answer, confidence, original_confidence, reasoning, sources
- Use newline characters correctly so that they are formatted in an excel cell, perticularly for bullets, lists, and other formatted text.
- Double check your updated response and confidence - speak precisely, there is not room for error.
