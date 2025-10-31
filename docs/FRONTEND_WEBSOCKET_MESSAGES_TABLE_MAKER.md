# Table Maker WebSocket Messages - Frontend Integration Guide

**Version:** 2.5 (Background Research Phase)
**Last Updated:** October 31, 2025

## Overview

This document describes the WebSocket messages sent by the Table Maker system for frontend integration, including the new background research phase (Step 0) and autonomous recovery flow.

---

## New in Version 2.5

### Background Research Phase (Step 0 - Internal)

**What Changed:** Table generation now has an internal Step 0 that finds authoritative sources and starting tables BEFORE defining columns.

**Frontend Impact:**
- Total steps remains 4 (user-visible)
- Step 0 runs internally (progress 0% → 25%)
- Step 1 (Column Definition) now starts at 25% instead of 5%

**Progress Sequence:**
```
0% - "Starting table generation"
5% - "Researching domain and finding authoritative sources..." (Step 0)
25% - "Background research complete" (Step 0 done)
30% - "Defining columns and search strategy" (Step 1 starts)
40% - "Column definition complete" (Step 1 done)
[Continue with Steps 2-4 as before]
```

**On Restructure:**
```
0% - "Restructuring table..."
10% - "Using cached domain research (restructure mode)" (Step 0 skipped)
30% - "Defining columns with simpler structure" (Step 1 starts)
[Continue...]
```

**New WebSocket Fields:**
```json
{
  "type": "table_execution_update",
  "current_step": 0,  // Step 0 = internal research phase
  "total_steps": 4,   // Still 4 user-visible steps
  "status": "Researching domain...",
  "progress_percent": 5,
  "research_sources_count": 3,      // NEW - number of authoritative sources found
  "starting_tables_count": 2        // NEW - number of starting tables found
}
```

---

## New Messages in Version 2.4

### 1. `table_execution_restructure`

**When:** QC determines 0 rows found but the request is RECOVERABLE through restructuring

**Purpose:** AI autonomously restructures the table and retries execution

**Payload:**
```json
{
  "type": "table_execution_restructure",
  "conversation_id": "conv_123",
  "phase": "restructure",
  "status": "Restructuring table automatically...",
  "user_facing_message": "I found that the table structure was too specific. I'm restructuring it with simpler columns and broader criteria. Retrying discovery now...",
  "autonomous_restructure": true,
  "clear_previous_state": true,
  "restructuring_guidance": {
    "column_changes": "Simplify ID columns to only Company Name and Website...",
    "requirement_changes": "Make funding status a soft requirement...",
    "search_broadening": "Include also digital health companies..."
  },
  "search_improvements": [
    "Use aggregator sites like Crunchbase instead of individual articles",
    "Focus on company directories rather than news mentions"
  ],
  "qc_reasoning": "The entities exist but ID columns were too specific for web search discovery"
}
```

**Frontend Action:**
1. **CLEAR previous execution state**:
   - Remove any displayed columns (ID/Research boxes)
   - Remove any displayed discovered rows
   - Clear progress from previous attempt
2. **Show restructure notice**:
   - Display `user_facing_message` prominently
   - Show as progress, not error (e.g., blue info banner)
3. **Reset to Step 0**:
   - Progress bar back to 0%
   - Status: "Restructuring table..."
4. **Show detailed feedback (optional)**:
   - Display `restructuring_guidance` in expandable section
   - Show `search_improvements` learned from previous attempt
   - Show `qc_reasoning` for transparency
5. **Wait for new execution messages**:
   - System will send new `table_execution_update` starting from Step 1
   - Treat as fresh execution flow
   - Config generation from previous attempt has been cancelled

---

### 2. `table_execution_unrecoverable`

**When:** QC determines 0 rows found and the request is fundamentally IMPOSSIBLE

**Purpose:** AI gives up and apologizes, frontend shows new table card

**Payload:**
```json
{
  "type": "table_execution_unrecoverable",
  "conversation_id": "conv_123",
  "phase": "failed",
  "status": "Unable to discover rows",
  "fundamental_problem": "This topic requires proprietary company data that isn't publicly available via web search.",
  "user_facing_apology": "I apologize, but I wasn't able to find any rows for this table. This type of information requires proprietary company data that isn't publicly available through web searches. Unfortunately, I can't discover this information. Would you like to try a different table topic?",
  "show_new_table_card": true
}
```

