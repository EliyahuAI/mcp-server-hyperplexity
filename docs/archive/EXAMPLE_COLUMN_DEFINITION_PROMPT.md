# Example Column Definition Prompt

This is what actually gets sent to Claude Haiku for column definition.

---

## Example Prompt (Real, with variables filled)

```
You are defining precise column specifications and search strategy for a research table generation system.

## Context
The user has completed a conversation about their research needs and approved a table concept. Your task is to create a detailed column specification and search strategy for finding the right entities.

## Conversation Context
Turn 1 (user): I want to create a table tracking AI companies that are actively hiring.

Columns needed:
- Company Name
- Website
- Is hiring for AI roles? (yes/no)
- Team size (approximate)
- Recent funding (last round)

Find about 10 companies across different AI sectors like research, healthcare, and enterprise.
Make sure to include both established companies and startups.

## User's Approved Requirements
User wants to track AI companies that are actively hiring.

Requested columns:
- Company Name
- Website
- Is hiring for AI roles?
- Team size
- Recent funding

Target: ~10 companies across research, healthcare, enterprise sectors.


## IMPORTANT: Understanding Your Task

You are designing columns for a table that will track REAL ENTITIES (companies, people, papers, etc.), NOT describing table structure itself.

### Example Task Clarification

**If user says:** "Create a table tracking AI companies"
**You should create columns FOR the companies:**
- ✅ Company Name (ID column)
- ✅ Website (ID column)
- ✅ Is Hiring for AI? (research column)
- ✅ Team Size (research column)

**You should NOT create meta-columns about tables:**
- ❌ Table Name
- ❌ Column Name
- ❌ Description
- ❌ Format

**If user says:** "Track research papers on climate change"
**You should create columns FOR the papers:**
- ✅ Paper Title (ID)
- ✅ Authors (ID)
- ✅ Citation Count (research)
- ✅ Publication Year (research)

**NOT meta-columns like:** Table Name, Column Name, etc.

### Complete Example for "AI Companies"

If the user wants to track AI companies, return this structure:

```json
{
  "columns": [
    {
      "name": "Company Name",
      "description": "Name of the AI company",
      "format": "String",
      "importance": "ID",
      "is_identification": true
    },
    {
      "name": "Website",
      "description": "Company website URL",
      "format": "URL",
      "importance": "ID",
      "is_identification": true
    },
    {
      "name": "Is Hiring for AI?",
      "description": "Whether actively hiring for AI/ML roles",
      "format": "Boolean",
      "importance": "CRITICAL",
      "is_identification": false,
      "validation_strategy": "Check careers page for AI/ML job postings"
    }
  ],
  "search_strategy": {
    "description": "Find AI companies actively hiring",
    "subdomains": [
      {
        "name": "AI Research Companies",
        "focus": "Research-focused AI companies",
        "search_queries": ["top AI research companies 2024"],
        "target_rows": 10
      }
    ]
  },
  "table_name": "AI Companies Hiring Status"
}
```

---

## Your Task

### 1. Define Precise Column Specifications

For each column (both ID columns and research columns):
- **Name**: Clear, concise column name
- **Description**: Detailed explanation of what this column contains
- **Format**: Data type (String, Number, Boolean, URL, Date, etc.)
- **Importance**: "ID" for identification columns, "CRITICAL" for research columns
- **Is Identification**: true for ID columns, false for research columns
- **Validation Strategy**: HOW to validate/find this data (REQUIRED for research columns)

[... rest of template continues with subdomain specification, scoring rubric, etc. ...]
```

---

## What Claude Haiku SHOULD Return

```json
{
  "columns": [
    {
      "name": "Company Name",
      "description": "Name of the AI company",
      "format": "String",
      "importance": "ID",
      "is_identification": true
    },
    {
      "name": "Website",
      "description": "Company website URL",
      "format": "URL",
      "importance": "ID",
      "is_identification": true
    },
    {
      "name": "Is Hiring for AI?",
      "description": "Whether the company is actively hiring for AI/ML roles",
      "format": "Boolean",
      "importance": "CRITICAL",
      "is_identification": false,
      "validation_strategy": "Check company careers page for job postings containing 'AI', 'ML', or 'Machine Learning' keywords"
    },
    {
      "name": "Team Size",
      "description": "Approximate number of employees",
      "format": "Number",
      "importance": "CRITICAL",
      "is_identification": false,
      "validation_strategy": "Check LinkedIn company page for employee count or About Us section"
    },
    {
      "name": "Recent Funding",
      "description": "Most recent funding round information",
      "format": "String",
      "importance": "CRITICAL",
      "is_identification": false,
      "validation_strategy": "Search Crunchbase, press releases, or tech news for recent funding announcements"
    }
  ],
  "search_strategy": {
    "description": "Find AI companies actively hiring for AI/ML positions across research, healthcare, and enterprise sectors",
    "subdomains": [
      {
        "name": "AI Research Companies",
        "focus": "Research-focused AI companies and labs",
        "search_queries": [
          "top AI research companies hiring 2024",
          "AI research labs with job openings",
          "AI companies publishing research"
        ],
        "target_rows": 10
      },
      {
        "name": "Healthcare AI Companies",
        "focus": "AI companies in healthcare and medical sectors",
        "search_queries": [
          "healthcare AI companies hiring",
          "medical AI startups with job postings",
          "AI health tech companies list"
        ],
        "target_rows": 10
      },
      {
        "name": "Enterprise AI Companies",
        "focus": "B2B AI solution providers",
        "search_queries": [
          "enterprise AI companies hiring",
          "B2B AI software companies list",
          "AI automation companies with jobs"
        ],
        "target_rows": 10
      }
    ]
  },
  "table_name": "AI Companies Hiring Status",
  "tablewide_research": "Focus on companies with active AI/ML job postings in 2024-2025"
}
```

---

## What It's ACTUALLY Returning (Wrong)

```json
{
  "columns": [
    {
      "name": "Table Purpose",
      "description": "The primary research objective and what entities this table will track",
      "format": "String",
      "importance": "ID",
      "is_identification": true
    },
    {
      "name": "Entity Type",
      "description": "The category of entities being tracked",
      "format": "String",
      "importance": "ID",
      "is_identification": true
    },
    {
      "name": "Primary Identifier Column",
      "description": "The main column used to uniquely identify each entity",
      "format": "String",
      "importance": "CRITICAL",
      "is_identification": false
    }
  ]
}
```

**It's creating columns ABOUT tables, not columns FOR the entities!**

---

## The Problem

Despite the clear examples and instructions, Claude is interpreting the task as:
- "Define what columns a research table should have"

Instead of:
- "Define columns to track specific AI companies"

**Possible cause:** The framing "research table generation system" in line 1 might be confusing it.

**Key question:** What are the actual values of `{{CONVERSATION_CONTEXT}}` and `{{USER_REQUIREMENTS}}`? These variables might not contain enough specificity.
