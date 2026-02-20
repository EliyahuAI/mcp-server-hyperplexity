# Implementation Plan: Dynamic Row & Column Addition

## Context

The starting Excel is static — rows and columns are fixed at upload. Config generation/refinement only controls *how* existing columns are validated. This plan adds two structural capabilities:

1. **Column Addition** (early priority): Let users add new columns during config refinement. Costly because it requires full re-validation across all rows + QC re-run.
2. **Row Addition** (post-validation flow): After a full validation completes, offer to discover and add more entities like the ones already in the table. Charged only for the new rows.

Both features use the **fork model**: original session is never mutated. Changes go into a new session ID that copies Excel + config + agent_memory from the source.

---

## Feature 1: Column Addition (Config Refinement Flow)

### User Flow
1. User is in config refinement and says "add a column for X".
2. System recognizes column-add intent and warns: "Adding a column requires re-validation of all N rows and a QC re-run. Estimated cost: $Y."
3. User confirms.
4. System forks to a new session ID.
5. AI generates the new `validation_target` definition for column X.
6. New column header added to forked Excel (empty cells).
7. Validation runs on all existing rows for the **new column only**.
8. QC re-runs on the **entire table** (QC reviews holistically — can't skip it).
9. Results merged into the forked Excel alongside existing validated columns.
10. New session presented as a new study version with provenance: "Based on [original session], added column X."

### Cost Model
- Charge: `N_rows × per_row_cost_for_new_column + QC_re_run_cost`
- QC re-run is unavoidable (QC reviews the whole table, not individual columns).
- Quote this to the user before they confirm, same as a standard validation quote.

### Key Design Decisions
- **Fork always**: Never mutate the source session. If column addition fails, original is safe.
- **New column validation only**: Don't re-run validation for existing columns — they're already done.
- **Full QC re-run**: QC must see the full enriched table including the new column. No shortcut here.
- **Formula columns**: If the new column is derived (Excel formula), skip validation — mark as `formula_info` in config, same as existing formula detection.
- **agent_memory preserved**: Copy `agent_memory.json` to forked session so AI has full context of why the table was designed as it is.

### Files to Modify / Create
| File | Change |
|------|--------|
| `src/lambdas/interface/actions/create_update_session.py` | Add `structural_fork()` function — forks session + applies structural changes |
| `src/lambdas/interface/actions/copy_config.py` | Already has `copy_agent_memory()` — reuse as-is |
| `src/lambdas/interface/actions/generate_config.py` | Detect column-add intent; generate new `validation_target`; trigger fork |
| `src/lambdas/interface/core/unified_s3_manager.py` | Add column header to forked Excel before validation |
| `src/lambdas/validation/lambda_function.py` | Support `columns_to_validate` filter — validate only specific columns |
| `src/lambdas/interface/actions/start_preview.py` | Quote column-add cost before user confirms |

---

## Feature 2: Row Addition (Post-Validation Flow)

### User Flow
1. Full validation completes. Results Excel is ready.
2. System auto-generates an **entity description** from the validated table:
   - Analyzes ID columns + sample of existing rows (e.g., first 10)
   - Produces: "Your table contains 47 publicly traded U.S. biotech companies with $100M+ market cap..."
3. UI presents: "Would you like to add more entities like these?"
4. If yes:
   - User can refine the description or add criteria ("also include European companies").
   - Row discovery runs using existing `row_discovery.py` pipeline.
   - Deduplication against existing rows using `row_consolidator.py` (extended to check existing Excel rows, not just within-discovery rows).
   - QC review of **new rows only**.
5. Preview of discovered rows shown (N candidates found, M after dedup and QC).
6. Offer: "Add X rows. Validation at your preview rate ($Z/row). Total: $W."
   - The per-row price is the same as the last preview session's per-row rate — user already knows this price.
7. User approves → validation runs on **new rows only** across all columns.
8. New rows appended to forked Excel. Results merged.
9. Forked session presented: "Based on [original session], added N rows."

### Key Design Decisions
- **Post-validation only**: Row addition is not offered mid-flow. Only surfaces after full validation completes.
- **Entity description as row requirements**: The auto-generated description + existing rows serve as the row discovery guidance. This solves the "no explicit row requirements" problem without needing the original Table Maker conversation.
- **User can refine description**: If the auto-description is wrong ("actually we only want private companies"), user corrects it before discovery runs.
- **Validate new rows only**: Existing validated rows are not re-processed. Only the N new rows go through the validation pipeline.
- **No QC re-run on existing rows**: QC runs on new rows only. The full-table QC already happened during original validation.
- **Pricing**: Per-row rate from the last completed preview. Not a new quote — locks in the known rate.
- **Fork model**: Append to a new session. Original validated session is preserved.

### Row Discovery Guidance Construction
Since this table may not have Table Maker conversation history (e.g., was a user-uploaded Excel), the system infers guidance from:
1. ID column names and sample values → entity type
2. Column definitions in config (search_groups, subdomains) → search strategy
3. Existing rows sample → quality/format examples
4. User-refined entity description → explicit intent

This is fed into the existing `row_discovery.py` pipeline as `discovery_guidance` (same field Table Maker uses).

### Files to Modify / Create
| File | Change |
|------|--------|
| `src/lambdas/interface/actions/table_maker/row_discovery.py` | Reuse as-is; accepts `discovery_guidance` + existing rows for context |
| `src/lambdas/interface/actions/table_maker/row_consolidator.py` | Extend deduplication to check against existing Excel rows (not just within-discovery) |
| `src/lambdas/interface/actions/discover_rows.py` | New action — orchestrates entity description → discovery → dedup → QC |
| `src/lambdas/interface/actions/create_update_session.py` | Reuse `structural_fork()` from Feature 1 |
| `src/lambdas/validation/lambda_function.py` | Support `rows_to_validate` filter — validate only newly added rows |
| `src/lambdas/interface/handlers/api_handler.py` | New endpoint: `POST /discover-rows` to trigger post-validation row addition |
| Frontend | Post-validation "Add more rows?" prompt with entity description display + refinement |

---

## Shared Infrastructure: Fork Model

Both features rely on forking. This should be built once cleanly.

### `structural_fork()` function
```
Input:
  source_session_id
  fork_type: "column_addition" | "row_addition"
  modifications: { new_columns?, new_rows? }

Steps:
  1. Copy Excel from source session to new session ID
  2. Copy config (latest version) to new session
  3. Copy agent_memory.json to new session (preserves AI context)
  4. Apply structural modifications to copies:
     - column_addition: add empty column headers to Excel + validation_target to config
     - row_addition: append new rows to Excel (ID columns only, research columns empty)
  5. Write session_info.json for new session with provenance:
     { "forked_from": source_session_id, "fork_type": "...", "fork_reason": "..." }
  6. Return new session ID
```

---

## Sequencing / Build Order

1. **Build `structural_fork()`** in `create_update_session.py` — shared by both features.
2. **Build column-add validation filter** in validation lambda (`columns_to_validate` param).
3. **Build row-add validation filter** in validation lambda (`rows_to_validate` param).
4. **Wire up column addition** in config refinement flow — detect intent, quote cost, fork, validate, present.
5. **Extend `row_consolidator.py`** to deduplicate against existing Excel rows.
6. **Build `discover_rows.py`** action — entity description generation + discovery orchestration.
7. **Wire up row addition** to post-validation completion — surface prompt, run discovery, quote, validate, merge.
8. **Frontend** for both: column-add warning/confirmation, and post-validation row-add prompt.

---

## Verification

**Column Addition:**
1. Upload Excel with N rows → generate config → refine with "add column for headquarters city."
2. Verify: new session created, new column header in forked Excel, new `validation_target` in forked config, validation runs only for the new column, QC re-runs, results merged.
3. Verify: original session Excel unchanged.
4. Verify: quoted cost = N rows × new column rate + QC cost.

**Row Addition:**
1. Run full validation on Excel → verify post-validation prompt appears with entity description.
2. Approve row addition → verify discovery runs, deduplication excludes existing rows, new rows added to forked Excel only.
3. Confirm validation runs only on new rows (not re-running existing rows).
4. Verify per-row price matches last preview rate.
5. Verify original validated session unchanged.
