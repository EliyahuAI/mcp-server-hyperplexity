# Table Maker Configuration Creation

═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **YOUR CORE TASK**: Create validation config for AI-generated table with ALL columns validated
2. **TABLE MAKER CONTEXT**: Rich context from conversation, column definitions, tablewide research
3. **CRITICAL REQUIREMENTS**: NO IGNORED COLUMNS, use column definitions exactly, generate examples
4. **GENERAL GUIDANCE**: Capability codes, search context, importance levels, search groups
5. **YOUR TASK**: Step-by-step config creation instructions
6. **FINAL REMINDER**: Core requirements repeated with critical constraints

═══════════════════════════════════════════════════════════════
## 🎯 YOUR CORE TASK
═══════════════════════════════════════════════════════════════

**GOAL:** Create comprehensive validation configuration for an AI-generated research table

**DELIVERABLES:**
- Validation targets for EVERY SINGLE column (no exceptions)
- Search groups organized by information sources
- Capability codes for each validation target to control processing depth
- Clear general notes and column-specific notes incorporating all context
- Clear ai_summary explaining the configuration

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
2. **Validation group with importance: "RESEARCH"** - If the ID column is RESEARCHABLE on the web (e.g., company names, person names, URLs, institutions, products)

**⚠️ CRITICAL RULE**: At least ONE ID column (preferably the FIRST/primary identifier) MUST remain with `importance: "ID"` in Group 0. This is required because:
- Validation operates row-by-row and needs a stable identifier
- Without an ID column, rows cannot be uniquely identified
- This prevents duplication and tracking issues during validation

**Researchable ID columns** CAN be validated, but ONLY if at least one other ID column remains in Group 0:
- They can be verified for accuracy (e.g., "Is this the correct company name?")
- They can be enriched with additional context
- They serve as quality control for row generation

