## MCP Progress Tracking — Known Problem & Open Work

### The Core Problem

`wait_for_job` emits live MCP progress notifications (0–100%) while blocking on a
running job. Progress values come from the `/jobs/{id}/messages` stream, where each
message carries a `progress_percent` field representing within-phase completion.

The problem: **progress resets to 0% at the start of every new pipeline phase**, and
there are multiple phases in every run. A single `wait_for_job` call may need to span
several distinct phases before reaching a terminal state. Naively forwarding the raw
message percentage produces a bar that bounces between 0 and 100 repeatedly, which
looks broken.

---

### The Phase Geometry

A complete upload-validate-preview pipeline has three or more phases:

| Phase | Duration | Messages? |
|---|---|---|
| Upload interview (internal AI turn) | 30–90 s | None |
| Config generation | 2–5 min | None |
| Preview validation (3 rows) | 2–5 min | 0–100% |
| Full validation (post-approval) | 5–30 min | 0–100% |

For table-maker sessions, the phases are similar (table-making replaces config-gen).

The key observations:
1. **Phases 1 and 2 produce no messages at all.** The bar has nothing to display and
   sits at ~2% for potentially 5+ minutes.
2. **Phases 3 and 4 each independently count 0–100%.** Without adjustment, the bar
   resets to 0 when full validation starts after preview.
3. **The number of phases is not known in advance.** Config-match reuse skips phase 1.
   `instructions=` mode skips the interactive interview but keeps config-gen. Table-maker
   has a different intermediate step name. Future `auto_approve` would collapse the
   approval gate between phases 3 and 4.

---

### Multiple Paths Through the System

The same `wait_for_job` call is used across fundamentally different pipeline shapes:

**Path A — Config match found (fastest)**
```
create_job(config_id=...) → preview messages 0–100% → preview_complete
```
Single phase, messages from the start. Works well.

**Path B — Upload interview (standard)**
```
upload interview (silent) → config gen (silent) → preview messages → preview_complete
```
Two silent phases before any messages. Bar stays at 2% for ~5 min.

**Path C — instructions= mode (fire-and-forget)**
```
internal AI turn (silent, ~60s) → config gen (silent, ~3 min) → preview messages → preview_complete
```
Same as Path B but the silent period is unavoidable — no user interaction exists to
fill the time. The agent has no way to know how long it will take.

**Path D — Table maker (auto_start=True)**
```
wait_for_conversation (handled separately) → table-making (silent) → preview messages → preview_complete
```
`wait_for_conversation` covers the conversation phase with its own synthetic curve.
`wait_for_job` then sees an intermediate "table making" step followed by preview messages.

**Path E — Full validation (post-approval)**
```
approve_validation() → validation messages 0–100% → completed
```
Called as a fresh `wait_for_job` invocation. Works well — cursor priming discards stale
preview messages, and the new call sees validation messages from 0.

**Future Path F — auto_approve**
```
[Path B or C] → preview_complete (backend immediately auto-approves) → validation messages → completed
```
With auto_approve, the backend transitions out of `preview_complete` before the agent
has a chance to call `wait_for_job` again. A single `wait_for_job` call covering the
entire pipeline would need to treat `preview_complete` as an intermediate state (not
terminal) and apply a phase split there too. This is not yet implemented.

---

### Current Mitigation: Lazy Phase-Split

The implemented approach (`wait_for_job` in `tools/jobs.py`) uses a lazy geometric
split:

- Start with range [0, 99].
- When an intermediate phase completion is detected (status=`completed` with
  `current_step` matching "config generation", "table making", etc.), spend 80% of the
  current range on that completed phase and hand the remaining 20% to the next phase.
- Map all incoming message percentages into the current sub-range using linear scaling.
- Apply a monotonic floor (`last_emitted`) so the bar never visually goes backward.
- Cursor priming: discard the first batch of messages fetched, advancing `last_seq` to
  the current tail. Prevents stale messages from a previous phase poisoning the new
  invocation.
- De-duplication guard (`_last_intermediate_step`): a stuck status endpoint returning
  the same stale intermediate completion on every poll does not trigger repeated splits.

**What this gets right:**
- Paths A, D (table-maker), E (full validation) work well.
- The bar never goes backward.
- Multi-QC-round jitter within a phase is absorbed by `last_emitted` clamping.

