# Common Configuration Guidance

This document contains shared guidelines used by both new config creation and refinement processes.

## Model Selection Guidelines
- **Default Model**: `sonar` is the default for most use cases - particularly for new configurations
- **Alternative Models**: Available models include:
  - Perplexity models: `sonar` (recommended for simple fact checking - default for new configurations), `sonar-pro` (recommended for deeper synthesis of sources, a great inexpensive upgrade for more reasoning)
  - DeepSeek models: `deepseek-v3.2` (ultra-low cost, 97% cheaper than Claude - FRONT LINE for reasoning without web search, displaces Haiku and Sonnet for pure reasoning tasks), `deepseek-v3.2-exp` (variant with caching support)
  - Anthropic models: `claude-sonnet-4-5` (automatic fallback for DeepSeek, first line when web search is needed for reasoning), `claude-opus-4-1` (expensive advanced reasoning - only for deep synthesis requiring web research)
- **Best Practices**:
  - Use Perplexity models (`sonar` or `sonar-pro`) for standard web search and validation tasks
  - Use `deepseek-v3.2` for pure reasoning tasks that don't require web access (QC review, synthesis of existing data, analysis)
  - Use `claude-sonnet-4-5` when web search is needed for reasoning tasks (anthropic_max_web_searches > 0)
  - Only use `claude-opus-4-1` when deep reasoning with extensive web research is critical
  - **CRITICAL LIMITATION**: DeepSeek cannot access the web - never use with anthropic_max_web_searches > 0
  - **Recommended QC Approach**: Sonar/Sonar-Pro validation (with web search) → DeepSeek V3.2 QC (without web search, ultra-low cost)

## Search Context Size Guidelines for Perplexity
- **Values**: `"low"`,  `"medium"`,`"high"` (default), (Perplexity only)
- **Global Default**: Set `default_search_context_size` at the root level (defaults to `"high"`, unless you it is a simple fact lookup -> `"low"`). Setting search context to `"low"` results in the fastest results. 
- **Per-Search Group Override**: You can use `search_context_size` field for specific search groups
- **Best Practices**:
  - Use `"high"` for most columns (cheap enough with sonar, takes time but worth it).
  - Use `"medium"`, and `"low"` when search results are obvious.

## Anthropic Web Search Guidelines
- **Global Default**: Set `anthropic_max_web_searches_default` at the root level (defaults to 1)
- **Per-Search Group Override**: Use `anthropic_max_web_searches` field (0-10) for specific search groups  
- **Recommended Values**:
  - **0**: Disable web search entirely (cached knowledge only), great for reasoning only tasks
  - **1**: For obvious items that need the internet, but still benefit from anthropic models (default)
  - **3**: For more complex items requiring moderate research, this can get expensive fast
  - **5**: For esoteric facts requiring extensive search - a bit of a last resort. 
- **Cost Control**: Lower values reduce API costs but may miss current information


## Importance Level Guidelines
- **ID**: These define the rows - at least one column must be assigned 'ID', usually it is one or more columns to the left of the table.  Getting these right is critical as these define the row information and the stability of the analysis.  An Index is not enough.
- **CRITICAL**: ANy column requiring research that we can help with
- **IGNORED**: Indices, metadata, internal fields, timestamps, calculated/formula columns that are dependent on other columns and need calculation not AI approximation. 

## Search Group Strategy
Create search groups based on where information typically appears together. Are these elements usually found together? For example, a conference start date, end date, and location are almost always found together, and should be part of the same group. Critically, these groups are processed sequentially, from low to high with information aggregated along the way - make sure that more sophisticated and fragile information is presented after information that it might need first!

## Intelligent Analysis Process

When analyzing any table, follow this process:

1. **Infer table purpose** from column names and data patterns, how is this table used? who uses it? what are the critical patterns?
2. **Detect data types** from sample values (dates, time, numbers, strings, URLs, etc.) - be specific about the format in the notes is not evident in the examples. 
3. **Identify likely ID columns** usually the first column(s), these are used to identify the row and are not used for research. Another indicator of an ID collumn is that they are usually filled in in every row. In many cases you need more than 1 column to form the stable context for the row. 
5. **Group related columns** that would appear in same sources, with the simplest information in the lowest columns.
6. **Extract real examples** from the actual data if provided and consistent with the guidance, otherwise specify a new consistent set.  Examples must match the requirements, update the examples to be in scope. Strongly prefer consistent formatting across the examples.  
7. **Assign importance levels** based on column criticality, mark calculated/formula columns as IGNORED as they are dependent on other columns and require calculation not AI research, ID columns needed to specify the row precisely, critical columns which serve the tables primary purpose. Make sure to mark any columns that you do not know what they are as IGNORED.

## Analysis Presentation Format

Show your assumptions clearly in this format:

**Technical AI Summary:**

**Table Purpose**: [Your inference from columns/data]
**Unique Identifiers**: [Likely ID columns]

**Search Groups**:
- Group 0: [ID columns] (not validated, used for context)
- Group 1: [Columns typically found together in source A]
- Group 2: [Columns typically found together in source B]
- Group N: [Additional logical groupings]

**Column Classifications**:
| Column | Importance | Format | Notes | Examples (from data) |
|--------|------------|--------|-------|---------------------|
| [name] | [level] | [type] | [formatting rules] | [actual values] |

## Clarification Urgency Scale

**Use these anchored levels:**
- 0.0-0.1 = MINIMAL (configuration is solid, minor tweaks only)
- 0.2-0.3 = LOW (clarification would improve the output modestly)
- 0.4-0.6 = MODERATE (important clarifications needed)
- 0.7-0.8 = HIGH (significant assumptions made)
- 0.9-1.0 = CRITICAL (core columns will likely be wrong)

