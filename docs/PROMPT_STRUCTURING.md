# Prompt Structuring Guide

This document defines the standardized structure for all AI prompts in the system and verifies that prompts match their corresponding JSON schemas.

## Standard Prompt Structure

All prompts in this system follow a consistent structure to maximize clarity and reduce AI errors:

### 1. **Prompt Map** (at the beginning)
```markdown
═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **SECTION 1**: Brief description
2. **SECTION 2**: Brief description
...
```

**Purpose**: Provides a navigation overview so the AI understands what information is coming and can prepare accordingly.

### 2. **Core Task** (immediately after map)
```markdown
═══════════════════════════════════════════════════════════════
## 🎯 YOUR CORE TASK / MISSION
═══════════════════════════════════════════════════════════════

**GOAL:** [One sentence goal]

**DELIVERABLES:**
- Item 1
- Item 2

**KEY RULES:**
1. ✅ Rule 1
2. ✅ Rule 2
```

**Purpose**: States the primary objective, deliverables, and critical rules upfront before any details.

### 3. **Context Sections** (middle content)
```markdown
═══════════════════════════════════════════════════════════════
## 📚 SECTION TITLE (with emoji)
═══════════════════════════════════════════════════════════════

Content here...
```

**Purpose**: Provides necessary background information, examples, and guidance. Each section clearly separated by visual dividers.

### 4. **Final Reminder** (at the end)
```markdown
═══════════════════════════════════════════════════════════════
## 🎯 FINAL REMINDER - Your Core Requirements
═══════════════════════════════════════════════════════════════

**GOAL:** [Repeat goal]

**CRITICAL REQUIREMENTS:**
1. ✅ Requirement 1
2. ✅ Requirement 2
...

**Return your [output type] using the [tool_name] tool.**
```

**Purpose**: Repeats the most critical requirements and deliverables to ensure the AI doesn't miss them after processing all the middle content.

## Visual Elements

### Dividers
Use `═══════════════════════════════════════════════════════════` to separate major sections.

### Emojis for Section Identification
- 📋 Prompt Map / Your Task
- 🎯 Core Task / Mission / Final Reminder
- ⚠️ Critical Requirements / Warnings
- 📚 Context / Information / Background
- 🤖 Model / AI settings
- 🔍 Search / Discovery
- 🌐 Web / Network
- ⭐ Importance / Priority
- 📊 Data / Groups / Strategy
- 🧠 Analysis / Intelligence
- 📝 Format / Presentation
- 🎚️ Scale / Level
- ❓ Questions
- 📐 Format Detection
- 📏 Measurements / Units
- ✅ Quality Control / Validation
- 🔴 Mandatory Requirements
- 💬 Conversation / Context
- 💡 Principles / Ideas
- 🔧 Tools / Strategies / Optimization
- 📌 Scenarios / Cases

### Checkmarks for Rules/Requirements
Use ✅ for affirmative rules and ❌ for prohibitions:
```markdown
1. ✅ DO this
2. ✅ ALWAYS do this
3. ❌ DON'T do this
4. ❌ NEVER do this
```

## Prompt-Schema Mapping

Each prompt must have a corresponding JSON schema that defines the exact structure of the AI's response.

### Table Maker Prompts

| Prompt File | Schema File | Tool Name | Verified |
|------------|-------------|-----------|----------|
| `table_maker/prompts/table_initial.md` | `table_maker/schemas/interview_response.json` | N/A (uses modes) | ✅ |
| `table_maker/prompts/column_definition.md` | `table_maker/schemas/column_definition_response.json` | N/A (direct response) | ✅ |
| `table_maker/prompts/row_discovery.md` | `table_maker/schemas/row_discovery_response.json` | N/A (direct response) | ✅ |
| `table_maker/prompts/qc_review.md` | `table_maker/schemas/qc_review_response.json` | N/A (direct response) | ⚠️ Need to verify |

**Note**: Table Maker context injection was fixed on 2025-10-28. The `build_table_analysis_section()` function now extracts and injects `conversation_context` (research_purpose, user_requirements, tablewide_research, column_details, identification_columns) into the config generation prompt.

### Config Generation Prompts

| Prompt File | Schema File | Tool Name | Verified |
|------------|-------------|-----------|----------|
| `config_generation/prompts/table_maker_config_prompt.md` | `config_generation/schemas/column_config_schema.json` (wrapped) | `generate_config_and_questions` | ⚠️ Fields mentioned, needs explicit JSON structure |
| `config_generation/prompts/create_new_config_prompt.md` | `config_generation/schemas/column_config_schema.json` (wrapped) | `generate_config_and_questions` | ⚠️ Fields mentioned, needs explicit JSON structure |
| `config_generation/prompts/refine_existing_config_prompt.md` | `config_generation/schemas/column_config_schema.json` (wrapped) | `generate_config_and_questions` | ⚠️ Fields mentioned, needs explicit JSON structure |
| `config_generation/prompts/common_config_guidance.md` | N/A (included in others) | N/A | N/A |

