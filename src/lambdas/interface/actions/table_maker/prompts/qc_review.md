# Quality Control Review

## 1. Prompt Structure Overview

This QC review prompt serves multiple functions to help you assess discovered table rows:

**What this prompt contains:**

1. **Subdomains List** - All search areas attempted with their result counts
2. **Table Context** - User's request, table definition, and requirements
3. **Rows to Review** - Discovered entities with discovery metadata
4. **Row-by-Row Validation Task** - Your job: approve, demote, or reject each row
5. **Retrigger Section (Technical)** - System context for requesting additional discovery
6. **User-Facing Feedback** - How to communicate with the user if results are insufficient

**Your core tasks:**
- Review discovered rows against requirements
- Assign quality scores and keep/reject decisions
- Provide user-friendly feedback if results came up short
- Optionally request additional discovery with new search strategies

---

## 2. Subdomains List (From Discovery)

**All search areas attempted:**

{{SUBDOMAIN_RESULTS_SUMMARY}}

Each subdomain shows:
- **Number** - Reference ID (1-based index)
- **Name** - Subdomain name
- **Focus** - What this search area covered
- **Result Count** - How many entities were discovered
- **No Matches Reason** (for 0-result subdomains) - Why this search strategy failed

Example format:
```
1. "AI Research Companies" - Academic/research-focused AI companies (8 results)
2. "Healthcare AI" - Healthcare and medical AI companies (5 results)
3. "Radiology AI Startups" - Specialized radiology AI startups (0 results)
   Reason: Search queries too specific, combining three narrow criteria (radiology + AI + startup stage) yielded no matches. Consider broadening to "medical imaging AI" or removing the startup stage requirement.
```

---

## 3. Table Context

### User's Original Request

{{USER_CONTEXT}}

### Table Definition

**Table Name:** {{TABLE_NAME}}

**Table Purpose:** {{TABLE_PURPOSE}}

**Background Research Context:**
{{TABLEWIDE_RESEARCH}}

### Requirements for This Table

#### Hard Requirements (Must Meet):
{{HARD_REQUIREMENTS}}

#### Soft Requirements (Preferences):
{{SOFT_REQUIREMENTS}}

**QC Instructions:**
- **Reject:** Only for clear violations of hard requirements, obvious duplicates, or fake/fabricated entries
- **Demote (keep=true, priority=demote):** Doesn't meet soft requirements well but is real and meets hard requirements - marginal but acceptable
- **Approve (keep=true, priority=promote or none):** Meets requirements well, good fit for the table

**Key Principle:** Be conservative with rejections. If an entity meets hard requirements and is real, keep it (even if demoted). Only reject for hard requirement violations or quality issues.

### Understanding the Rows

Each row in this table represents **one specific entity**. Rows are defined by their **ID fields** (identification columns).

#### ID Fields (What Identifies Each Row)

{{ID_COLUMNS}}

**What this means:**
- Each row is a UNIQUE entity (e.g., one company, one paper, one person)
- The ID fields contain the IDENTIFIERS for that entity
- Example: For company "Anthropic", ID fields would be: Company Name="Anthropic", Website="https://anthropic.com"

#### All Column Definitions (For Context)

{{COLUMN_DEFINITIONS}}

---

## 4. Rows to Review ({{ROW_COUNT}} discovered)

{{DISCOVERED_ROWS}}

Each discovered row has:
- **row_id** - Unique identifier for this row
- **id_values** - The actual identifiers for this entity (populated ID fields)
- **row_score** - Discovery score from search (0-1)
- **model_used** - Which model found it (sonar, sonar-pro, claude)
- **context_used** - Search context level (low, high)
- **subdomain_number** - Which subdomain discovered this (1-based index from Section 2)
- **match_rationale** - Why it was selected during discovery
- **source_urls** - Where the information was found

---

## 5. Row-by-Row Validation Task

### Your Job

Review each discovered row to decide if it should be included in the final table.

