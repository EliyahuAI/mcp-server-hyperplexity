# Next Session Startup Prompt

Use this prompt to start your next session with Claude Code:

---

## Prompt:

```
I'm continuing work on the Table Maker Independent Row Discovery system.

Current Status:
- Branch: feature/independent-row-discovery
- Local system: WORKING (4-step pipeline tested)
- Lambda integration: NOT STARTED
- Documentation: NEEDS CLEANUP

Please read these three planning documents IN ORDER:

1. docs/TABLE_MAKER_LOCAL_PROCESS.md
   - Understand the working 4-step pipeline
   - Column Definition → Row Discovery → Consolidation → QC Review

2. docs/TABLE_MAKER_LAMBDA_INTEGRATION_ROADMAP.md
   - Integration strategy (copy local components, add thin wrappers)
   - What to keep/delete from existing Lambda code
   - Phase-by-phase plan

3. docs/TABLE_MAKER_DOCUMENTATION_CLEANUP_PLAN.md
   - Documentation consolidation strategy
   - Create single TABLE_MAKER_GUIDE.md entry point
   - Archive old versions

Next Steps (in priority order):

OPTION A - Lambda Integration First:
1. Copy 5 local handlers to Lambda table_maker_lib/
2. Copy schemas and prompts
3. Create execution.py wrapper
4. Update conversation.py (minimal changes)
5. Test in dev environment

OPTION B - Documentation Cleanup First:
1. Create TABLE_MAKER_GUIDE.md (single entry point)
2. Consolidate 40 docs → 15 organized files
3. Archive old implementation notes
4. Then do Lambda integration

Which approach do you recommend, and shall we proceed?

Key Files:
- Local components: table_maker/src/*.py (5 handlers, tested, working)
- Config: table_maker/table_maker_config.json
- Tests: table_maker/test_local_e2e_*.py (validated)
```

---

## Additional Context if Needed:

**If Claude asks about current state:**
- "The local system works end-to-end and has been tested with real API calls"
- "Cost tracking, QC layer, progressive escalation all working"
- "Branch has 90+ commits, everything is committed"

**If Claude asks about Lambda:**
- "Existing Lambda has outdated preview/refinement code that needs replacing"
- "We want to use local components directly with minimal changes"
- "Just need thin wrappers for S3, WebSocket, runs DB"

**If Claude asks about priorities:**
- "Lambda integration is higher priority"
- "Documentation cleanup can happen after integration works"
- "Frontend updates come last"

---

## Expected Response

Claude should:
1. ✅ Read all three planning documents
2. ✅ Understand the 4-step pipeline
3. ✅ Propose starting with Lambda integration (Phase 1: Copy components)
4. ✅ Ask which components to copy first
5. ✅ Begin implementation

---

**Save this file and use it to start your next session!**