**Note**: Config generation prompts mention all required fields in context but lack explicit JSON structure examples showing the complete schema. The AI relies on common_config_guidance.md for field descriptions.

**Note**: Config generation prompts use `column_config_schema.json` wrapped in an AI response schema that includes `updated_config`, `clarifying_questions`, `clarification_urgency`, `technical_ai_summary`, and `ai_summary`. See `config_generation/__init__.py:get_unified_generation_schema()`.

### Validation Prompts

| Prompt File | Schema File | Tool Name | Verified |
|------------|-------------|-----------|----------|
| `shared/prompts/multiplex_validation.md` | `shared/perplexity_schema.py:MULTIPLEX_RESPONSE_SCHEMA` | N/A (direct response) | ✅ |
| `shared/prompts/qc_validation.md` | `shared/perplexity_schema.py:QC_RESPONSE_SCHEMA` | N/A (direct response) | ✅ |

**Note**: Validation prompts were migrated from `prompts.yml` to structured markdown files on 2025-10-28. The prompts preserve all critical nuances from the original YAML including:
- Exact wording of confidence hierarchy rules
- Specific examples and format guidance
- Critical instructions (e.g., "why would you update it with a value that you are less confident in!!?")
- Minor typos/misspellings preserved from working prompts (e.g., "perticularly", "orignal valie")

**Key Files:**
- `src/shared/schema_validator_simplified.py:generate_multiplex_prompt()` - Loads and formats multiplex validation prompt
- `src/shared/qc_module.py:load_prompts_from_file()` - Loads QC validation prompt
- `src/shared/qc_integration.py:QCIntegrationManager` - Manages QC integration with validation lambda

## Schema Verification Checklist

When creating or modifying a prompt, verify:

### 1. **All Required Fields Listed**
- [ ] Prompt explicitly mentions all required fields from schema
- [ ] Prompt explains what each required field should contain
- [ ] Examples show the required fields populated

### 2. **Field Names Match Exactly**
- [ ] Prompt uses exact field names from schema (case-sensitive)
- [ ] No typos or variations in field names
- [ ] Nested object paths correctly described

### 3. **Data Types Correct**
- [ ] String fields described as text
- [ ] Number fields described with ranges/scales
- [ ] Boolean fields described as true/false
- [ ] Array fields described with "list of" or "array of"
- [ ] Object fields show nested structure

### 4. **Constraints Documented**
- [ ] `minItems`/`maxItems` for arrays mentioned in prompt
- [ ] `enum` values listed in prompt
- [ ] Required vs optional fields clearly marked
- [ ] Format requirements (e.g., ISO dates, URLs) specified

### 5. **Examples Match Schema**
- [ ] Example JSON in prompt validates against schema
- [ ] All required fields present in examples
- [ ] Field values match expected types and constraints

## Config Schema Field Coverage

The config generation prompts use `column_config_schema.json` which has these required top-level fields:
- `search_groups` (array) - **✅ Covered** in common_config_guidance.md and all prompts
- `validation_targets` (array) - **✅ Covered** in common_config_guidance.md and all prompts

Optional top-level fields:
- `general_notes` (string) - **✅ Covered** - explicitly instructed in all prompts
- `default_model` (string) - **✅ Covered** in common_config_guidance.md MODEL SELECTION section
- `default_search_context_size` (enum) - **⚠️ Not documented** - may be legacy parameter
- `anthropic_max_web_searches_default` (integer) - **✅ Covered** in common_config_guidance.md WEB SEARCH CONFIGURATION section
- `qc_settings` (object) - **✅ Covered** in common_config_guidance.md QUALITY CONTROL section

### Search Group Schema Fields

Required fields for each search group:
- `group_id` (integer) - **⚠️ Mentioned** but not explicitly in JSON examples
- `group_name` (string) - **⚠️ Mentioned** but not explicitly in JSON examples
- `description` (string) - **✅ Covered** in instructions
- `model` (string) - **✅ Covered** in instructions

Optional fields:
- `search_context` (enum: low/medium/high) - **⚠️ Not documented** - may be legacy parameter
- `anthropic_max_web_searches` (integer 0-10) - **✅ Covered** in common_config_guidance.md WEB SEARCH CONFIGURATION section

### Validation Target Schema Fields

Required fields for each validation target:
- `column` (string) - **✅ Covered** explicitly
- `description` (string) - **✅ Covered** explicitly
- `importance` (enum: ID/CRITICAL/IGNORED) - **✅ Covered** explicitly (Table Maker: no IGNORED)
- `format` (string) - **✅ Covered** explicitly
- `examples` (array of strings) - **✅ Covered** explicitly (Table Maker: must generate)
- `search_group` (integer) - **✅ Covered** explicitly