You will:
1. **Decide which rows to keep** (genuinely match user's needs)
2. **Reject rows that** don't match, are duplicates, or are low quality
3. **Assign QC scores** (0-1) with more nuance than discovery scoring
4. **Adjust priorities** (promote exceptional fits, demote marginal ones)

**IMPORTANT:** We need at least 4 usable results. If discovery found fewer than 4 total entities, you'll be asked to provide recommendations for improvement.

### Three-Tier System: Keep or Reject?

Use the existing `keep` and `priority_adjustment` fields to indicate quality tier:

**Tier 1 - Approve (keep=true, priority=promote or none):**
- Genuinely matches user requirements well
- Meets both hard requirements and most soft requirements
- Unique entity (not duplicate)
- Good quality sources
- Use **priority=promote** for exceptional fits (top-tier examples)
- Use **priority=none** for strong, solid fits

**Tier 2 - Demote but Keep (keep=true, priority=demote):**
- Meets all hard requirements (if any)
- Doesn't meet soft requirements well
- Real entity but marginal fit
- Lower quality but not fake
- **These rows are acceptable fillers** - keep them, just rank lower

**Tier 3 - Reject (keep=false):**
- Violates hard requirements
- Obvious duplicate (same entity as another row)
- Fabricated/nonsense entries (clearly made-up URLs, fake entities)
- Completely off-topic or wrong entity type

**Key Principle:** Be conservative with rejections. If it's a real entity that meets hard requirements, demote it rather than reject it. Only reject for clear violations, duplicates, or fake entries.

### Assign QC Score (0-1.0)

More flexible than discovery rubric. Consider:
- **Overall relevance** to user's goals
- **How well it meets hard vs soft requirements**
- **Uniqueness** (not duplicate)
- **Actionability** (can we validate this?)
- **Strategic value** (good example for table)

**QC Score Guidelines:**
- **0.9-1.0:** Exceptional - perfect match, meets all requirements
- **0.7-0.89:** Strong - good fit, meets hard requirements and most soft
- **0.5-0.69:** Adequate - meets hard requirements, some soft requirements
- **0.3-0.49:** Marginal - meets hard requirements but few soft requirements (consider demoting)
- **0.0-0.29:** Poor - likely reject unless discovery was very sparse

**Note:** If your qc_score matches the discovery score (row_score), you can omit the qc_rationale - agreement needs no explanation. Only provide qc_rationale when your assessment differs significantly from the discovery score.

### Priority Adjustment (Maps to Three Tiers)

- **promote:** Tier 1 exceptional - rank higher, definitely include first
- **none:** Tier 1 solid - good fit, include
- **demote:** Tier 2 marginal - meets hard requirements but weak on soft, include but rank lower
- (reject is separate: keep=false)

### Output Format

**IMPORTANT: Use the row_id shown for each row in your response.**

Return JSON:

```json
{
  "reviewed_rows": [
    {
      "row_id": "1-Anthropic",
      "row_score": 0.95,
      "qc_score": 0.98,
      "qc_rationale": "Perfect match - leading AI company with active hiring",
      "keep": true,
      "priority_adjustment": "promote",
      "subdomain_number": 1
    },
    {
      "row_id": "2-PathAI",
      "row_score": 0.80,
      "qc_score": 0.80,
      "keep": true,
      "priority_adjustment": "none",
      "subdomain_number": 2
    },
    {
      "row_id": "3-Generic Corp",
      "row_score": 0.65,
      "qc_score": 0.2,
      "qc_rationale": "Not an AI company, off-topic",
      "keep": false,
      "priority_adjustment": "none",
      "subdomain_number": 1
    }
  ]
}
```

Note: Row 2 (PathAI) omits qc_rationale since qc_score matches row_score - no explanation needed for agreement.

**Note:** qc_summary will be auto-calculated from reviewed_rows if you don't provide it.

---

## 6. Retrigger Section (Technical - For System)

**This section provides system context to help you decide if requesting a retrigger would help.**

### Original Subdomains and Results

(Already shown in Section 2 above - see Subdomains List)

### Aggregated Search Improvements

{{AGGREGATED_SEARCH_IMPROVEMENTS}}

These are suggestions from the discovery workers about what worked and what didn't.

### Aggregated Domain Filtering Recommendations

{{AGGREGATED_DOMAIN_RECOMMENDATIONS}}

Feedback from discovery workers about which domains were helpful or problematic.

### Current Requirements

**Hard Requirements:**
{{HARD_REQUIREMENTS}}

**Soft Requirements:**
{{SOFT_REQUIREMENTS}}

### Current Domain Filters

**Included Domains:** {{CURRENT_INCLUDED_DOMAINS}}
**Excluded Domains:** {{CURRENT_EXCLUDED_DOMAINS}}

### How to Request Retrigger Discovery

If results are insufficient and you believe a different search strategy could help, you can request ONE additional discovery cycle.

**Provide this field in your response:**

```json
"retrigger_discovery": {
  "should_retrigger": true,
  "reason": "Why retrigger is needed - what was wrong with current approach",
  "new_subdomains": [
    {
      "name": "Completely New Subdomain Name",
      "focus": "What this subdomain should search for",
      "search_queries": [
        "specific query 1",
        "specific query 2",
        "specific query 3"
      ],
      "target_rows": 10,
      "included_domains": ["optional.com"],
      "excluded_domains": ["optional.com"]
    }
  ],
  "updated_requirements": [
    {
      "requirement": "New or modified requirement",
      "type": "hard" or "soft",
      "rationale": "Why this change helps"
    }
  ],
  "updated_default_domains": {
    "excluded_domains": ["add.com", "or-replace.com"]
  }
}
```

**Important Notes:**
- **Specify COMPLETELY NEW subdomains**, not modifications of existing ones. Redesign the search strategy from scratch.
- You can optionally adjust requirements (make them more/less strict) or excluded domain filters
- **You can only modify EXCLUDED domains, not included domains.** Included domains are set by the user and should not be changed.
- This will run ONE additional discovery cycle and merge results with existing rows (deduplication will be applied)
- Only use this if you genuinely believe different searches will find better results
- If you don't want to retrigger, omit this field or set should_retrigger: false

---

## 7. User-Facing Feedback (If Results Are Insufficient)

### Message to User (If We Came Up Short)

**ONLY provide this section if discovery found fewer than 4 total entities.**

If the discovery process returned fewer than 4 candidates total (not just 4 kept after QC, but 4 discovered in total), you must provide user-friendly feedback explaining what happened and how they can improve their request.

**Tone:** Apologetic and encouraging - we tried our best, here's what we attempted, and here's how you can help us do better.

**NO technical jargon:** Don't mention subdomains, models, escalation levels, sonar, claude, search strategies, or other system internals.

### insufficient_rows_statement

A brief, friendly summary (2-3 sentences) explaining what we tried and why results were limited.

**Focus on:**
- What search areas we explored (in plain language)
- What approaches we attempted
- Acknowledgment that we didn't find enough results

**Example:**
```json
"insufficient_rows_statement": "We searched across several different areas related to healthcare AI companies, but had difficulty finding enough companies that matched your specific criteria. We tried looking at general healthcare AI, specialized radiology tools, and research-focused companies, but many of our searches came up with very few matches."
```

**Avoid technical language like:**
- "Subdomain fragmentation"
- "Search queries too specific"
- "Escalation to Claude"
- "Model performance"

### insufficient_rows_recommendations

An array of specific, actionable suggestions for how the user can modify their ORIGINAL REQUEST to get better results.

**Focus on:**
- What to add to their initial request
- How to rephrase or broaden their criteria
- Specific language they could include
- Alternative angles they might not have considered

**Example:**
```json
"insufficient_rows_recommendations": [
  {
    "issue": "Your request focused on a very specific combination of criteria",
    "recommendation": "Try adding phrases like 'including early-stage companies' or 'companies working in related medical imaging fields' to your original request"
  },
  {
    "issue": "We found it challenging to locate companies in such a narrow specialty",
    "recommendation": "Consider broadening your request to include 'AI companies in healthcare diagnostics' or 'medical imaging AI' rather than focusing only on radiology"
  },
  {
    "issue": "Many relevant companies might use different terminology",
    "recommendation": "In your request, you could add: 'include companies that describe themselves as clinical decision support or diagnostic AI, not just radiology AI'"
  }
]
```

**Format guidelines:**
- Plain, conversational language
- Focus on modifying the ORIGINAL REQUEST (not technical search parameters)
- Specific suggestions the user can understand and act on
- Encouraging tone - "you could try", "consider adding", "might help to include"

---

Review all rows and return your assessment.
