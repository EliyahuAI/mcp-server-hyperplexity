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

**IMPORTANT:** We need at least {{MIN_ROW_COUNT}} usable results. If discovery found fewer than {{MIN_ROW_COUNT}} total entities, you'll be asked to provide recommendations for improvement.

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

**Bonus Consideration - Well-Populated Rows:**
- Rows with populated research columns (shown as "Populated Research Columns" in row data) have extra value
- These rows already have data beyond ID fields, reducing validation work later
- When choosing between similar-quality rows, prioritize those with more populated research columns
- This doesn't override quality assessment - a well-populated low-quality row should still be demoted/rejected

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

## 5B. DECISION TREE - What Action to Take After Review

**After reviewing rows, you have FOUR possible outcomes based on how many you approved:**

### Count Your Approved Rows

Count rows with: `keep=true` AND `qc_score >= 0.5`

```
Approved Count >= {{MIN_ROW_COUNT}} (typically 4)?
    YES → ✅ Option 1: SUCCESS (return approved rows, you're done)
    NO  → Continue to decision tree below ↓
```

### Decision Tree for Insufficient Rows

```
Approved: 1-3 rows?
    ↓
Can you identify NEW subdomains to search (domains we didn't explore)?
    YES → 🔄 Option 2: RETRIGGER (add new subdomains, keep table structure)
    NO  → ⬆️ Option 3: PROMOTE (system auto-promotes top rejected rows)

Approved: 0 rows?
    ↓
Do entities exist but table structure prevented discovery?
    YES → 🔧 Option 4: RESTRUCTURE (redesign table, restart from column definition)
    NO  → ❌ Option 5: GIVE_UP (apologize, show new table card)
```

### Quick Reference

| Approved | Can Find More? | Table Structure | Action |
|----------|----------------|-----------------|--------|
| >= 4 | N/A | N/A | ✅ SUCCESS |
| 1-3 | YES (new domains) | Good | 🔄 RETRIGGER |
| 1-3 | NO | Good | ⬆️ PROMOTE |
| 0 | N/A | Broken | 🔧 RESTRUCTURE |
| 0 | N/A | Fine but no entities | ❌ GIVE_UP |

### Key Questions to Ask Yourself

**For 1-3 approved rows:**
1. Did we search all relevant domains? (NO → RETRIGGER, YES → PROMOTE)
2. Are there obvious search domains we missed? (YES → RETRIGGER, NO → PROMOTE)

**For 0 approved rows:**
1. Did we find ANY candidates (even if rejected)? (YES → likely RESTRUCTURE, NO → likely GIVE_UP)
2. Were ID columns too complex? (YES → RESTRUCTURE)
3. Were requirements too strict? (YES → RESTRUCTURE)
4. Do these entities fundamentally not exist? (YES → GIVE_UP)

---

## 6. Option 2: RETRIGGER - Add New Subdomains (1-3 approved, more to find)

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

**When to Retrigger:**

You should request a retrigger ONLY when ALL of these conditions are met:

1. **Insufficient Quality Rows**: Fewer than {{MIN_ROW_COUNT}} rows meet the hard requirements (would be kept after QC)
2. **Confidence in Better Strategy**: You have identified a specific, concrete search approach that is likely to yield better results
3. **Clear Deficiency**: You can articulate what was wrong with the current search strategy and how a new approach would address it

**When NOT to Retrigger:**