Optional fields:
- `notes` (string) - **✅ Covered** explicitly (Table Maker: use column definitions exactly)
- `preferred_model` (string) - **⚠️ Not explicitly mentioned** in prompts
- `search_context_size` (enum) - **⚠️ Not explicitly mentioned** in prompts
- `formula_info` (object) - **✅ Covered** via FORMULA_ANALYSIS template variable

### Recommendations

1. **Add explicit JSON structure examples** to config prompts showing:
   ```json
   {
     "general_notes": "...",
     "default_model": "sonar",
     "search_groups": [
       {
         "group_id": 0,
         "group_name": "ID Group",
         "description": "...",
         "model": "sonar"
       }
     ],
     "validation_targets": [
       {
         "column": "Column Name",
         "description": "...",
         "importance": "CRITICAL",
         "format": "String",
         "notes": "...",
         "examples": ["example1", "example2"],
         "search_group": 1
       }
     ]
   }
   ```

2. **Document optional per-column overrides** (`preferred_model`, `search_context_size`) in prompts or accept that these are advanced features not commonly used.

3. **QC settings structure** could be more explicit in prompts with example JSON.

## Common Schema-Prompt Mismatches

### Issue 1: Missing Optional Fields
**Problem**: Schema has optional fields not mentioned in prompt
**Solution**: Add note about optional fields with "Optional: populate if available"

### Issue 2: Different Field Names
**Problem**: Prompt uses "description" but schema expects "desc"
**Solution**: Use exact schema field names in prompt

### Issue 3: Unclear Array Structures
**Problem**: Prompt says "list candidates" but doesn't show array structure
**Solution**: Show example: `"candidates": ["item1", "item2"]`

### Issue 4: Missing Nested Objects
**Problem**: Prompt doesn't explain nested object structure
**Solution**: Show full nested example in prompt

### Issue 5: Wrong Data Types
**Problem**: Prompt suggests string but schema expects number
**Solution**: Align prompt description with schema type

## Template for New Prompts

```markdown
# [Prompt Name]

═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **YOUR CORE TASK**: [Brief description]
2. **CONTEXT**: [Brief description]
3. **REQUIREMENTS**: [Brief description]
4. **OUTPUT FORMAT**: [Brief description]
5. **FINAL REMINDER**: [Brief description]

═══════════════════════════════════════════════════════════════
## 🎯 YOUR CORE TASK
═══════════════════════════════════════════════════════════════

**GOAL:** [One sentence goal]

**DELIVERABLES:**
- [Deliverable 1]
- [Deliverable 2]

**KEY RULES:**
1. ✅ [Rule 1]
2. ✅ [Rule 2]

---

═══════════════════════════════════════════════════════════════
## 📚 CONTEXT SECTION
═══════════════════════════════════════════════════════════════

[Context information here]

---

═══════════════════════════════════════════════════════════════
## ⚠️ REQUIREMENTS
═══════════════════════════════════════════════════════════════

[Requirements here]

---

═══════════════════════════════════════════════════════════════
## 📤 OUTPUT FORMAT
═══════════════════════════════════════════════════════════════

Return JSON in this exact format:

\```json
{
  "required_field_1": "value",
  "required_field_2": 123,
  "optional_field": "value"
}
\```

**Required Fields:**
- `required_field_1` (string): [Description]
- `required_field_2` (number): [Description]

**Optional Fields:**
- `optional_field` (string): [Description]

---

═══════════════════════════════════════════════════════════════
## 🎯 FINAL REMINDER - Your Core Requirements
═══════════════════════════════════════════════════════════════

**GOAL:** [Repeat goal]

**CRITICAL REQUIREMENTS:**
1. ✅ [Requirement 1]
2. ✅ [Requirement 2]

**Return your response as valid JSON matching the format above.**
```

## Maintenance

### When to Update This Guide
- Adding new prompts to the system
- Changing prompt structure standards
- Modifying schemas that affect prompts
- Discovering new schema-prompt mismatch patterns

### Verification Schedule
- **After schema changes**: Immediately verify affected prompts
- **After prompt changes**: Verify against schema before committing
- **Quarterly**: Full audit of all prompt-schema pairs

## Related Documentation
- See `/src/lambdas/interface/actions/table_maker/schemas/` for Table Maker schemas
- See `/src/lambdas/interface/actions/config_generation/schemas/` for Config Generation schemas
- See `/src/lambdas/interface/actions/table_maker/prompts/` for Table Maker prompts
- See `/src/lambdas/interface/actions/config_generation/prompts/` for Config Generation prompts
- See `config_generation/__init__.py:get_unified_generation_schema()` for how config schemas are constructed
