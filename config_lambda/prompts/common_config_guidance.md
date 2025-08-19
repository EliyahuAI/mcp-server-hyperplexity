# Common Configuration Guidance

This document contains shared guidelines used by both new config creation and refinement processes.

## Model Selection Guidelines
- **Default Model**: `sonar-pro` is the default for most use cases
- **Alternative Models**: Available models include:
  - Perplexity models: `sonar`, `sonar-pro` (recommended for most validation tasks)
  - Anthropic models: `claude-sonnet-4-0` (latest Claude 4), `claude-3-opus`, `claude-3-haiku`
- **Per-Column Model**: Use `preferred_model` field to override default for specific columns
- **Best Practices**:
  - Use Perplexity models (`sonar-pro`) for standard web search and validation tasks
  - Only use Anthropic models when deeper reasoning, complex analysis, or nuanced understanding is specifically required
  - Consider the validation complexity before choosing Anthropic models

## Search Context Size Guidelines
- **Values**: `"low"`, `"high"`
- **Global Default**: Set `default_search_context_size` at the root level (defaults to `"low"`)
- **Per-Column Override**: Use `search_context_size` field for specific columns
- **Best Practices**:
  - Use `"low"` for most columns (faster, cheaper, usually sufficient)
  - Use `"high"` only when search results are missing critical information
  - Avoid `"high"` unless necessary as it increases cost and latency
- **Search Group Behavior**: When multiple columns in a search group have different context sizes, the highest value is used for the entire group

## Importance Level Guidelines
- **ID**: These define the rows - at least one column must be assigned 'ID', usually it is one or more columns to the left of the table. 
- **CRITICAL**: Core business data, status fields, key metrics
- **HIGH**: Important descriptive or analytical fields
- **MEDIUM**: Supporting information, secondary attributes
- **LOW**: Optional or supplementary data
- **IGNORED**: Metadata, internal fields, timestamps

## Search Group Strategy
Create search groups based on where information typically appears together:
- **Regulatory data**: FDA approvals, clinical phases, trial IDs
- **Commercial data**: Companies, products, market information  
- **Technical data**: Targets, mechanisms, scientific details
- **Timeline data**: Launch dates, milestone timelines

## Intelligent Analysis Process

When analyzing any table, follow this process:

1. **Infer table purpose** from column names and data patterns
2. **Detect data types** from sample values (dates, numbers, strings, URLs)
3. **Identify likely ID columns** from names and uniqueness patterns
4. **Deduce domain/industry** from content and terminology
5. **Group related columns** that would appear in same sources
6. **Extract real examples** from the actual data (if possible, otherwise specify a consistent set)
7. **Assign importance levels** based on column criticality

## Analysis Presentation Format

Show your assumptions clearly in this format:

**MY ANALYSIS:**

**Table Purpose**: [Your inference from columns/data]
**Domain**: [Deduced industry/field]
**Preferred Sources**: [Logical sources for this domain]

**Unique Identifiers**: [Likely ID columns based on names/uniqueness]

**Search Groups**:
- Group 0: [ID columns] (not validated, used for context)
- Group 1: [Columns typically found together in source A]
- Group 2: [Columns typically found together in source B]
- Group N: [Additional logical groupings]

**Column Classifications**:
| Column | Importance | Format | Notes | Examples (from data) |
|--------|------------|--------|-------|---------------------|
| [name] | [level] | [type] | [formatting rules] | [actual values] |

## Targeted Questions Guidelines

Only ask when genuinely unclear or need confirmation:

### Types of Questions to Ask:
- **Corrections**: "Is my understanding of [specific assumption] correct?"
- **A/B Clarifications**: "For [ambiguous column], should this be: A) [option A] or B) [option B]?"
- **Domain specifics**: "What specific sources should I prioritize for [domain-specific information]?"

### Avoid Asking:
- ❌ Obvious table purposes (clear from column names)
- ❌ Clear data formats (evident from sample data)
- ❌ Standard examples (use real data from table)
- ❌ Basic groupings (infer from logical relationships)
- ❌ Model preferences (default to sonar-pro unless complex reasoning needed)

## Format Detection Guidelines

Auto-detect from sample data:
- Dates: YYYY-MM-DD, MM/DD/YYYY patterns
- Numbers: Integer, decimal, currency patterns
- URLs: http/https patterns
- Emails: @ symbol patterns
- Strings: Default for text data

## Search Group Requirements (MANDATORY)

Search groups are **REQUIRED** for every configuration - they are essential for building an effective search strategy and cannot be omitted.

**MANDATORY REQUIREMENTS:**
- **You MUST define at least two search groups** in the `search_groups` array (Group 0 and another)
- **Every validation target MUST be assigned to a search group** via the `search_group` field
- **Group 0**: Always ID/identifier fields (not validated, used for context), you must provide an ID group and assign at least one validation target to this. Note - these usually come from the left-most column(s).  
- **Group 1+**: Columns whose information appears together in typical sources
- **Upper limit**: No more than 5 gropus allowed
- **No ungrouped fields allowed**: Every column must belong to a search group for optimal performance

**Why Search Groups are Mandatory:**
- **Performance**: Grouped validation is faster and more efficient than individual column validation
- **Consistency**: Related fields get validated together using the same sources
- **Cost Optimization**: Reduces API calls by batching related columns
- **Source Strategy**: Ensures fields that appear together in sources are searched together