**Examples**:
- ✅ Keep as ID: The FIRST/primary identifier column (e.g., "Company Name" if it's the main row identifier)
- ✅ Validate (if another ID exists): Secondary identifiers like "Website URL", "Researcher Name"
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
- Researchable ID columns (names, companies, URLs) → Validation group with importance: "RESEARCH"
- Research columns → Validation groups with importance: "RESEARCH"
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

{{TABLE_ANALYSIS}}

{{FORMULA_ANALYSIS}}

---

═══════════════════════════════════════════════════════════════
## 📋 YOUR TASK - Step by Step
═══════════════════════════════════════════════════════════════

Using all the context provided above (including the table analysis with column definitions and conversation context):

### Step 1: Understand the Table

1. Read the **research_purpose** and **user_requirements** from conversation context
2. Read the **tablewide_research** to understand the table's goal
3. Review the column definitions to understand what each column represents

### Step 2: Create General Notes

Write comprehensive `general_notes` that:
- Explain the table's research purpose (from conversation context)
- **Embed tablewide_research**: Include concise key points from tablewide_research that apply to MULTIPLE columns or the entire table
- Provide overall validation guidance for this table's domain

**Context Embedding Rules**:
- If tablewide_research or other context applies to **MULTIPLE COLUMNS** or the **ENTIRE TABLE** → Embed in `general_notes`
- If context applies to **ONLY ONE COLUMN** → Embed in that column's `notes` field (see Step 4)
- Focus on non-common knowledge that provides specific context the AI wouldn't know
- Keep it concise and actionable

**Example**: "This table tracks job opportunities combining radiology expertise with AI/ML skills in healthcare settings. Focus on positions that leverage both medical training and technical capabilities. Prefer current job postings (< 3 months old). [Key point from research: Many positions require specific certifications - validate these requirements.]"

### Step 3: Define Search Groups

Create search groups based on where information appears together:

**Group 0 (Required - MUST have at least one ID column)**:
- **⚠️ MANDATORY**: At least one column with `importance: "ID"` must be in Group 0
- The FIRST/primary identifier column should always be in Group 0 as ID (e.g., "Company Name", "Person Name")
- Additional simple ID columns (dates, indices, internal IDs) also go here
- These provide context but don't need validation

**Groups 1+**:
- SECONDARY researchable ID columns (only if a primary ID already exists in Group 0)
- Research columns from column definitions
- Organize by information sources - columns whose data appears together should share a group
- Consider the validation strategies from column definitions when grouping

### Step 4: Create Validation Targets

For EACH column (no exceptions):

**Primary ID Column** (FIRST/main identifier - MUST remain as ID):
- **⚠️ MANDATORY**: The first/primary identifier MUST be in Group 0 with `importance: "ID"`
- This is the main column that uniquely identifies each row (e.g., "Company Name", "Person Name", "Product Name")
- Minimal notes (used for context only)
- **Never convert this to RESEARCH** - validation needs at least one stable ID

**Simple ID Columns** (secondary identifiers, not researchable):
- Place in Group 0
- Set importance: "ID"
- Minimal notes (used for context only)
- Examples: "Index", "Date Created", "Row Number"

**Researchable Secondary ID Columns** (ONLY if a primary ID already exists in Group 0):
- Place in appropriate validation group (1+)
- Set importance: "RESEARCH"
- **Notes field**: Use column `description` and `validation_strategy` EXACTLY (copy verbatim, don't paraphrase)
- **If column-specific context exists**: Append any relevant context from tablewide_research or other sources that applies ONLY to this column
- **Generate realistic examples** since no actual data rows exist yet - use 2-3 plausible examples that match the column description and format
- Examples: "Website URL" (secondary to "Company Name"), "Institution" (secondary to "Researcher Name")

**Research Columns** (is_identification: false):
- Place in appropriate search group (1+)
- Set importance: "RESEARCH"
- **Notes field**: Use column `description` and `validation_strategy` EXACTLY (copy verbatim, don't paraphrase)
- **If column-specific context exists**: Append any relevant context from tablewide_research or other sources that applies ONLY to this column
- **Generate realistic examples** since no actual data rows exist yet - use 2-3 plausible examples that match the column description and format

**Context Embedding in Column Notes**:
- Start with the column's `description` and `validation_strategy` (verbatim)
- Then append: "Additional context: [column-specific information from research]" (only if applicable to just this column)
- Example: "Description: Company headquarters location. Validation: Verify city and country match the company's official HQ. Additional context: For biotech companies in this dataset, many have multiple locations - prioritize the corporate HQ, not R&D facilities."

### Step 5: Assign Capability Codes and QC Settings

Follow the capability code guidance from Common Configuration Guidance above:
- **Capability Codes**: Assign appropriate flags (`Ql`, `P`, `C`, `N`) to each RESEARCH validation target — models and QC are derived automatically from these flags
- **QC**: Enabled automatically when 2+ search groups with validated columns are present — no manual setting needed

### Step 6: Write Summary

**ai_summary**: Write 1-3 sentences describing what will be validated. Keep it light and simple. Example: "Set up thorough validation for all research fields including company names, researcher details, and publication information."

---

═══════════════════════════════════════════════════════════════
## 🎯 FINAL REMINDER - Your Core Requirements
═══════════════════════════════════════════════════════════════

**GOAL:** Create validation config for AI-generated research table using ALL available context

**CRITICAL REQUIREMENTS:**

1. ✅ **NO IGNORED COLUMNS**: Every single column must have a validation target
   - ID columns → Group 0 with importance: "ID"
   - Research columns → Groups 1+ with importance: "RESEARCH"
   - NEVER use importance: "IGNORED" for any column

2. ✅ **USE ALL CONTEXT**: You have rich information available
   - Conversation context → Inform general_notes and understand purpose
   - Column definitions → Use descriptions and validation strategies EXACTLY in notes
   - **Embed tablewide_research/context appropriately**:
     - Multi-column or table-wide context → `general_notes`
     - Single-column specific context → That column's `notes` field

3. ✅ **AT LEAST ONE ID COLUMN REQUIRED**: The FIRST/primary ID column MUST remain `importance: "ID"` in Group 0
   - This is MANDATORY - validation needs a stable row identifier
   - Secondary researchable IDs (names, URLs, institutions) → Can be validated in Groups 1+
   - Simple IDs (dates, indices, internal IDs) → Keep as ID in Group 0

4. ✅ **USE COLUMN DEFINITIONS EXACTLY**:
   - Copy description and validation_strategy verbatim into column `notes`
   - Then append any column-specific context if applicable

5. ✅ **GENERATE EXAMPLES**: No actual data rows exist yet - create 2-3 realistic examples for each column

6. ✅ **MINIMUM 2 SEARCH GROUPS**: Group 0 (ID) + at least one validation group

7. ✅ **EVERY COLUMN ASSIGNED**: Every column must be in a search group

8. ✅ **RETURN CLEAR SUMMARY**: Must include clear ai_summary explaining your configuration decisions

**Return your configuration using the generate_config_and_questions tool with complete updated_config.**
