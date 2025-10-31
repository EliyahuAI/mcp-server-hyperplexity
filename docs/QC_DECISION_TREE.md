# QC Review Decision Tree

**Purpose:** Clear criteria for QC to choose between retrigger, restructure, promote, or give up.

---

## Decision Flow

```
QC Reviews Rows
     ↓
Count approved rows (keep=true, qc_score >= 0.5)
     ↓
     ┌────────────────────────────────┐
     │  How many approved?            │
     └────────────────────────────────┘
              ↓
    ┌─────────┴──────────┐
    ↓                    ↓
>= MIN_ROW_COUNT    < MIN_ROW_COUNT
    ↓                    ↓
✅ SUCCESS          Insufficient Rows
                         ↓
              ┌──────────┴──────────┐
              ↓                     ↓
         0 Approved          1-3 Approved
              ↓                     ↓
      Zero Row Flow      Low Row Flow
              ↓                     ↓
    ┌─────────┴────────┐   ┌───────┴────────┐
    ↓                  ↓   ↓                ↓
RESTRUCTURE       GIVE_UP  RETRIGGER    PROMOTE
```

---

## Option 1: SUCCESS (>= MIN_ROW_COUNT approved)

**Criteria:**
- Approved rows >= MIN_ROW_COUNT (config: typically 4)
- At least MIN_ROW_COUNT rows have keep=true AND qc_score >= 0.5

**Action:**
- Return approved_rows as-is
- No retrigger, no restructure
- System proceeds to CSV generation

**Response:**
```json
{
  "approved_rows": [...],  // >= MIN_ROW_COUNT
  "rejected_rows": [...]
  // No retrigger_discovery field
  // No recovery_decision field
}
```

---

## Option 2: RETRIGGER (1-3 approved, can find more similar entities)

**Criteria:**
- Approved rows: 1-3 (some success, but not enough)
- You can identify NEW search domains/subdomains that weren't explored
- Current table structure is GOOD (ID columns are fine, requirements are reasonable)
- Problem: Search strategy didn't cover all relevant domains

**When to Use:**
- "We found 2 good companies, but only searched tech sector. Should also search healthcare sector."
- "Found 3 researchers, but only searched NIH grants. Should also search NSF and private foundations."
- Table structure is fine, just need broader search coverage

**Action:**
- Provide NEW subdomains to explore
- Keep current table structure
- Add new discovery round

**Response:**
```json
{
  "approved_rows": [...],  // 1-3 rows
  "rejected_rows": [...],
  "retrigger_discovery": {
    "should_retrigger": true,
    "reason": "Found 2 good companies but only searched venture-backed startups. Many bootstrapped AI companies exist that weren't covered.",
    "new_subdomains": [
      {
        "name": "Bootstrapped AI Companies",
        "focus": "Self-funded or revenue-funded AI companies (not VC-backed)",
        "search_queries": ["bootstrapped AI companies 2025", "profitable AI startups no funding"],
        "target_rows": 15
      }
    ]
  }
  // No recovery_decision field
}
```

---

## Option 3: PROMOTE (1-3 approved, no new domains to search)

**Criteria:**
- Approved rows: 1-3 (some success, but not enough)
- Cannot identify new subdomains to search (already comprehensive)
- Some rejected rows are decent quality (qc_score 0.3-0.49)
- Can promote best rejected rows to meet MIN_ROW_COUNT

**When to Use:**
- "We found 2 great rows and 5 mediocre rows. No new search domains to explore. Promote the best 2 mediocre ones."
- Search was already comprehensive, just need to lower bar slightly

**Action:**
- System automatically promotes top rejected rows to meet MIN_ROW_COUNT
- No retrigger needed
- No restructure needed

**Response:**
```json
{
  "approved_rows": [...],  // 1-3 rows
  "rejected_rows": [...],  // Include some with qc_score 0.3-0.49 (promotable)
  // No retrigger_discovery field
  // No recovery_decision field
  // System will auto-promote in backend
}
```

**Note:** Backend automatically promotes if approved < MIN_ROW_COUNT. You just need to make sure some rejected rows have decent scores (0.3-0.49).

---

## Option 4: RESTRUCTURE (0 approved, entities exist but table is broken)

**Criteria:**
- Approved rows: 0
- Entities EXIST and are discoverable (search found candidates)
- Problem: Table structure prevented discovery
  - ID columns too complex
  - Requirements too restrictive
  - Search domains too narrow

**When to Use:**
- "Found candidates but all rejected because ID columns required fields not in search results"
- "Requirements were so strict nothing passed, but entities exist with slightly relaxed criteria"
- Table design flaw, not fundamental impossibility

**Evidence to Look For:**
- Subdomain results show SOME matches (even if low quality)
- Search improvements suggest structural issues ("ID too complex", "requirements too strict")
- You can articulate HOW to fix the structure