**What this gets wrong:**

1. **The silent-phase problem (Paths B, C):** During the upload-interview and config-gen
   phases, no messages arrive. `msg_progress` stays at the initial value of 2.0, so the
   bar sits at ~2% for the entire silent period (3–8 minutes). Then when config-gen
   completes and the phase split fires, the bar jumps from ~2% to ~80%. This looks like
   the job was stuck, then suddenly advanced.

2. **The jump after the split:** Even with the warmup fix (below), when the split fires
   it snaps the floor to `0.8 × range`. If warmup had only advanced to, say, 40%, the
   bar jumps from 40% to 80% instantaneously. Not catastrophic but visually jarring.

3. **auto_approve not handled:** Path F (future) needs `preview_complete` treated as an
   intermediate state. The current code returns immediately at `preview_complete`. A
   separate `wait_for_job` call after approval works correctly but requires the agent to
   make two sequential calls, and guidance must tell the agent to do this.

---

### The warmup_seconds Attempt

A `warmup_seconds` parameter was added to `wait_for_job`. When set, it applies a
synthetic sqrt-curve from 0→70% over `warmup_seconds` during the pre-message phase
(while `_pf[0] < 1`, i.e., before any intermediate step has completed). Once the first
phase split fires, the warmup condition becomes false and real message tracking takes over.

For `instructions=` mode, guidance passes `warmup_seconds=300` (covering ~5 min of
silent config-gen).

**Why this is incomplete:**

- `warmup_seconds` is a magic constant that has to be chosen in advance. If config-gen
  takes 8 minutes (large complex table), the bar will hit 70% and plateau long before
  config-gen is done — which still looks stuck.
- The curve reaches 70%, then the split fires and snaps to 80%. The 10% jump is
  tolerable but still abrupt.
- The parameter has to be propagated through guidance correctly for every path. Getting
  it wrong (or omitting it on a path that needs it) means the old "stuck at 2%" behavior
  silently regresses.
- For standard interview sessions (Path B), guidance does NOT currently set
  `warmup_seconds` because the interactive Q&A fills the silent time from the user's
  perspective. But if the interview is very short, the same silent config-gen problem
  applies.

---

### What a Real Fix Would Look Like

**Option 1 — Status-based synthetic progress**

Poll the status endpoint more intelligently. When `current_step` changes from one
named phase to another (e.g., "Interview Processing" → "Config Generation" → "Preview"),
use the step name as a phase label and advance a synthetic percentage within each named
phase based on elapsed time and a per-step time budget. This requires the backend to
expose consistent `current_step` values for all phases, which it currently does not
reliably do for the silent pre-message phases.

**Option 2 — Backend-emitted phase events**

Have the backend emit a lightweight progress message at the START of each new phase
(e.g., `{type: "phase_start", phase: "config_generation", estimated_seconds: 150}`).
`wait_for_job` could use these to calibrate the warmup curve automatically without any
hardcoded constants. This is the cleanest solution but requires a backend change.

**Option 3 — Per-session phase manifest**

After `confirm_upload`, the response could include a `pipeline_phases` list with
estimated durations. `wait_for_job` would read this from a passed parameter and split
the 0–99 range proportionally across all known phases upfront rather than lazily.

**Option 4 — Separate progress tracking from completion tracking**

Accept that 0–100% progress within a phase is all that can be shown reliably. Don't
try to show overall pipeline progress — instead, emit the phase name alongside the
percentage (e.g., "Config Generation: 0%" → "Preview: 45%"). This requires MCP
progress notifications to carry a string label, which the current `ctx.report_progress`
API does not support (it only takes two numbers).

---

### Current State Summary

| Path | Progress quality | Notes |
|---|---|---|
| Config match → preview | Good | Single phase, messages from start |
| Interview → config-gen → preview | Poor (silent gap) | warmup_seconds not set for this path |
| instructions= → config-gen → preview | Partial | warmup_seconds=300 set in guidance; still jumps at split |
| Table-maker → preview | Good | Handled by phase-split on "table making" step |
| Full validation (post-approval) | Good | Fresh call, cursor priming handles reset |
| auto_approve (not implemented) | Not handled | preview_complete must become intermediate |

The `warmup_seconds` fix is a best-effort patch. A proper solution requires either
backend changes (Option 2) or a richer progress API (Option 4).
