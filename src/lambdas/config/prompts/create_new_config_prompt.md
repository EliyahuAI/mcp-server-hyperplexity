# New Configuration Creation Prompt

═══════════════════════════════════════════════════════════════
## 📋 PROMPT MAP - What You'll Find Below
═══════════════════════════════════════════════════════════════

1. **MISSION**: Create comprehensive new configuration from scratch
2. **CRITICAL REQUIREMENTS**: Never modify column names, minimum 2 search groups, return both summaries
3. **YOUR TASK**: What to create (search groups, validation targets, summaries)
4. **COMMON GUIDANCE**: Model selection, search context, importance levels, search groups (included)
5. **TABLE ANALYSIS**: Column details and sample data
6. **FORMULA ANALYSIS**: Calculated columns and dependencies
7. **USER FEEDBACK**: Any specific instructions provided
8. **CLARIFYING QUESTIONS**: Configuration choices requiring confirmation

═══════════════════════════════════════════════════════════════
## 🎯 MISSION
═══════════════════════════════════════════════════════════════

**Create comprehensive new configuration for AI validation from scratch.**

═══════════════════════════════════════════════════════════════
## ⚠️ CRITICAL REQUIREMENTS
═══════════════════════════════════════════════════════════════
1. NEVER modify column names from table analysis
2. Minimum 2 search groups (Group 0 + validation groups)
3. Every column MUST be assigned to a search group
5. Return both technical_ai_summary AND ai_summary

═══════════════════════════════════════════════════════════════
## 📋 YOUR TASK
═══════════════════════════════════════════════════════════════

You are analyzing a table for the **first time** and need to create an optimal configuration from scratch.
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

{{USER_FEEDBACK_SECTION}}

═══════════════════════════════════════════════════════════════
## ❓ CLARIFYING QUESTIONS - CONFIGURATION CHOICES
═══════════════════════════════════════════════════════════════
Generate questions that explain what you configured and suggest specific improvements:

**Good**: "I configured searches for current revenue data - would you prefer quarterly breakdowns instead?"
**Bad**: "Should I validate revenue or skip it?"

Reference your actual configuration decisions and offer concrete alternatives that might work better. These must no refer to any technical details of the configuration. They should focus on the business needs, cost/accuracy tradeoffs for context and performance models, and critical assumptions.

═══════════════════════════════════════════════════════════════
## 📤 RESPONSE REQUIREMENTS
═══════════════════════════════════════════════════════════════
You MUST use the generate_config_and_questions tool with:
- Complete updated_config with all required fields
- Specific clarifying_questions (2-4 questions)
- **technical_ai_summary** field with detailed technical reasoning explaining your configuration decisions
- **ai_summary** field with simple business-friendly overview

Focus on creating a solid foundation that can be iteratively improved through user feedback.