# Progressive Model Escalation - Quick Reference

## What Was Implemented?

**Progressive Model Escalation** for row discovery - start with cheap/fast models and only escalate to expensive/slow ones if needed.

---

## Files Changed (LOCAL ONLY)

| File | Changes | Lines Added |
|------|---------|-------------|
| `src/row_discovery_stream.py` | Added `discover_rows_progressive()` | ~150 |
| `src/row_consolidator.py` | Added model quality ranking | ~80 |
| `src/row_discovery.py` | Added early stopping between subdomains | ~60 |
| `table_maker_config.json` | Added escalation strategy config | ~25 |
| `test_local_e2e_sequential.py` | Enhanced test output | ~50 |

**Total:** ~365 lines

---

## How It Works

### Step 1: Round-by-Round Escalation (Within Subdomain)

```
Round 1: sonar (low context)     [Fast, cheap - ~$0.001, 20s]
  ↓ If < 50% of target found
Round 2: sonar (high context)    [More thorough - ~$0.001, 30s]
  ↓ If < 75% of target found
Round 3: sonar-pro (high context) [Best quality - ~$0.003, 45s]
  ↓ Use all results
```

**Stop early if you have enough candidates!**

### Step 2: Subdomain-by-Subdomain (Between Subdomains)

```
Subdomain 1 → 8 candidates
  Check: 8 < 120% of 10 target → Continue

Subdomain 2 → 6 candidates (14 total)
  Check: 14 >= 120% of 10 target → STOP

Subdomain 3 → SKIPPED (saved time/cost!)
```

### Step 3: Consolidation with Model Preference

When duplicates found:
- **Keep:** Best quality model version
- **Merge:** All source URLs
- **Track:** Which models found it

**Quality Ranking:**
1. sonar-pro (high) → rank 5 ⭐⭐⭐⭐⭐
2. sonar-pro (low) → rank 4 ⭐⭐⭐⭐
3. sonar (high) → rank 3 ⭐⭐⭐
4. sonar (low) → rank 2 ⭐⭐
5. unknown → rank 1 ⭐

---

## Configuration

### Location: `table_maker/table_maker_config.json`

```json
{
  "row_discovery": {
    "escalation_strategy": [
      {
        "model": "sonar",
        "search_context_size": "low",
        "min_candidates_percentage": 50
      },
      {
        "model": "sonar",
        "search_context_size": "high",
        "min_candidates_percentage": 75
      },
      {
        "model": "sonar-pro",
        "search_context_size": "high",
        "min_candidates_percentage": null
      }
    ],
    "check_targets_between_subdomains": true,
    "early_stop_threshold_percentage": 120
  }
}
```

### Tuning Parameters

| Parameter | What It Does | Recommended |
|-----------|--------------|-------------|
| `min_candidates_percentage` | % of target to skip next round | 50% → 75% → null |
| `check_targets_between_subdomains` | Stop entire subdomains early | `true` |
| `early_stop_threshold_percentage` | % of total target to stop | 120% (20% buffer) |

**More aggressive:** Lower percentages (30%, 50%) = more savings, possible quality loss
**More conservative:** Higher percentages (75%, 100%) = less savings, better quality

---

## Cost & Time Savings

### Typical Scenario: 3 Subdomains, Target = 10 Rows

**Baseline (no escalation):**
- 3 × sonar-pro(high) = $0.009 + 135s

**With Progressive Escalation:**
- Subdomain 1: sonar(low) + sonar(high) = $0.002 + 50s ✓
- Subdomain 2: sonar(low) only = $0.001 + 20s ✓
- Subdomain 3: SKIPPED = $0.000 + 0s ✓
- **Total: $0.003 + 70s**

**Savings: 67% cost, 48% time** 🎉

---

## Testing

### Run the Test:
```bash
cd table_maker
python.exe test_local_e2e_sequential.py
```

### What to Look For:

✅ **Round execution logging:**
```
[INFO] Progressive escalation: 2 round(s) executed, 1 skipped
[INFO] Candidates by model: sonar(low): 6, sonar(high): 4
```

✅ **Early stopping between subdomains:**
```
[INFO] Early stop between subdomains: 17 candidates >= 12.0 threshold
```

✅ **Model quality in results:**
```
1. Anthropic (score: 0.92, quality_rank: 3)
   Model: sonar(high)
   [MERGED] Found by: sonar(low), sonar(high)
```

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| All rounds return 0 | Continues through all rounds |
| First round exceeds target | Stops after round 1 (optimal!) |
| No escalation strategy provided | Falls back to legacy mode (low → high with same model) |
| Missing model info on candidate | Gets quality rank 1 (lowest) |
| Parallel mode | Each subdomain runs progressive escalation independently |

---

## API Reference

### New Method: `discover_rows_progressive()`

```python
await stream.discover_rows_progressive(
    subdomain=subdomain,
    columns=columns,
    search_strategy=search_strategy,
    target_rows=10,
    escalation_strategy=[
        {"model": "sonar", "search_context_size": "low", "min_candidates_percentage": 50},
        {"model": "sonar", "search_context_size": "high", "min_candidates_percentage": 75},
        {"model": "sonar-pro", "search_context_size": "high", "min_candidates_percentage": null}
    ]
)
```

### Updated Method: `discover_rows()`

```python
# New parameters (all optional, backward compatible)
await discovery.discover_rows(
    search_strategy=search_strategy,
    columns=columns,
    target_row_count=20,
    escalation_strategy=escalation_strategy,           # NEW
    check_targets_between_subdomains=True,             # NEW
    early_stop_threshold_percentage=120                # NEW
)
```

### New Consolidator Method: `_get_model_quality_rank()`

```python
rank = consolidator._get_model_quality_rank(candidate)
# Returns: 1-5 based on model and context
```

---

## Quality Assurance

### What's Preserved:
- ✅ All unique candidates (no information loss)
- ✅ Better quality on duplicates (model preference)
- ✅ All source URLs (merged from all rounds)
- ✅ Transparency (track which models found what)

### What's Optimized:
- ⚡ Skip expensive rounds when possible
- ⚡ Skip entire subdomains when target reached
- ⚡ Use cheaper models first
- ⚡ Only escalate when necessary

---

## Rollback Plan

If issues found, easy rollback:

1. **Disable escalation:** Set `escalation_strategy: null` in config
2. **Falls back to legacy mode:** Two-step context escalation (low → high)
3. **No code changes needed:** Backward compatible

---

## Next Steps

### DO NOT Deploy to Lambda Yet
This is **LOCAL VERSION ONLY** for testing and validation.

### Validation Checklist:
1. [ ] Run sequential E2E test
2. [ ] Verify early stopping logs
3. [ ] Check cost savings in output
4. [ ] Validate model preference works
5. [ ] Ensure quality matches or exceeds baseline
6. [ ] Test with different thresholds

### After Validation:
1. Adjust thresholds based on results
2. Test parallel mode (max_parallel_streams > 1)
3. Document optimal configuration
4. Deploy to Lambda (separate task)

---

## Questions?

See full documentation:
- `PROGRESSIVE_ESCALATION_IMPLEMENTATION.md` - Full implementation details
- `EXAMPLE_EXECUTION.md` - Expected test output
- `docs/PROGRESSIVE_MODEL_ESCALATION_PLAN.md` - Original plan

**Implementation by:** Claude Code (Sonnet 4.5)
**Date:** October 21, 2025
