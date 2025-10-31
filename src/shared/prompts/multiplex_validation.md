# Multiplex Field Validation

═══════════════════════════════════════════════════════════════
## 🔍 FOCUSED RESEARCH QUESTIONS - USE THIS FOR WEB SEARCH
═══════════════════════════════════════════════════════════════

**Entity Context:** {context}

**Research Questions:**
{research_questions}

**Suggested Search Query:** `{suggested_search}`

**IMPORTANT: Use the above information to formulate your web searches. Focus on finding specific, current information about these exact questions.**

═══════════════════════════════════════════════════════════════

---

═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **FOCUSED RESEARCH QUESTIONS**: Simple, direct questions for web search (ABOVE)
2. **WHAT TO RESEARCH**: The specific information you need to look up
3. **BACKGROUND CONTEXT**: Entity identification (NOT what to research)
4. **FULL ORIGINAL ROW CONTEXT**: All original unvalidated data for reference (NOT what to research)
5. **ACCURACY STANDARDS**: How to verify information quality (NOT what to research)
6. **PREVIOUS DATA**: Already validated fields for reference
7. **FIELD DETAILS**: Format requirements and examples
8. **CONFIDENCE LEVELS**: How to assign confidence ratings
9. **RESPONSE FORMAT**: JSON structure

═══════════════════════════════════════════════════════════════
## 🎯 WHAT TO RESEARCH - Your Research Task
═══════════════════════════════════════════════════════════════

{validation_intro}

**Your task**: Use web search to find the CURRENT, ACTUAL VALUES for the fields above. Search for the specific data points (prices, projections, news, metrics, etc.) for the entity described in the context below.

---

═══════════════════════════════════════════════════════════════
## 📍 BACKGROUND CONTEXT - Entity Information (NOT what to research)
═══════════════════════════════════════════════════════════════

**This section tells you WHICH entity you're researching. This is CONTEXT, not research targets:**

{context}

---

═══════════════════════════════════════════════════════════════
## 📄 FULL ORIGINAL ROW CONTEXT - All Original Data (NOT what to research)
═══════════════════════════════════════════════════════════════

**Complete original row data for context (unvalidated values - for reference only):**

{original_row_context}

---

═══════════════════════════════════════════════════════════════
## ✅ ACCURACY STANDARDS - How to Verify Quality (NOT what to research)
═══════════════════════════════════════════════════════════════

**These are QUALITY STANDARDS for verifying the information you find. Use preferred sources and formatting:**

{general_notes}

---

═══════════════════════════════════════════════════════════════
## 📊 PREVIOUS DATA - Already Validated Fields (Reference only)
═══════════════════════════════════════════════════════════════

**Other fields already validated for this entity (for context/reference):**

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
## ⭐ CONFIDENCE RUBRICS
═══════════════════════════════════════════════════════════════

Assign confidence levels to the original and updated values:

- **HIGH**: Claim is a widely accepted fact, directly verified by authoritative source, or straightforward calculation that matches the guidance provided, without cause for pause. Claim matches the guidance provided.

- **MEDIUM**: Good estimates, confident projections, or respectable but not definitive sources that are consistent with the guidance .provided.

- **LOW**: Weak/conflicting sources, uncertainty, no information available, or that does not match the guidance provided - if you cannot verify a value- it is low confidence

- **None**: For blank values that should remain blank (no confidence assignment needed). If the orignal valie is blank, and you have nothing to add, provied a null confidence.

---

═══════════════════════════════════════════════════════════════
## 🔍 REMINDER: FOCUSED RESEARCH QUESTIONS
═══════════════════════════════════════════════════════════════

**Before generating your response, remember to search for:**

{research_questions}

**Suggested Search Query:** `{suggested_search}`

**Entity:** {context}

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
- Do not research the context and guidance - research only the Current Value in the context provided
- Double check your updated response and confidence - speak precisely, there is not room for error.