**Action:**
- Provide restructuring guidance
- System restarts from column definition
- Research is reused (cached)

**Response:**
```json
{
  "approved_rows": [],  // 0 rows
  "rejected_rows": [...],
  "recovery_decision": {
    "decision": "restructure",
    "reasoning": "Entities exist but ID columns were too complex. Searches found companies but couldn't populate 'Detailed Product Description' as an ID field.",
    "restructuring_guidance": {
      "column_changes": "Simplify ID columns to only Company Name and Website. Move Product Description to a research column.",
      "requirement_changes": "Make 'Has active product' a soft requirement instead of hard.",
      "search_broadening": "Include also early-stage companies, not just Series B+."
    },
    "user_facing_message": "The table structure was too specific. Restructuring with simpler columns and broader criteria..."
  }
}
```

---

## Option 5: GIVE_UP (0 approved, entities don't exist)

**Criteria:**
- Approved rows: 0
- ALL subdomains returned 0 results (even after escalation)
- OR entities require proprietary/internal data
- OR topic is fundamentally impossible

**When to Use:**
- "All searches returned 0 results. These entities don't exist."
- "This requires internal company data not available via web search."
- "Request is contradictory (profitable companies that lost money)."

**Evidence to Look For:**
- ALL subdomains: 0 candidates found
- Search improvements say "no results found anywhere"
- Request requires data that web search fundamentally cannot provide

**Action:**
- Apologize and explain why
- Frontend shows "Get Started" card

**Response:**
```json
{
  "approved_rows": [],  // 0 rows
  "rejected_rows": [],
  "recovery_decision": {
    "decision": "give_up",
    "reasoning": "All search domains returned 0 results. These entities don't exist in publicly accessible sources.",
    "fundamental_problem": "This requires internal company data not available via web search.",
    "user_facing_apology": "I wasn't able to find any rows for this table. This type of information requires proprietary data that isn't publicly available. Would you like to try a different topic?"
  }
}
```

---

## Decision Matrix

| Approved Rows | Evidence | Action | Outcome |
|--------------|----------|--------|---------|
| >= 4 (MIN_ROW_COUNT) | N/A | ✅ SUCCESS | Return approved rows |
| 1-3 | New domains identifiable | 🔄 RETRIGGER | Add new subdomains, re-run discovery |
| 1-3 | No new domains, some decent rejected | ⬆️ PROMOTE | System auto-promotes rejected to meet min |
| 0 | Entities exist, structure broken | 🔧 RESTRUCTURE | Restart from column definition |
| 0 | Entities don't exist | ❌ GIVE_UP | Apologize, show new table card |

---

## Key Distinctions

### RETRIGGER vs RESTRUCTURE

**RETRIGGER:**
- Table structure is GOOD ✅
- Just need to search MORE PLACES
- Keep columns, requirements as-is
- Add new subdomains
- Example: "Searched tech sector, now search healthcare sector"

**RESTRUCTURE:**
- Table structure is BROKEN ❌
- Need to REDESIGN the table
- Change columns, requirements, search strategy
- Restart from column definition
- Example: "ID columns too complex, simplify them"

### PROMOTE vs RETRIGGER (when 1-3 approved)

**PROMOTE:**
- No new places to search
- Already searched comprehensively
- Some rejected rows are close (0.3-0.49 score)
- Just lower the bar slightly

**RETRIGGER:**
- Found new places to search
- Haven't covered all relevant domains
- Worth exploring more before lowering standards

### RESTRUCTURE vs GIVE_UP (when 0 approved)

**RESTRUCTURE:**
- Entities EXIST somewhere
- Table design prevented finding them
- Can articulate HOW to fix

**GIVE_UP:**
- Entities DON'T EXIST
- OR fundamentally undiscoverable
- No structural fix will help

---

## Examples

### Example 1: 12 Approved → SUCCESS
- Action: Return approved rows
- No additional action needed

### Example 2: 2 Approved, Searched Only Tech → RETRIGGER
- Found: 2 AI companies (tech sector)
- Missing: Healthcare AI, Finance AI sectors
- Action: Retrigger with new subdomains for those sectors

### Example 3: 2 Approved, Searched Everything → PROMOTE
- Found: 2 excellent companies
- Searched: All relevant sectors comprehensively
- Rejected: 8 companies with scores 0.35-0.45 (decent but not great)
- Action: Let system promote top 2 rejected to meet MIN_ROW_COUNT=4

### Example 4: 0 Approved, ID Columns Too Complex → RESTRUCTURE
- Problem: ID columns required "Detailed Product Description"
- Searches found companies but couldn't populate that field
- Fix: Simplify ID to just "Company Name", move description to research column
- Action: Restructure

### Example 5: 0 Approved, Topic Doesn't Exist → GIVE_UP
- Problem: User requested "AI companies that lost money in 2025 despite being profitable"
- All searches: 0 results
- Reason: Contradictory request
- Action: Give up with explanation
