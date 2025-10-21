# Level-by-Level Escalation Architecture

**Date:** October 21, 2025
**Status:** Proposed Enhancement
**Current:** Per-subdomain escalation
**Proposed:** Level-by-level across ALL subdomains

---

## Current Architecture (Per-Subdomain)

```
Subdomain 1:
  Round 1: sonar(low) → 8 candidates → STOP (50% reached)

Subdomain 2:
  Round 1: sonar(low) → 3 candidates
  Round 2: sonar(high) → 4 candidates → STOP (75% reached)

Subdomain 3:
  Round 1: sonar(low) → 2 candidates
  Round 2: sonar(high) → 3 candidates
  Round 3: sonar-pro(high) → 3 candidates
```

**Issue:** Each subdomain escalates independently. Can't leverage findings across subdomains.

---

## Proposed Architecture (Level-by-Level)

```
LEVEL 1: Run ALL subdomains with sonar(low)
  Subdomain 1: sonar(low) → 8 candidates
  Subdomain 2: sonar(low) → 3 candidates
  Subdomain 3: sonar(low) → 2 candidates
  TOTAL: 13 candidates
  CHECK: Is 13 >= target (10)? YES → STOP

OR if not enough:

LEVEL 2: Run ONLY subdomains that had <threshold with sonar(high)
  Subdomain 2: sonar(high) → 4 candidates (now 7 total for this subdomain)
  Subdomain 3: sonar(high) → 3 candidates (now 5 total for this subdomain)
  TOTAL: 8 + 7 + 5 = 20 candidates
  CHECK: Is 20 >= target? YES → STOP

OR if still not enough:

LEVEL 3: Run remaining sparse subdomains with sonar-pro(high)
  Subdomain 3: sonar-pro(high) → 5 candidates
  TOTAL: 8 + 7 + 10 = 25 candidates
  STOP (final level)
```

---

## Benefits

### 1. **Better Resource Allocation**
- Don't waste expensive calls on subdomains already yielding good results
- Focus escalation on sparse subdomains

### 2. **Cross-Subdomain Awareness**
- Check total across ALL subdomains before escalating
- If we have enough from rich subdomains, don't escalate sparse ones

### 3. **Cost Optimization**
- Only escalate subdomains that need it
- Example: If subdomain 1 yields 10 good candidates, skip levels 2-3 for all subdomains

### 4. **Parallel Efficiency**
- Run all subdomains at same level in parallel
- Check total, then escalate together if needed
- Better parallelization strategy

---

## Implementation

### Changes to row_discovery.py

```python
async def discover_rows_level_by_level(
    subdomains, columns, search_strategy,
    target_row_count, escalation_strategy
):
    all_subdomain_results = {}  # Track cumulative results per subdomain

    for level_idx, level_strategy in enumerate(escalation_strategy, 1):
        model = level_strategy['model']
        context = level_strategy['search_context_size']

        # Determine which subdomains need this level
        subdomains_to_run = []

        for subdomain in subdomains:
            subdomain_name = subdomain['name']

            # Check if this subdomain already has enough candidates
            current_count = len(all_subdomain_results.get(subdomain_name, []))
            threshold = subdomain.get('target_rows', 10) * 0.7  # 70% of target

            if current_count < threshold:
                subdomains_to_run.append(subdomain)

        if not subdomains_to_run:
            logger.info(f"Level {level_idx}: All subdomains have sufficient candidates, skipping")
            break

        logger.info(f"Level {level_idx}: Running {len(subdomains_to_run)} subdomain(s) with {model}({context})")

        # Run these subdomains in PARALLEL at this level
        level_results = await run_parallel_at_level(
            subdomains_to_run, model, context, columns, search_strategy
        )

        # Accumulate results
        for result in level_results:
            subdomain_name = result['subdomain']
            if subdomain_name not in all_subdomain_results:
                all_subdomain_results[subdomain_name] = []
            all_subdomain_results[subdomain_name].extend(result['candidates'])

        # Check if we have enough TOTAL candidates across all subdomains
        total_candidates = sum(len(cands) for cands in all_subdomain_results.values())

        if total_candidates >= target_row_count * 1.2:  # 20% buffer
            logger.info(
                f"Level {level_idx}: Reached {total_candidates} total candidates "
                f"(target: {target_row_count}). Stopping escalation."
            )
            break

    return all_subdomain_results
```

---

## Configuration

```json
{
  "row_discovery": {
    "escalation_mode": "level_by_level",  // NEW: vs "per_subdomain"
    "escalation_strategy": [
      {
        "model": "sonar",
        "search_context_size": "low",
        "check_threshold_percentage": 120  // Stop if total >= 120% of target
      },
      {
        "model": "sonar",
        "search_context_size": "high",
        "check_threshold_percentage": 120
      },
      {
        "model": "sonar-pro",
        "search_context_size": "high",
        "check_threshold_percentage": null  // Final level always runs
      }
    ],
    "subdomain_threshold_percentage": 70  // Skip subdomain if >= 70% of its target
  }
}
```

---

## Example Execution

**Scenario:** 3 subdomains, target = 10 rows total

```
LEVEL 1: sonar(low) - ALL subdomains in parallel
  - Subdomain 1 (Research): 8 candidates
  - Subdomain 2 (Healthcare): 3 candidates
  - Subdomain 3 (Enterprise): 2 candidates
  TOTAL: 13 candidates >= 12 (120% of 10) → STOP

Skipped: Level 2 and 3 entirely
Cost savings: 2 levels × 3 subdomains = 6 API calls saved
```

**vs Current:**
```
Subdomain 1: 1 call (stopped early)
Subdomain 2: 2 calls
Subdomain 3: 3 calls
Total: 6 calls
```

**New is SAME calls but better distribution!**

---

## Estimated Implementation

- `row_discovery.py`: +150 lines (level-by-level orchestration)
- Config updates: +20 lines
- Test updates: +30 lines

**Time:** ~2 hours

---

**Should we implement this level-by-level approach?**

It's a cleaner architecture that manages threads better and checks progress after each level across ALL subdomains.
