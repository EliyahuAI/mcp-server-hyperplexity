# Table Maker Documentation - Cleanup Plan

**Date:** October 21, 2025
**Goal:** One clear guide + organized detailed docs, archive old versions

---

## Current Documentation Chaos

**Main directory has:**
- TABLE_MAKER_IMPLEMENTATION_COMPLETE.md (outdated, preview/refinement model)
- INDEPENDENT_ROW_DISCOVERY_IMPLEMENTATION_SUMMARY.md
- ARCHITECTURE_REVISIONS_COMPLETE.md
- FINAL_SESSION_SUMMARY.md
- FINAL_STATUS.md
- READY_TO_TEST.md
- SESSION_SUMMARY_AND_NEXT_STEPS.md
- And 10+ more...

**docs/ directory has:**
- Multiple implementation guides
- Multiple architecture plans
- Migration guides for old systems
- Component summaries
- And 15+ more...

**Problem:** Hard to find anything, duplicated information, no clear entry point

---

## Proposed Structure

```
docs/
├── TABLE_MAKER_GUIDE.md                    ← SINGLE ENTRY POINT
│   (Concise, 5-10 pages, covers everything at high level)
│
├── table_maker/                            ← DETAILED REFERENCE
│   ├── architecture/
│   │   ├── overview.md                     (4-step pipeline)
│   │   ├── column_definition.md            (Step 1 details)
│   │   ├── row_discovery.md                (Step 2 details)
│   │   ├── consolidation.md                (Step 3 details)
│   │   └── qc_review.md                    (Step 4 details)
│   │
│   ├── components/
│   │   ├── column_definition_handler.md
│   │   ├── row_discovery_stream.md
│   │   ├── row_consolidator.md
│   │   ├── row_discovery_orchestrator.md
│   │   └── qc_reviewer.md
│   │
│   ├── configuration/
│   │   ├── config_reference.md             (All settings explained)
│   │   ├── escalation_strategy.md
│   │   └── prompts_and_schemas.md
│   │
│   ├── deployment/
│   │   ├── local_testing.md
│   │   ├── lambda_integration.md
│   │   └── troubleshooting.md
│   │
│   └── api_reference/
│       ├── handlers.md                     (All handler signatures)
│       ├── data_structures.md
│       └── websocket_messages.md
│
└── archive/                                ← OLD VERSIONS
    ├── preview_refinement_architecture.md
    ├── old_implementation_complete.md
    ├── agent_summaries/                   (All agent reports)
    └── session_notes/                     (Development notes)
```

---

## New TABLE_MAKER_GUIDE.md (Single Entry Point)

**Structure (5-10 pages):**

### 1. Quick Start (1 page)
- What it does
- 30-second overview
- How to run local test
- Expected results

### 2. Architecture Overview (1 page)
- 4-step pipeline diagram
- Input/Output of each step
- Data flow

### 3. Components (1 page)
- 5 core handlers (one paragraph each)
- What each does
- Links to detailed docs

### 4. Configuration (1 page)
- Key settings explained
- Escalation strategy
- QC thresholds
- When to tune what

### 5. Local Testing (1 page)
- Running tests
- Interpreting results
- View prompts
- Cost analysis

### 6. Lambda Integration (1 page)
- How it integrates
- WebSocket flow
- S3 storage
- Runs database

### 7. Frontend Integration (1 page)
- WebSocket messages
- User flow
- Display components

### 8. Troubleshooting (1 page)
- Common issues
- Debug logging
- Cost optimization

### 9. Next Steps (1 page)
- Planned enhancements
- Known limitations
- Improvement roadmap

---

## Content to Consolidate

### From Multiple Session Summaries → Single Architecture Overview
**Consolidate:**
- INDEPENDENT_ROW_DISCOVERY_IMPLEMENTATION_SUMMARY.md
- ARCHITECTURE_REVISIONS_COMPLETE.md
- FINAL_SESSION_SUMMARY.md
- FINAL_STATUS.md

**Into:**
- `docs/table_maker/architecture/overview.md` (definitive architecture doc)

### From Implementation Details → Component Docs
**Consolidate:**
- Individual agent summaries
- Component implementation notes
- Technical details

**Into:**
- `docs/table_maker/components/*.md` (one file per component)

### From Test Instructions → Deployment Guide
**Consolidate:**
- READY_TO_TEST.md
- Local testing guides
- Setup instructions

**Into:**
- `docs/table_maker/deployment/local_testing.md`

---

## Content to Archive

**Move to `docs/archive/`:**

**Old Architecture:**
- TABLE_MAKER_IMPLEMENTATION_COMPLETE.md (outdated preview/refinement)
- Preview generation docs
- Refinement loop docs
- Old data flow diagrams

**Development Notes:**
- SESSION_SUMMARY_AND_NEXT_STEPS.md
- IMPLEMENTATION_STATUS_AND_NEXT_STEPS.md
- All agent summary files (Agent 1, Agent 2, etc.)
- WIP documents
- Revision plans already implemented

**Migration Guides:**
- MIGRATION_GUIDE_ROW_DISCOVERY.md (after everyone migrated)

**Plans (after implementation):**
- PROGRESSIVE_MODEL_ESCALATION_PLAN.md → Implemented, archive
- QC_LAYER_AND_ENHANCEMENTS_PLAN.md → Implemented, archive

**Plans (keep for future):**
- GLOBAL_COUNTER_AND_EXCLUSION_PLAN.md (not implemented yet)
- LEVEL_BY_LEVEL_ESCALATION_PLAN.md (not implemented yet)

---

## Content to DELETE

**Completely remove:**
- Duplicate/redundant summaries
- Test output examples (actual test JSONs are enough)
- Obsolete implementation notes
- Scratch/WIP documents with no useful info

---

## Implementation Steps

### Step 1: Create New Structure (2 hours)
1. Create folder structure in docs/table_maker/
2. Write TABLE_MAKER_GUIDE.md (single entry point)
3. Consolidate architecture docs into overview.md
4. Create component docs (extract from summaries)

### Step 2: Archive Old Docs (30 min)
1. Create docs/archive/
2. Move old architecture docs
3. Move implementation session notes
4. Move agent summaries

### Step 3: Update README (30 min)
1. Point to TABLE_MAKER_GUIDE.md
2. Remove outdated info
3. Add quick links to key docs

### Step 4: Cleanup (30 min)
1. Delete truly redundant files
2. Verify all links work
3. Test documentation flow (can someone understand it?)

**Total Time:** ~3.5 hours

---

## Success Criteria

After cleanup:

✅ **New user can find everything in <5 minutes**
- Reads TABLE_MAKER_GUIDE.md
- Understands system
- Knows how to run it
- Knows where to find details

✅ **No duplicate information**
- Each concept explained once
- Cross-references for details
- Clear hierarchy

✅ **Clear entry points**
- TABLE_MAKER_GUIDE.md for users
- docs/table_maker/ for deep dives
- archive/ for history

✅ **Easy to maintain**
- Update one place, not five
- Clear ownership of each doc
- Dated and versioned

---

## Documentation Files Count

**Before:** ~40 markdown files scattered
**After:** ~15 organized files + archive

**Reduction:** 60% fewer files, 100% clearer structure

---

**Execute this cleanup AFTER Lambda integration is working, before production deployment.**
