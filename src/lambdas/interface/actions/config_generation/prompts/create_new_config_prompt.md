# New Configuration Creation Prompt

**MISSION**: Create comprehensive new configuration for AI validation from scratch.

## CRITICAL REQUIREMENTS
1. NEVER modify column names from table analysis
2. Minimum 2 search groups (Group 0 + validation groups)
3. Every column MUST be assigned to a search group
4. Return clear ai_summary explaining your configuration

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

3. **AI Summary** (REQUIRED - goes in ai_summary field)
   - 1-3 sentences describing what will be validated
   - Keep it simple and light
   - Example: "Configured thorough validation for company data and financial information with quality control enabled."
   - No technical details

{{INCLUDE:common_config_guidance.md}}

{{TABLE_ANALYSIS}}

{{FORMULA_ANALYSIS}}

{{USER_FEEDBACK_SECTION}}

## CLARIFYING QUESTIONS - CONFIGURATION CHOICES
Generate questions that explain what you configured and suggest specific improvements:

**Good**: "I configured searches for current revenue data - would you prefer quarterly breakdowns instead?"
**Bad**: "Should I validate revenue or skip it?"

Reference your actual configuration decisions and offer concrete alternatives that might work better. These must no refer to any technical details of the configuration. They should focus on the business needs, cost/accuracy tradeoffs for context and performance models, and critical assumptions.

## Response Requirements
You MUST use the generate_config_and_questions tool with:
- Complete updated_config with all required fields
- Specific clarifying_questions (2-4 questions)
- **ai_summary** field with clear explanation of your configuration decisions

Focus on creating a solid foundation that can be iteratively improved through user feedback.