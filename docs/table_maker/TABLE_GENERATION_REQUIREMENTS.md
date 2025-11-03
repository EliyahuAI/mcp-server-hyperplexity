# Table Generation System - Master Requirements

## Overview
Conversational AI system for designing research tables through natural language dialogue, following the same architectural pattern as the config generation system.

## Phase 1: Standalone Local Implementation
Build and test in isolated folder structure before integration.

## Phase 2: Integration into Config Lambda
Integrate tested code into existing lambda infrastructure.

---

## Architecture Model

**Follow Config Generation Pattern:**
- Prompts as markdown files with `{{VARIABLE}}` placeholders
- Conversation logs stored and passed iteratively
- Structured schema for AI responses
- Use existing `ai_api_client.py` for API calls
- Similar function signatures and flow

---

## Core Functionality

### 1. Conversational Table Design

**User Flow:**
1. User describes research problem
2. AI proposes table structure (rows + columns)
3. Back-and-forth refinement through conversation
4. User confirms → Generate CSV + AI config
5. Optional: Expand rows or pre-fill data

**Conversation Elements:**
- **Rows**: 1-3 "identification columns" + sample data
- **Columns**: Research questions with clear descriptions
- **Iterative refinement**: User feedback shapes structure
- **Conversation history**: Full log maintained and passed to AI

### 2. Row Expansion Function

**Purpose:** Generate additional rows based on user criteria

**Example:**
- Initial: 3 sample startup rows
- User: "Add 10 more Y Combinator companies from 2023"
- System: Expands to 13 rows with new examples

**Implementation:**
- Separate prompt for row expansion
- Takes existing table structure + expansion request
- Returns additional row data
- Appends to existing CSV

### 3. Configuration Generation

**Input:** Final conversation state with confirmed table structure

**Output:** Full AI config JSON (using existing config generation logic)

**Process:**
1. Extract column definitions from conversation
2. Map to validation_targets
3. Create appropriate search_groups
4. Generate config using existing system
5. Store with conversation metadata

---

## File Structure

### Standalone Development Folder
```
table_maker/
├── requirements.txt                  # Dependencies
├── README.md                        # Local testing instructions
├── prompts/
│   ├── table_initial.md            # Initial conversation prompt
│   ├── table_refinement.md         # Refinement prompt
│   ├── row_expansion.md            # Row expansion prompt
│   └── config_generation.md        # Config from table prompt
├── schemas/
│   ├── conversation_response.json  # AI response schema
│   ├── row_expansion_response.json # Row expansion schema
│   └── table_structure.json        # Final table structure schema
├── src/
│   ├── __init__.py
│   ├── conversation_handler.py     # Main conversation logic
│   ├── row_expander.py            # Row expansion logic
│   ├── table_generator.py         # CSV generation
│   ├── config_generator.py        # Config generation
│   ├── prompt_loader.py           # Load & fill prompt templates
│   └── schema_validator.py        # Validate AI responses
├── tests/
│   ├── __init__.py
│   ├── test_conversation.py       # Test conversation flow
│   ├── test_row_expansion.py      # Test row expansion
│   ├── test_table_generation.py   # Test CSV generation
│   └── test_integration.py        # End-to-end tests
└── examples/
    ├── example_conversation.json   # Sample conversation log
    ├── example_table.csv          # Sample generated table
    └── example_config.json        # Sample generated config
```

---

## Prompt Templates

### table_initial.md

```markdown
You are helping a researcher design a table for systematic research and data validation.

## User's Research Description
{{USER_MESSAGE}}

## Your Task
1. **Understand** their research problem and goals
2. **Propose row structure**:
   - 1-3 "identification columns" that uniquely define each row
   - These should be densely populated data (NOT research questions)
   - Provide 3-5 realistic sample rows with example data
3. **Propose research columns**:
   - 5-10 specific research questions/data points to investigate
   - Each with clear description of what information to collect
   - Specify format (String, Number, URL, Date, etc.)
   - Assign importance level (CRITICAL, HIGH, MEDIUM, LOW)
4. **Ask clarifying questions** if anything is unclear or ambiguous

## Guidelines
- Identification columns: Company Name, Paper Title, Product ID, etc.
- Research columns: things to look up, validate, or investigate
- Be specific and actionable
- Focus on feasibility - can this realistically be researched?
- Aim for 5-15 total columns (including identification)

## Output Format
Respond using the structured schema provided.
```

