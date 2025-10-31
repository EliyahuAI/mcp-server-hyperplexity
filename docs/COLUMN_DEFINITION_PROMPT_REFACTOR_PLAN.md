# Column Definition Prompt Refactor Plan

**Current Issues:**
1. Restructuring guidance is hardcoded at the top (always visible)
2. No clear section for background research input
3. Doesn't follow PROMPT_STRUCTURING.md guidelines
4. Missing sample_rows output documentation
5. Still references web search (now handled by background research)

---

## Required Changes

### 1. Fix Restructuring Section (Use Conditionals)

**Current (WRONG):**
```markdown
{{#RESTRUCTURING_GUIDANCE}}
═══════════════════════════════════════════════════════════════
## 🔄 RESTRUCTURING MODE - Previous Attempt Failed
═══════════════════════════════════════════════════════════════
[Always visible content]
{{/RESTRUCTURING_GUIDANCE}}
```

**Should Be:**
```markdown
{{#RESTRUCTURING_GUIDANCE}}
═══════════════════════════════════════════════════════════════
## 🔄 RESTRUCTURING MODE - Previous Attempt Failed
═══════════════════════════════════════════════════════════════

**IMPORTANT: This is a RESTRUCTURE after a previous execution found 0 rows.**

### Previous Failure Context
- **Reason**: {{FAILURE_REASON}}

### QC's Restructuring Guidance

**Column Changes:**
{{COLUMN_CHANGES}}

**Requirement Changes:**
{{REQUIREMENT_CHANGES}}

**Search Broadening:**
{{SEARCH_BROADENING}}

### Your Task
Apply the guidance above when redefining the table. The background research findings are still valid - only the table structure needs to change.

---

{{/RESTRUCTURING_GUIDANCE}}
```

**Handler Code:**
```python
# In column_definition_handler.py
variables = {
    'CONVERSATION_CONTEXT': conversation_history,
    'USER_REQUIREMENTS': user_requirements,
    'BACKGROUND_RESEARCH': formatted_research  # NEW
}

# Only add restructuring variables if in restructure mode
if is_restructure:
    variables['RESTRUCTURING_GUIDANCE'] = True  # Shows section
    variables['FAILURE_REASON'] = restructuring_guidance.get('failure_reason', '')
    variables['COLUMN_CHANGES'] = restructuring_guidance.get('column_changes', '')
    variables['REQUIREMENT_CHANGES'] = restructuring_guidance.get('requirement_changes', '')
    variables['SEARCH_BROADENING'] = restructuring_guidance.get('search_broadening', '')
else:
    variables['RESTRUCTURING_GUIDANCE'] = False  # Hides section
```

---

### 2. Add Background Research Input Section

**Add after USER_REQUIREMENTS:**
```markdown
═══════════════════════════════════════════════════════════════
## 📚 BACKGROUND RESEARCH (From Step 0)
═══════════════════════════════════════════════════════════════

The background research phase has already identified authoritative sources and starting tables. Use this information to guide your column design and subdomain structure.

{{BACKGROUND_RESEARCH}}

**How to Use This Research:**
1. **Starting Tables:** Use the sample entities to understand what ID columns should look like
2. **Authoritative Sources:** Reference these in subdomain discovered_list_url fields
3. **Discovery Patterns:** Follow the recommended approach for finding entities
4. **Common Identifiers:** Use these for ID column naming

---
```

---

### 3. Follow PROMPT_STRUCTURING.md

**Required Structure:**
```markdown
# Column Definition Task

═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **RESTRUCTURING GUIDANCE** (if applicable): Previous attempt feedback
2. **YOUR CORE TASK**: Define columns and search strategy
3. **BACKGROUND RESEARCH**: Authoritative sources and starting tables
4. **CONVERSATION CONTEXT**: User's requirements and discussion
5. **DESIGN PRINCIPLES**: Column types, requirements, subdomains
6. **OUTPUT FORMAT**: JSON structure with sample_rows
7. **FINAL REMINDER**: Critical requirements

═══════════════════════════════════════════════════════════════
## 🎯 YOUR CORE TASK
═══════════════════════════════════════════════════════════════

**GOAL:** Define precise column specifications and search strategy using background research as a foundation

**DELIVERABLES:**
- Column definitions (ID columns + research columns)
- Search strategy with 2-10 subdomains
- Sample rows from starting tables (5-15 rows)
- Table name and research context

**KEY RULES:**
1. ✅ Use background research to guide column design
2. ✅ Reference starting tables for ID column structure
3. ✅ Keep ID columns simple (1-5 words)
4. ✅ Offload filtering to research columns
5. ✅ Output sample rows from starting tables

---

[Rest of prompt...]

═══════════════════════════════════════════════════════════════
## 🎯 FINAL REMINDER
═══════════════════════════════════════════════════════════════

**GOAL:** Define columns and strategy using background research

**CRITICAL REQUIREMENTS:**
1. ✅ Use {{BACKGROUND_RESEARCH}} to guide design
2. ✅ Extract 5-15 sample_rows from starting tables
3. ✅ Keep ID columns simple
4. ✅ Reference authoritative sources in subdomains
5. ✅ Apply {{RESTRUCTURING_GUIDANCE}} if provided

**Return your response as valid JSON.**
```

