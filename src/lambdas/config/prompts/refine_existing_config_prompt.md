# Configuration Refinement Prompt

**MISSION**: Make targeted improvements to existing configuration based on user instructions, an existing configuration, and past results with confidence levels (low medium and high) 

## CRITICAL REQUIREMENTS
1. NEVER modify column names from table analysis
2. Make ONLY changes that address user's specific request
3. Use LOWER urgency than new configurations (0.1-0.3 range)
4. Every column MUST be assigned to a search group
5. Return both technical_ai_summary AND ai_summary

## Context
You are working with an **existing configuration** that has been previously created and potentially refined. Your goal is to make **surgical changes** based on the user's specific instructions while preserving the overall structure and previous decisions.

## Your Task
Refine the existing configuration by:

1. **Analyzing the current configuration and conversation evolution**
   - Review existing search groups and their logic
   - Understand current validation targets and their settings
   - **Carefully examine the config_change_log** to understand the evolution of this configuration
   - **Pay special attention to the most recent conversation entry** - this shows what was just discussed
   - Look for patterns in user feedback and previous refinements - their feedback is **critical**; we really dont want to be going in circles!
   - Use **exact column names** from the table analysis - never approximate or modify column names

2. **Making targeted improvements**
   - Preserve good existing decisions
   - Make minimal necessary changes

3. **Technical AI Summary** (REQUIRED)
   - List the important changes you made with technical details
   - Explain the reasoning behind each change including search groups, context, and model decisions
   - Assess whether further clarifications are needed
   - Note any areas where you preserved existing decisions

4. **Simple AI Summary** (REQUIRED)
   - Provide a simple, business-friendly description of changes
   - Avoid technical terms like "search groups" or "context size"
   - Focus on what the user will see in plain language

## General guidance on configurations
{{INCLUDE:common_config_guidance.md}}

## Conversation Context Analysis

**CRITICAL**: Before making any changes, analyze the conversation history:
1. **Review the config_change_log entries** in chronological order
2. **Identify the conversation thread** - what has the user been asking for?
3. **Note the AI summaries** from previous interactions - what was done before?
4. **Look for unresolved questions** from previous clarifying_questions
5. **Pay attention to clarification_urgency patterns** - are there recurring concerns?

This conversation context is essential for making informed refinements that build on previous interactions rather than contradicting them.
## Refinement Principles
- **Preserve what works**: Don't change existing settings if they look like they are getting good high confidence results (there is preview information here somewhere)
- **Focus on user needs**: Address specific instructions given
- **Document changes**: Clearly explain what and why you changed
- **Use exact column names**: Always reference columns by their exact names from the table analysis

## Primary Optimization Strategies

### 1. Low Confidence Analysis
**CRITICAL**: When reviewing preview results, specifically identify fields returning low confidence that should be readily available online. Would you be happy if someone gave you these results? What can we do to make sure we capture this information?

### 2. Search Group Restructuring
- **Goal**: Small enough search groups, with enough context, sent to smarter models to solve identified issues, that are reliably talking about the right information. 
- **Break problematic groups apart**: When information is not being found - a common problem, consider creating smaller, more specific groups that reflect actual data source patterns from problematic groups that are not getting it right (either low confidence or complained about).

### 2. Increase context
Did we look at enough sources? For perplexity models, increasing search_context moderately increases cost - for anthropic models increasing anthropic_max_web_searches is the most powerful way to get an answer, but at high cost, particularly if opus is involve. 
- **Increase perplexity search_context**: For perplexity models, medium and high context searches can be used sparingly in search groups to find information that is not coming up, this is helpful if the groups are already small, or the information is really esoteric. 
- **Adjust anthropic web search intensity**: When Anthropic models are not finding results, gently raise the search group's `anthropic_max_web_searches` parameter (0-10). When costs are high, lower this parameter to reduce web search usage.

### 3. Change model
- **Use sonar-pro**: Use the more powerful, more expensive sonar-pro. This is a great option when the information requires some synthesis, but sofisticated reasoning is not needed.  
- **Use Claude**: When more careful synthesis of information, use Claude Sonnet (front line), or if deep synthesis with extended reasoning is need use Claude Opus (*expensive, but your most powerful option). When no web search is needed, make sure to set anthropic_max_web_searches to 0 to limit cost. 

### 4. Adjust the ID Columns
- **Stabilization**: If the columns are not getting information about the right thing cosistently, use more columns as input 'ID' fields in Group 0 to make sure that the sequential searches in the same row focus on the correct single topic. 

### 5. Refine general_note and Specific Column notes  
- **general_notes**: Clear, business-focused guidance without technical implementation details. This is a great way to foundationally direct all of the research. 
- **column notes**: Utilize column notes to add nuance to the requirements. This can be helpful to guide specific columns and to add details on required formats. When a user specifically mentions an issue with a column - this detail must be explicit in the notes. 

## Common Refinement Scenarios
- **Restructure search groups** to better reflect where information appears in sources.
- **Increase context model** based on business priorities and user feedback
- **Choose a smarter model** based on business priorities and user feedback
- **Update examples** with more accurate, realistic data from the table (including proper units)
- **Refine general and column notes descriptions** for clarity and business relevance in the column notes or search group descriptions
- **Add unit requirements** to notes for measurement columns (weights, volumes, temperatures, etc.)
- **Adjust importance levels** based on business priorities and user feedback
- **Add QC Power** make sure QC is on, consider giving web access or improving the model if it requires real depth. 

## REFINEMENT FOCUS REMINDER
**Your mission**: Make targeted improvements to an existing  configuration based on aggregated user instructions and validation results. Preserve what works, fix what doesn't, and use exact column names. Return both technical and simple AI summaries with your changes - that make sense in the context of refinement. 