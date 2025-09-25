# Common Configuration Guidance

This document contains shared guidelines used by both new config creation and refinement processes.

## Model Selection Guidelines
- **Default Model**: `sonar` is the default for most use cases - particularly for new configurations
- **Alternative Models**: Available models include:
  - Perplexity models: `sonar` (recommended for simple fact checking- default for new configurations), `sonar-pro` (recommended deeper synthesis of sources, a great inexpensive upgrade for more reasoning)
  - Anthropic models: `claude-opus-4-1` (latest Claude 4 opus for advanced reasoning - expensive!, bring out the big guns only when really deep thought and synthesis is needed - with ), `claude-sonnet-4-0` (latest Claude 4 - this is the first line of defense for advanced reasoning solutions that require search, and very helpful when pure reasoning is needed in response when anthropic_max_web_searches is set to 0, `claude-3.5-haiku-latest` (great for fast reasoning solutions that dont need much thought)
- **Best Practices**:
  - Use Perplexity models (`sonar` or`sonar-pro`) for standard web search and validation tasks
  - Only use Anthropic models only when deeper reasoning (sonnet-4 in most cases, opus when deep reasoning is called for)
  - Consider the validation complexity before choosing Anthropic models
  - Rely on the anthropic QC layer (with or without web-search) to process the full information for the row. Sonar/Sonar Pro validation with Sonnet QC without web search is a great first approach.

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
- **IGNORE**: Indices, metadata, internal fields, timestamps, calculated/formula columns that are dependent on other columns and need calculation not AI approximation. 

## Search Group Strategy
Create search groups based on where information typically appears together. Are these elements usually found together? For example, a conference start date, end date, and location are almost always found together, and should be part of the same group. Critically, these groups are processed sequentially, from low to high with information aggregated along the way - make sure that more sophisticated and fragile information is presented after information that it might need first!

## Intelligent Analysis Process

When analyzing any table, follow this process:

1. **Infer table purpose** from column names and data patterns, how is this table used? who uses it? what are the critical patterns?
2. **Detect data types** from sample values (dates, time, numbers, strings, URLs, etc.) - be specific about the format in the notes is not evident in the examples. 
3. **Identify likely ID columns** usually the first column(s), these are used to identify the row and are not used for research.
5. **Group related columns** that would appear in same sources
6. **Extract real examples** from the actual data if provided and consistent with the guidance, otherwise specify a new consistent set.  Examples must match the requirements, update the examples to be in scope. Strongly prefer consistent formatting across the examples.  
7. **Assign importance levels** based on column criticality, mark calculated/formula columns as IGNORE as they are dependent on other columns and require calculation not AI research, ID columns needed to specify the row precisely, critical columns which serve the tables primary purpose. 

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

## CLARIFYING QUESTIONS - CONFIGURATION CHOICES
Generate questions that explain what you configured and suggest specific improvements:

**Good**: "I configured searches for current revenue data - would you prefer quarterly breakdowns instead?"
**Bad**: "Should I validate revenue or skip it?"

Reference your actual configuration decisions and offer concrete alternatives that might work better. These must no refer to any technical details of the configuration. They should focus on the business needs, cost/accuracy tradeoffs for context and performance models, and critical assumptions.

Only ask when genuinely unclear or need confirmation that would likely impprove the quality of your search. Format your questions nicely, and clearly, requiring no technical understanding of the user.

### Types of Questions to Ask:
- **Risky Assumptions**: "Is my understanding of [specific assumption] correct?"
- **A/B Clarifications**: "I have assumed  [option A], is [option B] more accurate?"
- **Cost/Accuracy Tradeoff**: "Are you OK with increasing the AI usage to achieve better accuracy? I can use more advanced models and or more searches - but this can amplify cost." This is a good question when items are missed, or require complex synthesis, and you have held back in your recommendations.  

### Avoid Asking:
- ❌ Obvious table purposes (clear from column names)
- ❌ Clear data formats (evident from sample data)
- ❌ Standard examples (use real data from table)
- ❌ Specific model preferences 
- ❌ Specific row preferences 

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
- **QC Models**: Default models are `claude-sonnet-4-0` for cost-efficiency, can use `claude-opus-4-1` for complex cases
- **Token Allocation**: Default 8K base + 4K per validated column (excluding ID fields)
- **Web Searches**: Default 0 (disabled) for cost efficiency, increase when getting it right is critical, or when the model already used claude with web searches. 

### When to Configure QC
- **Enable QC (Recommended)**: For most validation tasks where accuracy is important
- **Advanced QC Models**: Use `claude-opus-4-1` for complex scientific/technical data requiring deeper reasoning
- **Increase QC Web Searches**: When you need to get everything right, or when claude web search is already being used. 
- **Disable QC**: Only for simple fact-checking tasks or when speed is more important than accuracy


## Search Group Requirements (MANDATORY)
Search groups are **REQUIRED** for every configuration - they are essential for building an effective search strategy and cannot be omitted.

**MANDATORY REQUIREMENTS:**
- **You MUST define at least two search groups** in the `search_groups` array (Group 0/ID Group and another)
- **Every validation target MUST be assigned to a search group** via the `search_group` field (except those with IGNORE importance)
- **Group 0**: Always ID/identifier fields (not validated, used for context), you must provide an ID group and assign at least one,  validation target to this. Note - these usually come from the left-most column(s). No validated columns in this group!
- **Group 1+**: Columns whose information appears together in typical sources
- **Target Number of Groups**: Shoot for number of validation columns ceil((non-ID or IGNORE)/2)
- **Upper limit**: Maximum 10
- **No ungrouped fields allowed**: Every column must belong to a search group for optimal performance

