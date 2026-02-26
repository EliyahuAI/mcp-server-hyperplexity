# Common Configuration Guidance

This document contains shared guidelines used by both new config creation and refinement processes.

## Model Selection Guidelines
- **Default Model**: `the-clone-flash` is the default for ALL search groups. This is an agentic mix of Perplexity web search with Gemini 3 Flash synthesis (Google AI Studio → OpenRouter).

- **IMPORTANT**: Only specify a `model` in a search group when you need something OTHER than `the-clone-flash`. If omitted, `the-clone-flash` is automatically used.

- **Model Tiers (lowest to highest capability/cost)**:
  - **Standard** (default): `the-clone-flash` — Perplexity web search + Gemini 3 Flash synthesis, fast and cost-effective for most tables
  - **Upgraded**: `the-clone-claude` — Perplexity web search + Claude synthesis, for complex or nuanced research
  - **Scientific/Technical tables** (use this as first choice, not an upgrade): `the-clone-claude` for all search groups + `claude-opus-4-6` QC (no web search) — whenever the table has a strong scientific, medical, or technical basis
  - **Calculation/light reasoning**: `gemini-3-flash-preview-min` — fast, no web search, for derived or formula-like fields
  - **Advanced synthesis without web**: `claude-sonnet-4-6` or `claude-opus-4-6` — for complex reasoning on existing context, no web access needed

- **Recommended QC Approach**: Default QC is `moonshotai/kimi-k2.5`. Upgrade to `claude-opus-4-6` (no web search) for scientific/technical tables or when default QC is missing errors.

## Importance Level Guidelines
- **ID**: These define the rows - **AT LEAST ONE COLUMN MUST BE ASSIGNED 'ID'** (MANDATORY), usually the first/primary identifier column(s) to the left of the table. Getting these right is critical as these define the row information and the stability of the analysis. An Index alone is not enough - use meaningful identifiers. **⚠️ NEVER convert ALL ID columns to RESEARCH - at least one must remain ID.**
- **RESEARCH**: Any column requiring research that we can help with
- **IGNORED**: Indices, metadata, internal fields, timestamps, calculated/formula columns that are dependent on other columns and need calculation not AI approximation. 

## Search Group Strategy
Create search groups based on where information typically appears together. Are these elements usually found together? For example, a conference start date, end date, and location are almost always found together, and should be part of the same group. Critically, these groups are processed sequentially, from low to high with information aggregated along the way - make sure that more sophisticated and fragile information is presented after information that it might need first!

## Intelligent Analysis Process

When analyzing any table, follow this process:

1. **Infer table purpose** from column names and data patterns, how is this table used? who uses it?
2. **Detect data types** from sample values (dates, time, numbers, strings, URLs, etc.) - be specific about the format in the notes is not evident in the examples. 
3. **Identify likely ID columns** usually the first column(s), these are used to identify the row and are not used for research. Another indicator of an ID collumn is that they are usually filled in in every row. In many cases you need more than 1 column to form the stable ID context for the row. 
5. **Group related columns** that would appear in same sources into a single search group, with the simplest information in the lowest group.
6. **Extract real examples** from the actual data if provided and consistent with the guidance, otherwise specify a new consistent set.  Examples must match the requirements, update the examples to be in scope. Strongly prefer consistent formatting across the examples. If you are instructed to do something different (e.g. in a refinement step you can generate examples that match the guidance.)  
7. **Assign importance levels** based on column criticality, mark calculated/formula columns as IGNORED as they are dependent on other columns and require calculation not AI research, ID columns needed to specify the row precisely, RESEARCH columns which serve the tables primary purpose. Make sure to mark any columns that you do not clearly know what they are as IGNORED.

## AI Summary Guidelines

**CRITICAL**: Keep ai_summary to 1-3 sentences maximum - a light description only.

**Good Examples** (1-3 sentences):
- ✅ "Set up thorough validation for company and researcher information with quick checks for dates and identifiers."
- ✅ "Upgraded validation for financial columns to improve accuracy based on previous results."
- ✅ "Configured comprehensive research validation for all data fields with quality control enabled."

**Bad Examples** (too long, too technical):
- ❌ Multiple paragraphs explaining every detail
- ❌ Mentioning specific models, search groups, or technical parameters
- ❌ Listing every column or change made

**Rules**:
- 1-3 sentences total
- Plain language only
- Focus on WHAT is being validated
- No technical details


## CLARIFYING QUESTIONS - When and How to Ask

**IMPORTANT CONTEXT**: Clarifying questions are shown to the user AFTER they see the validation preview results. DO NOT reference the preview data in your questions - you can see the preview, but the user sees questions AFTER reviewing it.

**When to Ask Questions:**
- ONLY ask when genuinely unclear or when clarification would significantly improve results
- Prefer NO questions if the configuration is solid
- Keep total questions to 2-3 maximum (shorter is better)

### Clarification Urgency Scale

**Use these anchored levels:**
- 0.0-0.1 = MINIMAL (configuration is solid, minor tweaks only)
- 0.2-0.3 = LOW (clarification would improve the output modestly)
- 0.4-0.6 = MODERATE (important clarifications needed)
- 0.7-0.8 = HIGH (significant assumptions made)
- 0.9-1.0 = CRITICAL (core columns will likely be wrong)

**REFINEMENT RULE**: Always use LOWER urgency than the original configurations