**Frontend Action:**
1. Hide progress indicator
2. Show `user_facing_apology` message (friendly, non-technical)
3. **Display "Get Started" card** to allow user to create a new table
4. Mark current conversation as closed/failed
5. Optional: Show button "Try a Different Table"

---

## Existing Messages (Reference)

### `table_conversation_update`

Interview phase updates (user and AI exchanging messages)

### `table_execution_update`

Execution phase progress (Step X/4, subdomain progress, etc.)

### `table_execution_complete`

Successful completion with rows discovered

### `table_execution_error`

General execution errors (non-zero-row failures)

---

## Complete Flow Diagram

```
User Request → Interview → Execution → QC Review
                                           ↓
                                    0 Rows Approved?
                                           ↓
                        ┌──────────────────┴──────────────────┐
                        NO                                    YES
                        ↓                                      ↓
              table_execution_complete              QC Makes Autonomous Decision
              (Success with rows)                              ↓
                                          ┌────────────────────┴────────────────────┐
                                     RECOVERABLE                              UNRECOVERABLE
                                          ↓                                        ↓
                          table_execution_restructure              table_execution_unrecoverable
                          - Show progress                          - Show apology
                          - System restarts from                   - Show "Get Started" card
                            column definition                      - Conversation ends
                          - Retries execution
                                   ↓
                          (Loop back to Execution)
```

---

## Frontend Implementation Checklist

### For `table_execution_restructure`:
- [ ] Listen for `type === 'table_execution_restructure'`
- [ ] Display `user_facing_message` as progress update
- [ ] Keep progress indicator visible
- [ ] DO NOT show error state
- [ ] Wait for subsequent messages (column definition → execution → completion)

### For `table_execution_unrecoverable`:
- [ ] Listen for `type === 'table_execution_unrecoverable'`
- [ ] Hide progress indicator
- [ ] Display `user_facing_apology` in error container (friendly styling, not alarming)
- [ ] Show "Get Started" card or "Try Different Table" button
- [ ] Mark conversation as failed/closed
- [ ] Clear any pending table state

---

## Example Frontend Code (Pseudocode)

```javascript
websocket.on('message', (message) => {
  const data = JSON.parse(message);

  switch(data.type) {
    case 'table_execution_restructure':
      // Show restructuring progress
      showProgressMessage(data.user_facing_message);
      // Keep spinner visible, don't show error
      break;

    case 'table_execution_unrecoverable':
      // Hide progress
      hideProgressSpinner();

      // Show friendly apology
      showApologyMessage(data.user_facing_apology);

      // Show new table card
      if (data.show_new_table_card) {
        showGetStartedCard();
      }

      // Mark conversation as done
      markConversationFailed(data.conversation_id);
      break;

    case 'table_execution_complete':
      // Existing success handler
      showTableResults(data);
      break;
  }
});
```

---

## User Experience

### Recoverable Scenario:
```
User: "Track companies developing fusion energy"
[Discovery finds 0 rows]
QC: "This is discoverable but our ID columns were too strict"
Frontend: Shows "Restructuring table with simpler columns. Retrying..."
[System restarts with better structure]
Frontend: Shows normal execution progress
Result: 8 companies found with simplified structure
```

### Unrecoverable Scenario:
```
User: "Track internal R&D projects at OpenAI"
[Discovery finds 0 rows]
QC: "This requires proprietary internal data"
Frontend: Shows apology: "I apologize, but this information requires proprietary data that isn't publicly available. Would you like to try a different table topic?"
Frontend: Shows "Get Started" card for new table
User: Clicks "Get Started" and creates different table
```

---

## Notes for Frontend Developers

1. **No User Input Required**: In v2.4, the AI makes the recovery decision autonomously. User doesn't need to respond or choose options.

2. **Restructure is Transparent**: When restructuring happens, show it as progress (not an error). The user should feel like the system is working hard, not failing.

3. **Apology is Final**: When `show_new_table_card: true`, the conversation is over. Don't allow user to continue this conversation.

4. **Friendly Language**: Both messages use friendly, non-technical language. No mentions of "QC", "subdomains", "escalation", etc.

5. **TODO**: Restructure flow currently logs guidance but doesn't trigger column regeneration. This will be implemented to complete the loop.

---

## Questions?

Contact: Table Maker development team
See also: `docs/TABLE_MAKER_GUIDE.md` for full system documentation
