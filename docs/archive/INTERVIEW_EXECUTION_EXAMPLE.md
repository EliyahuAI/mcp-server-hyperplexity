# Interview Handler - Example Output with trigger_execution

## Scenario: Two-Turn Approval Workflow

### Turn 1: Present Table Sketch for Approval

**User Input:**
```
"I'm from Eliyahu.AI - find me companies that recently posted GenAI-related jobs so I can reach out"
```

**AI Response (trigger_execution=false):**
```json
{
  "trigger_execution": false,
  "follow_up_question": "I'll create a table with:\n\n**ID columns**: Company Name, Website\n\n**Research questions**:\n- Recent GenAI job postings (titles, dates, descriptions)\n- Company focus (B2B, B2C, infrastructure, etc.)\n- Outreach email draft (personalized to their posting)\n\n**Scope**: ~20 AI companies actively hiring for GenAI roles\n\nDoes this match your needs? If yes, I'll need 3-4 minutes to build the complete table.",
  "context_web_research": ["Eliyahu.AI company background and services"],
  "processing_steps": ["Researching Eliyahu.AI Context", "Identifying Target Companies", "Generating Preview Rows"],
  "table_name": "GenAI Hiring Companies for Outreach"
}
```

**What happens:**
- User sees the table sketch
- System waits for approval
- No execution pipeline starts yet

---

### Turn 2: User Approves

**User Input:**
```
"Yes, go ahead!"
```

**AI Response (trigger_execution=true):**
```json
{
  "trigger_execution": true,
  "follow_up_question": "Perfect! I'll need 3-4 minutes to:\n1. Define precise columns and search strategy\n2. Discover 20 matching AI companies\n3. Populate all data\n4. Validate everything\n\nStarting execution now...",
  "context_web_research": ["Eliyahu.AI company background and services"],
  "processing_steps": [
    "Defining Columns and Search Strategy",
    "Discovering 20 AI Companies",
    "Populating All Data",
    "Validating Results"
  ],
  "table_name": "GenAI Hiring Companies for Outreach"
}
```

**What happens:**
- System starts 3-4 minute execution pipeline
- Phase 2 begins:
  1. Column Definition (~30s)
  2. Row Discovery (~2 min, parallel)
  3. Table Population (~90s)
  4. Validation (~10s)
- User gets complete, validated table

---

## Alternative Scenario: Needs Clarification

### Turn 1: Unclear Request

**User Input:**
```
"I need to research some papers"
```

**AI Response (trigger_execution=false):**
```json
{
  "trigger_execution": false,
  "follow_up_question": "I'd like to help you create a research table for papers! What kind of papers and information are you interested in?\n\n**Paper type**: Are these (A) academic research papers, (B) industry whitepapers, or (C) something else?\n\n**Information to track**: Would you like to focus on:\n- **Research metrics**: citations, h-index, publication venue\n- **Content analysis**: methodology, datasets, key findings\n- **Practical application**: use cases, reproducibility, code availability\n\n**Scope**: Are you thinking 10-15 papers for focused review or 30-40 for comprehensive analysis?",
  "context_web_research": [],
  "processing_steps": [],
  "table_name": ""
}
```

**What happens:**
- System asks for clarification
- No execution starts
- Conversation continues

---

## Key Differences from Old Workflow

### OLD (trigger_preview):
```json
{
  "trigger_preview": true,
  "follow_up_question": "Here is what I understand... Shall I generate a preview for you to review? We can refine the table if it is not what you are expecting."
}
```
- Generated a "preview" with 3 rows
- User could refine and regenerate
- Quality dropped in final table
- Confusing: what's the difference between preview and final?

### NEW (trigger_execution):
```json
{
  "trigger_execution": true,
  "follow_up_question": "Does this match your needs? If yes, I'll need 3-4 minutes to build the complete table."
}
```
- Presents a sketch for approval
- User approves BEFORE execution
- One-shot execution builds complete table
- Clear: 3-4 minute pipeline, no refinement after

---

## Backward Compatibility

The implementation handles old responses gracefully:

```python
# If AI returns old field name
trigger_execution = structured_data.get('trigger_execution',
                                       structured_data.get('trigger_preview', False))
```

This ensures:
- Old cached responses still work
- Gradual migration is safe
- No breaking changes