### table_refinement.md

```markdown
You are refining a research table design based on user feedback.

## Conversation History
{{CONVERSATION_HISTORY}}

## Current Table Proposal
{{CURRENT_PROPOSAL}}

## User's Latest Feedback
{{USER_MESSAGE}}

## Your Task
1. **Analyze** user's feedback carefully
2. **Update** ONLY the aspects they mentioned
3. **Preserve** everything else that's working
4. **Explain** your changes clearly
5. **Ask** follow-up questions if needed

## Important
- Don't make changes the user didn't ask for
- Don't remove columns/rows unless explicitly requested
- Keep the same structure unless told to change it
- Be precise about what changed and why

## Output Format
Respond using the structured schema provided.
```

### row_expansion.md

```markdown
You are expanding the rows of an existing research table.

## Current Table Structure
{{TABLE_STRUCTURE}}

## Existing Rows
{{EXISTING_ROWS}}

## User's Expansion Request
{{EXPANSION_REQUEST}}

## Your Task
Generate {{ROW_COUNT}} additional rows that:
1. Match the existing column structure exactly
2. Fit the criteria specified in the expansion request
3. Use realistic, diverse example data
4. Don't duplicate existing rows

## Output Format
Return a list of row objects matching the existing structure.
```

---

## Schemas

### conversation_response.json

```json
{
  "type": "object",
  "required": ["ai_message", "proposed_rows", "proposed_columns", "clarifying_questions", "confidence", "ready_to_generate", "reasoning"],
  "properties": {
    "ai_message": {
      "type": "string",
      "description": "Natural language response to the user"
    },
    "proposed_rows": {
      "type": "object",
      "properties": {
        "identification_columns": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Names of columns that identify each row"
        },
        "sample_rows": {
          "type": "array",
          "items": {"type": "object"},
          "description": "Sample row data as key-value pairs"
        }
      }
    },
    "proposed_columns": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "description": {"type": "string"},
          "format": {"type": "string"},
          "importance": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
          "is_identification": {"type": "boolean"}
        }
      }
    },
    "clarifying_questions": {
      "type": "string",
      "description": "Questions for the user (empty if none)"
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "Confidence in current proposal (0-1)"
    },
    "ready_to_generate": {
      "type": "boolean",
      "description": "Whether table is ready to be generated"
    },
    "reasoning": {
      "type": "string",
      "description": "Why this structure makes sense"
    }
  }
}
```

### row_expansion_response.json

```json
{
  "type": "object",
  "required": ["expanded_rows", "reasoning"],
  "properties": {
    "expanded_rows": {
      "type": "array",
      "items": {"type": "object"},
      "description": "Additional rows matching table structure"
    },
    "reasoning": {
      "type": "string",
      "description": "How these rows were selected/generated"
    }
  }
}
```

---

## Implementation Requirements

### 1. Conversation Handler (conversation_handler.py)

```python
class TableConversationHandler:
    def __init__(self, ai_client):
        self.ai_client = ai_client
        self.conversation_log = []

    async def start_conversation(self, user_message: str) -> dict:
        """Initialize conversation with user's research description"""

    async def continue_conversation(self, user_message: str) -> dict:
        """Continue conversation with user feedback"""

    def get_conversation_history(self) -> list:
        """Return full conversation log"""

    def get_current_proposal(self) -> dict:
        """Return latest table proposal"""
```

### 2. Row Expander (row_expander.py)

```python
class RowExpander:
    def __init__(self, ai_client):
        self.ai_client = ai_client

    async def expand_rows(
        self,
        table_structure: dict,
        existing_rows: list,
        expansion_request: str,
        row_count: int = 10
    ) -> dict:
        """Generate additional rows based on criteria"""
```