- If {{MIN_ROW_COUNT}}+ rows meet hard requirements (even if soft requirements aren't fully met)
- If the topic is genuinely rare/niche and unlikely to yield more results
- If you cannot identify a meaningfully different search strategy
- If the current search strategy was already well-designed and comprehensive

**Provide this field in your response:**

```json
"retrigger_discovery": {
  "should_retrigger": true,
  "reason": "Clear explanation: (1) Why current results are insufficient, (2) What was wrong with current search approach, (3) Why new strategy is likely to succeed",
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
- This will run ONE additional discovery cycle
- Only use this if you meet ALL conditions above
- If you don't want to retrigger, omit this field or set should_retrigger: false

---

## 7. Autonomous Recovery Decision (If 0 Rows Approved)

### CRITICAL: When 0 Rows Approved After QC

**If you approve 0 rows (all rows rejected or no rows discovered), you MUST make an autonomous decision:**

Can restructuring the table help, or is this request fundamentally impossible?

### Your Decision Options

**Option A: RECOVERABLE - Restructure and Retry**
- The topic/domain exists and has discoverable entities
- The problem was in HOW we structured the table (columns, requirements, search strategy)
- We can fix it by: simplifying ID columns, relaxing requirements, or broadening search domains
- **Action**: Provide `recovery_decision` with restructuring instructions

**Option B: UNRECOVERABLE - Give Up**
- The topic is too niche, doesn't exist, or entities are genuinely undiscoverable via web search
- No amount of restructuring will help (e.g., "companies that don't exist", "proprietary internal data")
- **Action**: Provide `recovery_decision` explaining why it's impossible

### Decision Criteria

**Choose RECOVERABLE if:**
- Subdomain results show partial matches that were filtered out by strict criteria
- ID columns are too complex (e.g., requiring specific fields not in search results)
- Requirements are too strict (hard requirements that could be softened)
- Search strategy was too narrow (could expand to related domains)
- **Key indicator**: "The entities exist, but our table structure made them hard to discover"

**Choose UNRECOVERABLE if:**
- All subdomains returned 0 results even after escalation
- Web search fundamentally cannot answer this (proprietary data, future predictions, etc.)
- Topic is fabricated or extremely rare (< 5 entities globally)
- Requirements contradict each other or are impossible to satisfy
- **Key indicator**: "The entities don't exist or are impossible to discover via web search"

### Response Format for recovery_decision

**If RECOVERABLE - Provide restructuring guidance:**
```json
"recovery_decision": {
  "decision": "restructure",
  "reasoning": "Clear explanation of why this is recoverable (2-3 sentences)",
  "restructuring_guidance": {
    "column_changes": "Specific instructions for column generator: 'Simplify ID columns to only Company Name and Website. Move Product Name to a research column.'",
    "requirement_changes": "How to adjust requirements: 'Make funding status a soft requirement instead of hard. Broaden to include both series A and seed stage.'",
    "search_broadening": "How to expand search strategy: 'Include also digital health companies, not just pure AI companies.'"
  },
  "user_facing_message": "I found that the table structure was too specific. I'm restructuring it with simpler columns and broader criteria. Retrying discovery now..."
}
```

**If UNRECOVERABLE - Admit defeat:**
```json
"recovery_decision": {
  "decision": "give_up",
  "reasoning": "Clear explanation of why this cannot work (2-3 sentences)",
  "fundamental_problem": "Specific issue that makes this impossible: 'This topic requires proprietary company data that isn't publicly available via web search.'",
  "user_facing_apology": "I apologize, but I wasn't able to find any rows for this table. [Explain the fundamental problem in friendly terms]. Unfortunately, this type of information isn't discoverable through web searches. Would you like to try a different table topic?"
}
```

**NO technical jargon in user_facing messages:** Don't mention subdomains, models, escalation levels, sonar, claude, search strategies, or other system internals.

### insufficient_rows_statement (DEPRECATED - use recovery_decision instead)

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

An array of specific, actionable suggestions for how the user can modify their request to get better results.

**Focus on THREE types of recommendations:**

1. **Search Broadening** - How to adjust the original request wording
2. **Table Restructuring** - How to change columns to make discovery easier
3. **Criteria Adjustment** - How to relax requirements or add alternatives

**Example:**
```json
"insufficient_rows_recommendations": [
  {
    "type": "search_broadening",
    "issue": "Your request focused on a very specific combination of criteria",
    "recommendation": "Try adding phrases like 'including early-stage companies' or 'companies working in related medical imaging fields' to your original request"
  },
  {
    "type": "table_restructuring",
    "issue": "The ID columns required very specific details that weren't discoverable",
    "recommendation": "Consider simplifying your ID columns to just 'Company Name' and 'Website' instead of requiring 'Product Name' and 'Founding Year' as identifiers"
  },
  {
    "type": "criteria_adjustment",
    "issue": "Many relevant companies might use different terminology",
    "recommendation": "In your request, you could add: 'include companies that describe themselves as clinical decision support or diagnostic AI, not just radiology AI'"
  },
  {
    "type": "table_restructuring",
    "issue": "Some data columns might work better as ID columns for discoverability",
    "recommendation": "Move 'Industry Focus' from a data column to an ID column, so we can search for 'healthcare AI companies' more directly"
  }
]
```

**Format guidelines:**
- Include `type` field for each recommendation (search_broadening, table_restructuring, criteria_adjustment)
- Plain, conversational language
- Specific suggestions the user can understand and act on
- **Table restructuring recommendations** should suggest concrete column changes
- Encouraging tone - "you could try", "consider adding", "might help to include"

---

Review all rows and return your assessment.