**REFINEMENT RULE**: Always use LOWER urgency than the original configurations

## CLARIFYING QUESTIONS - When and How to Ask

**IMPORTANT CONTEXT**: Clarifying questions are shown to the user AFTER they see the validation preview results. DO NOT reference the preview data in your questions - you can see the preview, but the user sees questions AFTER reviewing it.

**When to Ask Questions:**
- ONLY ask when genuinely unclear or when clarification would significantly improve results
- Prefer NO questions if the configuration is solid
- Keep total questions to 2-3 maximum (shorter is better)

**How to Format Questions:**

✅ **GOOD - Clear, lay-person language:**
- "Should I prioritize recent information (last 6 months) or include historical data?"
- "Do you need detailed breakdowns or summary-level information?"

❌ **BAD - References preview, technical details, or specific models:**
- "The preview shows X - should I change Y?" (user hasn't seen preview yet when answering)
- "Should I use claude-sonnet-4-5 instead of sonar-pro?" (exposes internal model names)
- "Should I increase anthropic_max_web_searches from 1 to 3?" (technical parameter)
- "Should I set search_context_size to high?" (technical detail)

**Question Format Rules:**
1. **Limit A/B choices to 2 options maximum** - don't offer 3+ alternatives
2. **Use general terms** - "more thorough searching" not "high search context"
3. **Never mention specific models or costs** - "more advanced AI" not "claude-opus-4-1 at $15 per 1M tokens"
4. **Keep it short** - one clear sentence per question
5. **Focus on business needs** - what information they want, not how we get it
6. **Don't reference preview data** - questions are shown AFTER preview, so don't say "I noticed X in the results"

**Cost/Accuracy Tradeoff Language:**
- ✅ "Would you like more thorough analysis? This increases AI usage."
- ❌ "Should I upgrade to claude-opus-4-1 for $15/million tokens?"

**Types of Questions to Ask:**
- **Risky Assumptions**: "Should I focus on [assumption] or [alternative]?"
- **Scope Clarification**: "Do you need [option A] or [option B]?"
- **Quality Tradeoff**: "Would you like more thorough searching? This increases processing time and AI usage."

**Avoid Asking:**
- ❌ Obvious table purposes (clear from column names)
- ❌ Clear data formats (evident from sample data)
- ❌ Questions about preview data (questions shown after user sees preview)
- ❌ Specific model preferences (internal technical details)
- ❌ Technical parameters (search context, token limits, etc.)
- ❌ Questions with 3+ options (limit to 2 choices)

## Format Detection Guidelines

Auto-detect from sample data:
- Dates: YYYY-MM-DD, MM/DD/YYYY patterns, be consistent about the inclusion of time. 
- Numbers: Integer, decimal, currency patterns
- URLs: http/https patterns
- Emails: @ symbol patterns
- Strings: Default for text data

## Units and Measurements Guidelines

**Units Consistency**: If a column contains values with units (e.g., $B for billions, °C for temperature, mg for dosage, etc), make sure to specify in the notes that all values should consistently include the same units across all rows. This ensures validation results maintain proper unit formatting. When you detect a potential variablity in units of response, make sure the examples include consistent units (dont mit $T with $B, etc.)

## Quality Control (QC) Settings Guidelines

QC provides automated review of validation outputs to improve accuracy and consistency.

### QC Configuration Options
- **Enable QC**: Set `enable_qc: true` to enable automated quality control review
- **QC Models**: Default is `["deepseek-v3.2", "claude-sonnet-4-5"]` for ultra-low cost with quality fallback
- **Token Allocation**: Default 8K base + 4K per validated column (excluding ID fields)
- **Web Searches**: Default 0 (disabled) for cost efficiency, increase when getting it right is critical, or when the model already used claude with web searches.

### When to Configure QC
- **Enable QC (Recommended)**: For most validation tasks where accuracy is important
- **Default QC**: Uses `deepseek-v3.2` (97% cheaper than Claude, excellent quality)
- **Advanced QC Models**: Automatic fallback to `claude-sonnet-4-5` if deepseek fails
- **Increase QC Web Searches**: When you need to get everything right, or when claude web search is already being used.
- **Disable QC**: Only for simple fact-checking tasks or when speed is more important than accuracy


## Search Group Requirements (MANDATORY)
Search groups are **REQUIRED** for every configuration - they are essential for building an effective search strategy and cannot be omitted.

**MANDATORY REQUIREMENTS:**
- **You MUST define at least two search groups** in the `search_groups` array (Group 0/ID Group and another)
- **Every validation target MUST be assigned to a search group** via the `search_group` field (except those with IGNORED importance)
- **Group 0**: Always ID/identifier fields (not validated, used for context), you must provide an ID group and assign at least one,  validation target to this. Note - these usually come from the left-most column(s). No validated columns in this group!
- **Group 1+**: Columns whose information appears together in typical sources
- **Target Number of Groups**: Shoot for number of validation columns ceil((non-ID or IGNORED)/2)
- **Upper limit**: Maximum 10
- **No ungrouped fields allowed**: Every column must belong to a search group for optimal performance

## Embedding Tablewide Context Research

When **tablewide context research** is provided (e.g., background about a specific company, methodology, or domain-specific information), you MUST embed it appropriately:

- **General Notes**: If the research is relevant to the ENTIRE table or multiple columns, embed concise key points in the `general_notes` field
- **Column Notes**: If the research is relevant to ONLY ONE specific column, embed it in that column's `notes` field
- **Focus on Non-Common Knowledge**: Only embed information that is NOT common knowledge or that provides specific context the AI wouldn't know
- **Keep It Concise**: Summarize the research into actionable context relevant to the table topic. 