### 3. Table Generator (table_generator.py)

```python
class TableGenerator:
    def generate_csv(
        self,
        columns: list,
        rows: list,
        output_path: str
    ) -> dict:
        """Generate CSV file from table structure"""

    def append_rows(
        self,
        csv_path: str,
        new_rows: list
    ) -> dict:
        """Append rows to existing CSV"""
```

### 4. Config Generator (config_generator.py)

```python
class ConfigGenerator:
    def __init__(self, ai_client):
        self.ai_client = ai_client

    async def generate_config_from_table(
        self,
        table_structure: dict,
        conversation_history: list
    ) -> dict:
        """Generate AI config from final table structure"""
```

### 5. Prompt Loader (prompt_loader.py)

```python
class PromptLoader:
    def __init__(self, prompts_dir: str):
        self.prompts_dir = prompts_dir

    def load_prompt(self, template_name: str, variables: dict) -> str:
        """Load markdown prompt and replace {{VARIABLES}}"""

    def replace_variables(self, template: str, variables: dict) -> str:
        """Replace {{VAR}} with values"""
```

---

## Testing Requirements

### Unit Tests
- Prompt loading and variable replacement
- Schema validation
- CSV generation
- Row expansion logic

### Integration Tests
- Full conversation flow (3-5 turns)
- Row expansion on generated table
- Config generation from final structure
- End-to-end: conversation → CSV + config

### Test Data
- Sample research descriptions
- Expected table structures
- Known good configs

---

## Success Criteria

### Standalone System Must:
1. ✅ Complete 3-turn conversation successfully
2. ✅ Generate valid CSV from conversation
3. ✅ Expand rows with new criteria
4. ✅ Generate valid AI config matching existing schema
5. ✅ Handle conversation history correctly
6. ✅ Validate all AI responses against schemas
7. ✅ Pass all integration tests

### Ready for Integration When:
- All tests passing
- Local CLI demo works end-to-end
- Code follows existing patterns
- Documentation complete

---

## Integration into Config Lambda

### Files to Modify
- `src/lambdas/config/config_lambda_function.py` - Add table generation routing
- `src/lambdas/config/prompts/` - Add table generation prompts
- `src/lambdas/interface/actions/` - Add table generation actions
- `src/lambdas/interface/handlers/http_handler.py` - Add action routing

### New Lambda Actions
- `start_table_conversation` - Initialize conversation
- `continue_table_conversation` - Continue with user feedback
- `expand_table_rows` - Add rows to existing table
- `generate_table_config` - Create config from finalized structure

### Integration Approach
1. Copy tested code from `table_maker/` to lambda structure
2. Adapt to lambda event/response format
3. Integrate with existing `ai_api_client.py`
4. Add to config lambda routing
5. Test via interface lambda locally
6. Deploy to dev environment
7. Full integration testing

---

## Development Phases

### Phase 1: Standalone Development (Days 1-5)
1. Set up folder structure
2. Implement core classes
3. Create prompt templates
4. Write unit tests
5. Build integration tests
6. Create CLI demo

### Phase 2: Integration (Days 6-8)
1. Adapt code for lambda environment
2. Add to config lambda
3. Create interface lambda actions
4. Test locally with both lambdas
5. Deploy to dev
6. Integration testing

### Phase 3: Frontend (Days 9-10)
1. Add "Create New Table" UI
2. Implement conversation interface
3. Add table preview
4. Test end-to-end with real users

---

## Notes

- Use existing `ai_api_client.py` - don't recreate API logic
- Follow config generation patterns closely
- Model: `claude-sonnet-4-5` for quality
- Store conversation logs for debugging/improvement
- Support resuming conversations
- Handle API errors gracefully
- Validate all inputs and outputs

---

## Future Enhancements (Not in Initial Scope)

- Apps system (quick-start templates)
- Table synthesis (analyze completed tables)
- Multi-user collaboration
- Version control for table structures
- Template library for common research patterns
