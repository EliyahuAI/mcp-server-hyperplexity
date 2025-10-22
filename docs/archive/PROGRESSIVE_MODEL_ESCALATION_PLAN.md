# Progressive Model Escalation - Implementation Plan

**Date:** October 21, 2025
**Purpose:** Optimize row discovery with intelligent model/context escalation

---

## Requirements

### 1. Progressive Escalation Strategy
```
Round 1: sonar (low context)     - Fast, cheap
  ↓ Check if target reached
Round 2: sonar (high context)    - More thorough
  ↓ Check if target reached
Round 3: sonar-pro (high context) - Most comprehensive
  ↓ Use all results
```

**Key:** Stop early if we already have enough candidates

### 2. Configuration Structure
```json
{
  "row_discovery": {
    "escalation_strategy": [
      {
        "model": "sonar",
        "search_context_size": "low",
        "min_candidates_to_skip": "50%"
      },
      {
        "model": "sonar",
        "search_context_size": "high",
        "min_candidates_to_skip": "75%"
      },
      {
        "model": "sonar-pro",
        "search_context_size": "high",
        "min_candidates_to_skip": null
      }
    ]
  }
}
```

### 3. Consolidation Rules

**On duplicate entities:**
- Prefer output from later rounds (sonar-pro > sonar-high > sonar-low)
- Merge source_urls from all rounds
- Track which model/round found the entity
- Keep model_quality_rank for transparency

**On unique entities:**
- Keep from ALL rounds (don't discard sonar results)
- Track source model/context

---

## Implementation Changes

### File 1: row_discovery_stream.py

**Current:** Single call with one model
```python
async def discover_rows(subdomain, columns, ..., scoring_model='sonar-pro'):
    result = await call_api(model=scoring_model, context='low')
    if insufficient:
        result = await call_api(model=scoring_model, context='high')
    return result
```

**New:** Multiple attempts with escalation
```python
async def discover_rows_progressive(
    subdomain, columns, ...,
    escalation_strategy: List[Dict]
):
    all_attempts = []

    for round_idx, strategy in enumerate(escalation_strategy):
        model = strategy['model']
        context = strategy['search_context_size']
        min_to_skip = strategy.get('min_candidates_to_skip')

        # Execute this round
        result = await call_api(model=model, context=context)
        result['model_used'] = model
        result['context_used'] = context
        result['round'] = round_idx + 1
        all_attempts.append(result)

        # Check if we can skip remaining rounds
        total_so_far = sum(len(a['candidates']) for a in all_attempts)
        if min_to_skip and total_so_far >= calculate_threshold(target, min_to_skip):
            logger.info(f"Round {round_idx+1}: Reached {total_so_far} candidates, skipping remaining rounds")
            break

    # Merge all attempts
    return merge_progressive_results(all_attempts)
```

### File 2: row_consolidator.py

**Add:** Model preference ranking
```python
def _merge_duplicates_with_model_preference(
    group: List[Dict]
) -> Dict:
    """
    Merge duplicate entities, preferring later models.

    Ranking: sonar-pro (high) > sonar (high) > sonar (low)
    """
    # Sort by model quality (round number as proxy)
    sorted_group = sorted(group, key=lambda x: x.get('round', 0), reverse=True)

    # Take best (highest round)
    best = sorted_group[0].copy()

    # Merge source_urls from all
    all_urls = []
    for candidate in group:
        all_urls.extend(candidate.get('source_urls', []))
    best['source_urls'] = list(set(all_urls))

    # Track which models found this
    best['found_by_models'] = [
        f"{c.get('model_used', 'unknown')}({c.get('context_used', 'unknown')})"
        for c in group
    ]
    best['model_quality_rank'] = sorted_group[0].get('round', 0)

    return best
```

### File 3: row_discovery.py

**Add:** Target checking between subdomains
```python
# After each subdomain completes
accumulated_candidates = collect_all_from_completed_streams(results_so_far)
unique_count = estimate_unique_count(accumulated_candidates)

if unique_count >= target_row_count * 1.2:  # 20% buffer
    logger.info(f"Reached {unique_count} candidates (target: {target_row_count}), stopping early")
    # Skip remaining subdomains
    break
```

### File 4: Configuration

**table_maker_config.json:**
```json
{
  "row_discovery": {
    "escalation_strategy": [
      {
        "model": "sonar",
        "search_context_size": "low",
        "description": "Fast initial search",
        "min_candidates_to_skip_percentage": 50,
        "skip_if_total_reaches": null
      },
      {
        "model": "sonar",
        "search_context_size": "high",
        "description": "More thorough search",
        "min_candidates_to_skip_percentage": 75,
        "skip_if_total_reaches": null
      },
      {
        "model": "sonar-pro",
        "search_context_size": "high",
        "description": "Most comprehensive search",
        "min_candidates_to_skip_percentage": null,
        "skip_if_total_reaches": null
      }
    ],
    "check_targets_between_subdomains": true,
    "early_stop_threshold_percentage": 120
  }
}
```

---

## Example Execution Flow

### Scenario: 3 subdomains, target_row_count=20

```
Subdomain 1: "AI Research"
  Round 1: sonar (low) → 8 candidates
    Check: 8 < 50% of 10 target for this subdomain → Continue
  Round 2: sonar (high) → 6 candidates (14 total from this subdomain)
    Check: 14 >= 75% of 10 target → Skip Round 3
  Subdomain 1 complete: 14 candidates

Check between subdomains: 14 < 120% of 20 total target → Continue

Subdomain 2: "Healthcare AI"
  Round 1: sonar (low) → 12 candidates
    Check: 12 >= 50% of 10 target → Skip Rounds 2-3
  Subdomain 2 complete: 12 candidates

Check between subdomains: 14 + 12 = 26 >= 120% of 20 → STOP EARLY
Skip Subdomain 3

Consolidation:
  Total: 26 candidates from 2 subdomains (skipped 1)
  Merge duplicates (prefer sonar-high from subdomain 2)
  Filter by score
  Return top 20
```

**Result:** Found enough without processing all subdomains or all rounds!

---

## Benefits

1. **Cost Optimization:**
   - sonar (low): ~$1/MTok
   - sonar (high): ~$1/MTok (same cost, more context)
   - sonar-pro (high): ~$3/MTok
   - Skip expensive rounds when possible

2. **Time Optimization:**
   - sonar (low): ~20-30s
   - sonar (high): ~30-45s
   - sonar-pro (high): ~45-60s
   - Skip slow rounds when possible

3. **Quality:**
   - Prefer better models when available
   - But keep unique finds from cheaper models

4. **Flexibility:**
   - Fully configurable strategy
   - Can add/remove rounds
   - Can adjust thresholds

---

## Estimated Changes

- row_discovery_stream.py: +100 lines
- row_consolidator.py: +60 lines
- row_discovery.py: +80 lines
- config files: +30 lines
- tests: +50 lines

**Total:** ~320 lines of new code

**Time:** ~1-1.5 hours to implement and test

---

**Approve this plan?**