---

### 4. Add Sample Rows Output Documentation

**Add new section before FINAL REMINDER:**
```markdown
═══════════════════════════════════════════════════════════════
## 📤 SAMPLE ROWS OUTPUT (NEW)
═══════════════════════════════════════════════════════════════

**IMPORTANT: Extract 5-15 sample rows from the background research starting tables.**

These rows will be merged with rows from the discovery phase and sent to QC for review. This gives us immediate candidates without waiting for discovery.

### Format

```json
{
  "sample_rows": [
    {
      "id_values": {
        "Company Name": "Anthropic",
        "Website": "anthropic.com"
      },
      "source": "Forbes AI 50 2024",
      "match_score": 0.9,
      "model_used": "column_definition"
    },
    {
      "id_values": {
        "Company Name": "OpenAI",
        "Website": "openai.com"
      },
      "source": "Forbes AI 50 2024",
      "match_score": 0.95,
      "model_used": "column_definition"
    }
  ]
}
```

### How to Populate

1. **Look at starting_tables** from background research
2. **Extract 5-15 sample entities** (prefer entities with complete information)
3. **Fill ID column values** only (leave research columns empty)
4. **Set match_score** based on how well the entity fits requirements (0.7-0.95 typical)
5. **Set source** to the starting table name
6. **Set model_used** to "column_definition"

### Deduplication

- Discovery phase will find more rows via web search
- If discovery finds the same entity, it takes precedence (better model quality scoring)
- Column definition rows act as a "baseline" that discovery can improve upon
- QC will review all merged rows together

---
```

---

### 5. Remove Web Search References

**Remove sections like:**
- "STEP 1: Find Authoritative Lists (CRITICAL - Do This First!)"
- "Use web search to find..."
- Instructions about searching for lists

**Replace with:**
- "Use the authoritative sources from background research"
- "Reference the starting tables provided"
- "The research phase has already found the lists - use them"

---

## Implementation Priority

1. **HIGH PRIORITY:**
   - Fix restructuring conditionals (breaks current logic)
   - Add {{BACKGROUND_RESEARCH}} injection
   - Update handler to pass formatted research

2. **MEDIUM PRIORITY:**
   - Add sample_rows documentation
   - Follow PROMPT_STRUCTURING.md structure
   - Clean up web search references

3. **LOW PRIORITY:**
   - Polish examples
   - Add more guidance on using starting tables

---

## Handler Changes Needed

**column_definition_handler.py:**

```python
async def define_columns(
    self,
    conversation_context: Dict[str, Any],
    background_research_result: Dict[str, Any] = None,  # NEW
    model: str = "claude-sonnet-4-5",
    max_tokens: int = 8000
) -> Dict[str, Any]:
    """
    Args:
        background_research_result: Output from background_research_handler (REQUIRED)
    """

    # Format research for injection
    if background_research_result:
        from .background_research_handler import BackgroundResearchHandler
        research_handler = BackgroundResearchHandler(None, None, None)
        formatted_research = research_handler.format_research_for_column_definition(
            background_research_result
        )
    else:
        formatted_research = "(No background research available)"

    # Check for restructuring
    restructuring_guidance = conversation_context.get('restructuring_guidance', {})
    is_restructure = restructuring_guidance.get('is_restructure', False)

    # Build variables
    variables = {
        'CONVERSATION_CONTEXT': conversation_history,
        'USER_REQUIREMENTS': user_requirements,
        'BACKGROUND_RESEARCH': formatted_research  # NEW
    }

    # Conditionally add restructuring variables
    if is_restructure:
        variables['RESTRUCTURING_GUIDANCE'] = True
        variables['FAILURE_REASON'] = restructuring_guidance.get('failure_reason', '')
        variables['COLUMN_CHANGES'] = restructuring_guidance.get('column_changes', '')
        variables['REQUIREMENT_CHANGES'] = restructuring_guidance.get('requirement_changes', '')
        variables['SEARCH_BROADENING'] = restructuring_guidance.get('search_broadening', '')
    else:
        variables['RESTRUCTURING_GUIDANCE'] = False

    prompt = self.prompt_loader.load_prompt('column_definition', variables)

    # Call API (no web search needed - research already done)
    api_response = await self.ai_client.call_structured_api(
        prompt=prompt,
        schema=schema,
        model=model,
        max_tokens=max_tokens,
        debug_name="column_definition"
    )

    # Extract sample_rows if present
    structured_response = api_response.get('response', {})
    sample_rows = structured_response.get('sample_rows', [])

    if sample_rows:
        logger.info(f"Column definition provided {len(sample_rows)} sample rows from starting tables")

    result.update({
        'sample_rows': sample_rows  # NEW
    })
```

---

## Testing Plan

1. **Normal Flow:** Verify background research → column definition works
2. **Restructure Flow:** Verify restructuring section only shows when needed
3. **Sample Rows:** Verify column definition extracts rows from starting tables
4. **Deduplication:** Verify discovery rows take precedence over column definition rows

---

## Next Steps

1. Update column_definition.md with proper structure
2. Update column_definition_handler.py to accept research
3. Wire into execution.py
4. Test end-to-end
