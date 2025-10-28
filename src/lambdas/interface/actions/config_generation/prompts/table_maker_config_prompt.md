# Table Maker Configuration Creation

═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **YOUR CORE TASK**: Create validation config for AI-generated table with ALL columns validated
2. **TABLE MAKER CONTEXT**: Rich context from conversation, column definitions, and search strategy
3. **CRITICAL REQUIREMENTS**: NO IGNORED COLUMNS, use all available context
4. **GENERAL GUIDANCE**: Model selection, search context, importance levels, search groups
5. **YOUR TASK**: Step-by-step config creation instructions
6. **TABLE ANALYSIS**: Column details and sample data
7. **FINAL REMINDER**: Core requirements repeated with critical constraints

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
3. ✅ Use column definitions (descriptions, validation strategies) from column definition phase
4. ✅ Use search strategy (requirements, subdomains, discovered lists) to inform validation approach
5. ✅ Use tablewide_research to provide context in general_notes
6. ✅ Create search groups based on where information appears together
7. ✅ All columns defined as ID columns during table generation must be in Group 0

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

**INSTRUCTION**: Use the column `description` and `validation_strategy` to write detailed `notes` for each validation target. Don't just copy them - synthesize them into clear validation guidance.

### 3. Search Strategy

The Table Maker defined a search strategy including:

- **Requirements**: Hard and soft requirements that define valid rows (from search_strategy.requirements)
- **Subdomains**: Focus areas that guided row discovery (from search_strategy.subdomains)
- **Discovered Lists**: Authoritative sources found (URLs and example candidates from each subdomain)
- **Requirements Notes**: Overall guidance about what makes a good row

**INSTRUCTION**: Use requirements and discovered lists to inform your validation approach. If the search strategy found specific authoritative sources (e.g., "NIH RePORTER grants"), mention these in notes as preferred sources.

### 4. Identification Columns

Columns marked with `is_identification: true` in the column definitions are ID columns that:
- Define what each row represents
- Were used to discover/identify entities during row generation
- Should ALL be placed in Group 0 (context group, not validated)

**INSTRUCTION**: Group 0 must contain ALL ID columns. These provide context for validating research columns but are not themselves validated.

---

═══════════════════════════════════════════════════════════════
## ⚠️ CRITICAL REQUIREMENTS - Table Maker Specific
═══════════════════════════════════════════════════════════════

### 1. NO IGNORED COLUMNS Rule

**CRITICAL**: In Table Maker, EVERY column must be validated. You CANNOT mark any column as IGNORED importance.

**Why**: Unlike user-uploaded tables that may contain calculated columns or indices, Table Maker generates research tables where every column represents information that should be validated for accuracy and completeness.

**What this means**:
- Every column gets a validation target entry
- ID columns (is_identification: true) go in Group 0 with importance: "ID"
- Research columns go in Groups 1+ with importance: "CRITICAL"
- NO column should have importance: "IGNORED"

### 2. Use ALL Available Context

You have much more context than typical config generation:

**From Conversation**:
- Why the user wanted this table
- What they're researching
- Any specific requirements they mentioned

**From Column Definitions**:
- Detailed column descriptions
- Specific validation strategies
- Expected formats and examples

**From Search Strategy**:
- Requirements (hard/soft) that define valid rows
- Discovered authoritative sources
- Example candidates from those sources

**INSTRUCTION**: Synthesize ALL this information into your configuration. Don't ignore any of it.

### 3. Embed Tablewide Research

The `tablewide_research` field contains concise context about this table's purpose (e.g., "Target roles combining radiology expertise with AI/ML skills in healthcare settings").

**INSTRUCTION**: Embed key points from tablewide_research into your `general_notes`. This provides essential context for all validation queries.

### 4. Respect Column Definition Decisions

The column definition phase already decided:
- Which columns are ID fields vs research fields
- Column descriptions and validation strategies
- Format specifications

**INSTRUCTION**: Honor these decisions. Place all ID columns in Group 0, use their descriptions/strategies to inform validation notes.

---

{{INCLUDE:common_config_guidance.md}}

{{TABLE_ANALYSIS}}

{{FORMULA_ANALYSIS}}

---

═══════════════════════════════════════════════════════════════
## 📋 YOUR TASK - Step by Step
═══════════════════════════════════════════════════════════════

Using all the context provided above:

### Step 1: Understand the Table

1. Read the **research_purpose** and **user_requirements** from conversation context
2. Read the **tablewide_research** to understand the table's goal
3. Review the **requirements** from search_strategy to understand what makes valid rows
4. Note any **discovered lists** or authoritative sources found

### Step 2: Create General Notes

Write comprehensive `general_notes` that:
- Explain the table's research purpose (from conversation context)
- Include key points from tablewide_research
- Reference requirements from search strategy if relevant
- Provide overall validation guidance

**Example**: "This table tracks job opportunities combining radiology expertise with AI/ML skills in healthcare settings. Focus on positions that leverage both medical training and technical capabilities. Prefer current job postings (< 3 months old)."

### Step 3: Define Search Groups

Create search groups based on where information appears together:

**Group 0 (Required)**:
- ALL columns with `is_identification: true` from column definitions
- These define what each row represents
- Not validated, just provide context

**Groups 1+**:
- Organize research columns by information sources
- Columns whose data appears together in typical sources should share a group
- Consider the validation strategies from column definitions when grouping

### Step 4: Create Validation Targets

For EACH column (no exceptions):

**ID Columns** (is_identification: true):
- Place in Group 0
- Set importance: "ID"
- Minimal notes (used for context only)

**Research Columns** (is_identification: false):
- Place in appropriate search group (1+)
- Set importance: "CRITICAL"
- Write detailed notes synthesizing:
  - Column description from column definition
  - Validation strategy from column definition
  - Relevant requirements or discovered sources from search strategy
  - Format specifications and examples

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
- How you used the table maker context (conversation, column defs, search strategy)
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
   - Column definitions → Use descriptions and validation strategies in notes
   - Search strategy → Reference requirements and discovered lists
   - Tablewide research → Embed in general_notes

3. ✅ **ALL ID COLUMNS IN GROUP 0**: Columns with `is_identification: true` ALL go in Group 0

4. ✅ **RESPECT COLUMN DEFINITIONS**: Honor the decisions made during column definition phase

5. ✅ **MINIMUM 2 SEARCH GROUPS**: Group 0 (ID) + at least one validation group

6. ✅ **EVERY COLUMN ASSIGNED**: Every column must be in a search group

7. ✅ **RETURN BOTH SUMMARIES**: Must include both technical_ai_summary and ai_summary

**Return your configuration using the generate_config_and_questions tool with complete updated_config.**