###
**How to Format Questions:**

✅ **GOOD - Clear, lay-person language:**
- "Should I prioritize recent information (last 6 months) or include historical data?"
- "Do you need detailed breakdowns or summary-level information?"

❌ **BAD - References preview, technical details, or specific models:**
- "The preview shows X - should I change Y?" (user hasn't seen preview yet when answering)
- "Should I use a different AI model?" (exposes internal model names)
- "Should I increase search depth?" (technical parameter)
- "Should I use more context?" (technical detail)
- "Should I prioritize these rows" (you can only influence columns, rows are fixed)

**Question Format Rules:**
1. **Limit A/B choices to 2 options maximum** - don't offer 3+ alternatives
2. **Use general terms** - "more thorough searching" not technical parameters
3. **Never mention specific models or costs** - "more advanced AI" not specific model names or prices
4. **Keep it short** - one clear sentence per question
5. **Focus on business needs** - what information they want, not how we get it
6. **Don't reference preview data** - questions are shown AFTER preview, so don't say "I noticed X in the results"
7. **No row selection data** - We cannot adjust rows or row attention - questions are about columns only.

**Cost/Accuracy Tradeoff Language:**
- ✅ "Would you like more thorough analysis? This increases processing time and cost."
- ❌ "Should I upgrade models or increase search depth?"

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
- **QC Models**: Default is `["moonshotai/kimi-k2.5"]`; upgrade to `["claude-opus-4-6"]` for scientific/technical tables
- **Token Allocation**: Default 8K base + 4K per validated column (excluding ID fields)

### When to Configure QC
- **Enable QC (Recommended)**: For most validation tasks where accuracy is important
- **Default QC**: `moonshotai/kimi-k2.5` — fast, cost-effective quality control
- **Upgrade QC**: `claude-opus-4-6` (no web search) — for scientific/technical tables or when default QC is catching frequent errors
- **Disable QC**: Only for simple fact-checking tasks or when speed is more important than accuracy or when pushed to reduce costs.

## Web Search Configuration (Claude Models Only)

**IMPORTANT**: Web search access for Claude models is **NOT a first-line approach**. Only configure when:
1. ✅ **Explicitly requested** by the user
2. ✅ **Other approaches have failed** - tried different models/strategies and accuracy is still poor
3. ❌ **NEVER as default** - adds significant cost and latency

### Where Web Search Can Be Configured

**QC Settings** (most common use case):
```json
{
  "qc_settings": {
    "enable_qc": true,
    "model": ["claude-opus-4-6"],
    "anthropic_max_web_searches": 3
  }
}
```
- Use when QC needs to verify information from current web sources
- Default is 0 (disabled)
- Range: 0-10 searches

**Search Groups** (per-group override):
```json
{
  "search_groups": [
    {
      "group_id": 1,
      "model": "claude-sonnet-4-5",
      "anthropic_max_web_searches": 3
    }
  ]
}
```
- Only when a specific search group needs web access and user has requested it
- Overrides `anthropic_max_web_searches_default` if both are set

**Top-level Default** (applies to all Claude search groups):
```json
{
  "anthropic_max_web_searches_default": 3
}
```
- Rarely used - only when user explicitly wants all Claude groups to have web access
- Does NOT affect QC (QC has its own setting)

### Web Search Guidelines
- **Cost Impact**: Each web search adds API cost and processing time
- **When to Use**: Only after trying `the-clone` (which has built-in web via Perplexity) first
- **Typical Values**: 3 searches is standard when enabled, 5+ for complex research
- **QC vs Validation**: If validation already uses `the-clone`, enable web search on QC only when QC specifically needs to verify with current sources

## Search Group Requirements (MANDATORY)
Search groups are **REQUIRED** for every configuration - they are essential for building an effective search strategy and cannot be omitted.

**MANDATORY REQUIREMENTS:**
- **You MUST define at least two search groups** in the `search_groups` array (Group 0/ID Group and another)
- **Every validation target MUST be assigned to a search group** via the `search_group` field (except those with IGNORED importance)
- **Group 0**: Always ID/identifier fields (not validated, used for context). **⚠️ MANDATORY: You MUST assign at least one column with `importance: "ID"` to Group 0** - this is required for row identification during validation. Note - these usually come from the left-most column(s). No validated columns in this group!
- **Group 1+**: Columns whose information appears together in typical sources
- **Target Number of Groups**: Shoot for number of validation columns ceil((non-ID or IGNORED)/2)
- **Upper limit**: Maximum 10
- **No ungrouped fields allowed**: Every column must belong to a search group for optimal performance
- **Model field**: ONLY specify `model` in a search group when using something other than `the-clone-flash` (the default). Omit the model field to use `the-clone-flash`.

## Embedding Tablewide Context Research

When **tablewide context research** is provided (e.g., background about a specific company, methodology, or domain-specific information), you MUST embed it appropriately:

- **General Notes**: If the research is relevant to the ENTIRE table or multiple columns, embed concise key points in the `general_notes` field
- **Column Notes**: If the research is relevant to ONLY ONE specific column, embed it in that column's `notes` field
- **Focus on Non-Common Knowledge**: Only embed information that is NOT common knowledge or that provides specific context the AI wouldn't know
- **Keep It Concise**: Summarize the research into actionable context relevant to the table topic. 
