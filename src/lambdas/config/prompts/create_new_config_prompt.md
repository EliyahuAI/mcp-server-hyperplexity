# New Configuration Creation Prompt

**MISSION**: Create comprehensive new configuration for AI validation from scratch.

## CRITICAL REQUIREMENTS
1. NEVER modify column names from table analysis
2. Minimum 2 search groups (Group 0 + validation groups)
3. Every column MUST be assigned to a search group
5. Return both technical_ai_summary AND ai_summary

## Context
You are analyzing a table for the **first time** and need to create an optimal configuration from scratch.

## Your Task
Create a comprehensive configuration that includes:

1. **Search Groups** (MANDATORY - minimum 1 group)
   - Group 0: ID/identifier fields (used for context, not validated)
   - Group 1+: Columns that appear together in typical sources
   - Every column must be assigned to a search group

2. **Validation Targets**
   - All important columns with proper importance levels
   - Realistic examples from the actual data (INCLUDING UNITS when applicable)
   - If guidance no longer matches the provided examples, update the examples to a coherent set that matches the guidance
   - Appropriate format specifications with unit requirements for measurements

3. **Technical AI Summary** (REQUIRED - goes in technical_ai_summary field)
   - Overview of the search group structure you created with technical details
   - Which columns you identified as critical and why, including search groups and context decisions
   - Assessment of clarification urgency (use 0.4-0.8 range for new configs per anchored scale)
   - Specific areas where clarification would improve the configuration
   - Technical assumptions made about models, context sizes, and groupings

4. **Simple AI Summary** (REQUIRED - goes in ai_summary field)
   - Simple business-friendly overview of the configuration
   - Avoid technical terms like "search groups" or "context size"
   - Focus on what information will be validated and how
   - Examples: "Set up focused searches for company data" instead of "Created search groups"

{{INCLUDE:common_config_guidance.md}}

{{TABLE_ANALYSIS}}

{{FORMULA_ANALYSIS}}

## CLARIFYING QUESTIONS - CONFIGURATION CHOICES
Generate questions that explain what you configured and suggest specific improvements:

**Good**: "I configured searches for current revenue data - would you prefer quarterly breakdowns instead?"
**Bad**: "Should I validate revenue or skip it?"

Reference your actual configuration decisions and offer concrete alternatives that might work better. These must no refer to any technical details of the configuration. They should focus on the business needs, cost/accuracy tradeoffs for context and performance models, and critical assumptions.

## Response Requirements
You MUST use the generate_config_and_questions tool with:
- Complete updated_config with all required fields
- Specific clarifying_questions (2-4 questions)
- **technical_ai_summary** field with detailed technical reasoning explaining your configuration decisions
- **ai_summary** field with simple business-friendly overview

Focus on creating a solid foundation that can be iteratively improved through user feedback.