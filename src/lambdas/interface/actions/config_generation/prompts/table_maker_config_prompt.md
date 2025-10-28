# Table Maker Configuration Creation

═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **YOUR CORE TASK**: Create validation config for AI-generated table with ALL columns validated
2. **TABLE MAKER CONTEXT**: Rich context from conversation, column definitions, tablewide research
3. **CRITICAL REQUIREMENTS**: NO IGNORED COLUMNS, use column definitions exactly, generate examples
4. **GENERAL GUIDANCE**: Model selection, search context, importance levels, search groups
5. **YOUR TASK**: Step-by-step config creation instructions
6. **FINAL REMINDER**: Core requirements repeated with critical constraints

═══════════════════════════════════════════════════════════════
## 🎯 YOUR CORE TASK
═══════════════════════════════════════════════════════════════

**GOAL:** Create comprehensive validation configuration for an AI-generated research table

**DELIVERABLES:**
- Validation targets for EVERY SINGLE column (no exceptions)
- Search groups organized by information sources
- Appropriate models and context sizes for each group
- Clear general notes and column-specific notes incorporating all context
- Both technical_ai_summary and ai_summary

**KEY RULES:**
1. ✅ **CRITICAL**: EVERY column must have a validation target - NO columns can be marked as IGNORED
2. ✅ Use conversation context to understand table purpose and user requirements
3. ✅ Use column definitions (descriptions, validation strategies) EXACTLY in notes
4. ✅ Use tablewide_research to provide context in general_notes
5. ✅ Create search groups based on where information appears together
6. ✅ Researchable ID columns (names, companies, URLs) should be validated

---

═══════════════════════════════════════════════════════════════
## 📚 TABLE MAKER CONTEXT - Use This Rich Information
═══════════════════════════════════════════════════════════════

You are creating a validation config for a table that was generated through an AI-assisted process. You have access to rich contextual information that MUST inform your configuration:

### 1. Conversation Context

The user had a conversation with the Table Maker AI that resulted in this table structure. Key information available:

- **Research Purpose**: Why the user wanted this table (from conversation_context.research_purpose)
- **User Requirements**: What the user asked for (from conversation_context.user_requirements)
- **Table Purpose**: The overall goal of this research table (from tablewide_research)

**INSTRUCTION**: Use this context to write informed `general_notes` that guide all validation. The general notes should reflect the table's research purpose and any domain-specific context.

### 2. Column Definitions

Each column was carefully defined during the column definition phase with:

- **Description**: Detailed explanation of what the column contains
- **Validation Strategy**: Specific instructions for how to validate/research this column
- **Format**: Expected data format
- **Importance**: Whether it's an ID column or research column

**INSTRUCTION**: Use the column `description` and `validation_strategy` EXACTLY in the `notes` for each validation target. These were carefully crafted during column definition and should be used verbatim as validation guidance.

### 3. Identification Columns

Columns marked with `is_identification: true` in the column definitions are ID columns that:
- Define what each row represents
- Were used to discover/identify entities during row generation
- Typically go in Group 0 (context group)

**INSTRUCTION**: ID columns can be handled in two ways:
1. **Group 0 with importance: "ID"** - If the ID column is simple and doesn't need web research (e.g., dates, indices, simple labels)
2. **Validation group with importance: "CRITICAL"** - If the ID column is RESEARCHABLE on the web (e.g., company names, person names, URLs, institutions, products)

**Researchable ID columns** should be validated because:
- They can be verified for accuracy (e.g., "Is this the correct company name?")
- They can be enriched with additional context
- They serve as quality control for row generation

**Examples**:
- ✅ Validate: "Company Name", "Researcher Name", "Institution", "Job Title", "Product Name", "URL"
- ❌ Don't validate: "Index", "Row Number", "Date Created", "Internal ID"

---

═══════════════════════════════════════════════════════════════
## ⚠️ CRITICAL REQUIREMENTS - Table Maker Specific
═══════════════════════════════════════════════════════════════

### 1. NO IGNORED COLUMNS Rule

**CRITICAL**: In Table Maker, EVERY column must be validated. You CANNOT mark any column as IGNORED importance.

**Why**: Unlike user-uploaded tables that may contain calculated columns or indices, Table Maker generates research tables where every column represents information that should be validated for accuracy and completeness.

**What this means**:
- Every column gets a validation target entry
- Simple ID columns (dates, indices) → Group 0 with importance: "ID"
- Researchable ID columns (names, companies, URLs) → Validation group with importance: "CRITICAL"
- Research columns → Validation groups with importance: "CRITICAL"
- NO column should have importance: "IGNORED"

### 2. Use ALL Available Context

You have rich contextual information that must inform your configuration:

**From Conversation**:
- Why the user wanted this table
- What they're researching
- Any specific requirements mentioned

**From Column Definitions**:
- Column descriptions (use EXACTLY in notes)
- Validation strategies (use EXACTLY in notes)
- Format specifications and examples

**From Tablewide Research**:
- Concise research summary about the table's purpose
- Domain-specific context to embed in general_notes

**INSTRUCTION**: Use column `description` and `validation_strategy` verbatim in validation target `notes`. Don't paraphrase - copy exactly.

---

{{INCLUDE:common_config_guidance.md}}

---

═══════════════════════════════════════════════════════════════
## 📋 YOUR TASK - Step by Step
═══════════════════════════════════════════════════════════════

Using all the context provided above:

### Step 1: Understand the Table

1. Read the **research_purpose** and **user_requirements** from conversation context
2. Read the **tablewide_research** to understand the table's goal
3. Review the column definitions to understand what each column represents

### Step 2: Create General Notes

Write comprehensive `general_notes` that:
- Explain the table's research purpose (from conversation context)
- Include key points from tablewide_research
- Provide overall validation guidance for this table's domain

**Example**: "This table tracks job opportunities combining radiology expertise with AI/ML skills in healthcare settings. Focus on positions that leverage both medical training and technical capabilities. Prefer current job postings (< 3 months old)."

### Step 3: Define Search Groups

Create search groups based on where information appears together:

**Group 0 (Required)**:
- Simple ID columns that don't need web research (dates, indices, internal IDs)
- These provide context but don't need validation

**Groups 1+**:
- Researchable ID columns (company names, person names, URLs, institutions)
- Research columns from column definitions
- Organize by information sources - columns whose data appears together should share a group
- Consider the validation strategies from column definitions when grouping

### Step 4: Create Validation Targets

For EACH column (no exceptions):

**Simple ID Columns** (is_identification: true, not researchable):
- Place in Group 0
- Set importance: "ID"
- Minimal notes (used for context only)
- Examples: "Index", "Date Created", "Row Number"

**Researchable ID Columns** (is_identification: true, CAN be researched on web):
- Place in appropriate validation group (1+)
- Set importance: "CRITICAL"
- Use column `description` and `validation_strategy` EXACTLY in notes
- **Generate realistic examples** since no actual data rows exist yet - use 2-3 plausible examples that match the column description and format
- Examples of researchable ID types: "Company Name", "Researcher Name", "Institution", "Job Title", "URL"

**Research Columns** (is_identification: false):
- Place in appropriate search group (1+)
- Set importance: "CRITICAL"
- Use column `description` and `validation_strategy` EXACTLY in notes
- **Generate realistic examples** since no actual data rows exist yet - use 2-3 plausible examples that match the column description and format

### Step 5: Select Models and Context

- Use `sonar` (default) for straightforward fact-checking
- Use `sonar-pro` when synthesis of sources needed
- Use `claude-sonnet-4-5` for complex reasoning or when web search + reasoning needed
- Set appropriate `search_context_size` (high by default, lower for simple lookups)
- Set `anthropic_max_web_searches` (0-10) for Claude models based on complexity

### Step 6: Enable QC

- Set `enable_qc: true` to enable quality control review
- QC helps catch validation errors and improve accuracy
- Default QC settings are usually appropriate

### Step 7: Write Summaries

**technical_ai_summary**: Explain your configuration decisions with technical details:
- How you organized search groups and why
- Which models you chose and why
- How you used the table maker context (conversation, column definitions, tablewide research)
- Which ID columns you upgraded to CRITICAL for validation and why
- Any assumptions you made

**ai_summary**: Simple business-friendly overview:
- What information will be validated
- How the validation will work (in plain language)
- Avoid technical terms like "search groups" or "context size"

---

═══════════════════════════════════════════════════════════════
## 🎯 FINAL REMINDER - Your Core Requirements
═══════════════════════════════════════════════════════════════

**GOAL:** Create validation config for AI-generated research table using ALL available context

**CRITICAL REQUIREMENTS:**

1. ✅ **NO IGNORED COLUMNS**: Every single column must have a validation target
   - ID columns → Group 0 with importance: "ID"
   - Research columns → Groups 1+ with importance: "CRITICAL"
   - NEVER use importance: "IGNORED" for any column

2. ✅ **USE ALL CONTEXT**: You have rich information available
   - Conversation context → Inform general_notes and understand purpose
   - Column definitions → Use descriptions and validation strategies EXACTLY in notes
   - Tablewide research → Embed in general_notes

3. ✅ **RESEARCHABLE ID COLUMNS**: Upgrade to CRITICAL if they can be verified on web
   - Names, companies, URLs, institutions → Validate these
   - Dates, indices, internal IDs → Keep as ID in Group 0

4. ✅ **USE COLUMN DEFINITIONS EXACTLY**: Copy description and validation_strategy verbatim into notes

5. ✅ **GENERATE EXAMPLES**: No actual data rows exist yet - create 2-3 realistic examples for each column

6. ✅ **MINIMUM 2 SEARCH GROUPS**: Group 0 (ID) + at least one validation group

7. ✅ **EVERY COLUMN ASSIGNED**: Every column must be in a search group

8. ✅ **RETURN BOTH SUMMARIES**: Must include both technical_ai_summary and ai_summary

**Return your configuration using the generate_config_and_questions tool with complete updated_config.**
