# Global Counter and Row Exclusion - Implementation Plan

**Date:** October 21, 2025
**Purpose:** Optimize discovery by tracking total and excluding duplicates upfront

---

## Two Improvements

### 1. Global Counter Before Escalation

**Current:**
```
Subdomain 1, Round 1: sonar(low) → 8 candidates
  Check: 8 >= 50% of subdomain target? YES → Stop this subdomain
Subdomain 2, Round 1: sonar(low) → 3 candidates
  Check: 3 >= 50% of subdomain target? NO → Continue to Round 2
```

**Issue:** We don't check TOTAL count before escalating

**Proposed:**
```
ALL Subdomains, Round 1: sonar(low)
  Sub 1 → 8 candidates
  Sub 2 → 3 candidates
  Sub 3 → 2 candidates
  GLOBAL CHECK: Total = 13 >= target (10)? YES → STOP ALL ESCALATION

(Skip Round 2 and 3 entirely for all subdomains)
```

**Implementation:**
```python
# After completing level 1 for all subdomains
total_accumulated = sum(len(result['candidates']) for result in all_level_results)

if total_accumulated >= target_row_count * 1.2:  # 20% buffer
    logger.info(f"Global check: {total_accumulated} >= {target_row_count * 1.2}, stopping all escalation")
    break  # Don't run next level for ANY subdomain
```

---

### 2. Exclude Already-Found Rows

**Current:**
```
Subdomain 1: Finds "OpenAI", "Anthropic", "DeepMind"
Subdomain 2: Might also find "OpenAI" (duplicate)
  → Later removed in deduplication step
```

**Issue:** Wastes API calls finding the same entities again

**Proposed:**
```
Subdomain 1: Finds "OpenAI", "Anthropic", "DeepMind"
  EXCLUSION LIST: ["OpenAI", "Anthropic", "DeepMind"]

Subdomain 2 Prompt:
  "Find healthcare AI companies.
   EXCLUDE (already found): OpenAI, Anthropic, DeepMind
   Do NOT include these in your output."
```

**Implementation:**

#### Update Prompt Template
```markdown
## Already Discovered (EXCLUDE)

{{EXCLUSION_LIST}}

**CRITICAL:** Do NOT include any of the entities listed above in your output.
We have already found these entities in other subdomains.
Focus on finding NEW, UNIQUE entities not in the exclusion list.
```

#### Update row_discovery.py
```python
accumulated_entities = set()  # Track all found entities

for subdomain in subdomains:
    # Build exclusion list from all previously found entities
    exclusion_list = build_exclusion_list(accumulated_entities, id_columns)

    # Pass exclusion list to discovery
    result = await discover_subdomain(subdomain, exclusion_list=exclusion_list)

    # Add new entities to accumulated set
    for candidate in result['candidates']:
        entity_id = extract_entity_identifier(candidate, id_columns)
        accumulated_entities.add(entity_id)
```

#### Exclusion List Format
```python
def build_exclusion_list(accumulated_entities, id_columns):
    """Format exclusion list for prompt."""
    if not accumulated_entities:
        return "None - this is the first subdomain"

    lines = []
    for entity in accumulated_entities:
        # Format as human-readable
        lines.append(f"- {entity}")

    return f"The following entities have already been found:\n" + '\n'.join(lines)
```

**Example:**
```
## Already Discovered (EXCLUDE)

The following entities have already been found:
- OpenAI (https://openai.com)
- Anthropic (https://anthropic.com)
- DeepMind (https://deepmind.com)

Do NOT include these in your output.
```

---

## Combined Architecture

```
LEVEL 1: All subdomains with sonar(low)
  Subdomain 1: sonar(low), no exclusions → 8 candidates
    Exclusion list for next: OpenAI, Anthropic, ...

  Subdomain 2: sonar(low), exclude [8 from Sub1] → 3 NEW candidates
    Exclusion list for next: OpenAI, Anthropic, ..., PathAI, ...

  Subdomain 3: sonar(low), exclude [11 from Sub1+2] → 2 NEW candidates

  GLOBAL CHECK: Total = 13 candidates >= 12 (target 10 × 1.2)?
  YES → STOP (skip levels 2 and 3)

Result: Found 13 unique candidates with NO duplication, minimal cost
```

---

## Benefits

### Global Counter
- Stop escalation early if we already have enough
- Don't waste expensive API calls when target met
- Typical savings: Skip 1-2 levels = 50-70% cost reduction

### Exclusion List
- No duplicate entities found
- Faster deduplication (nothing to dedupe!)
- Better use of tokens (focus on new entities)
- More diverse results across subdomains

---

## Implementation Checklist

### 1. Update row_discovery.py
- [ ] Add global counter after each level
- [ ] Track accumulated_entities across subdomains
- [ ] Build exclusion_list before each subdomain
- [ ] Pass exclusion_list to row_discovery_stream

### 2. Update row_discovery_stream.py
- [ ] Accept exclusion_list parameter
- [ ] Pass to prompt builder
- [ ] Add to prompt variables

### 3. Update row_discovery.md prompt
- [ ] Add EXCLUSION_LIST section
- [ ] Add instructions to avoid excluded entities
- [ ] Add example showing how to handle exclusions

### 4. Update row_discovery_response.json schema
- [ ] No changes needed (exclusion is input-only)

### 5. Test
- [ ] Verify exclusion works (no duplicates found)
- [ ] Verify global counter stops early
- [ ] Check cost savings

---

## Estimated Implementation

- row_discovery.py: +80 lines (global counter + exclusion tracking)
- row_discovery_stream.py: +30 lines (exclusion parameter)
- row_discovery.md: +15 lines (exclusion section)
- Tests: +20 lines (verify exclusions)

**Total:** ~145 lines
**Time:** ~1-1.5 hours

---

**Should I implement these improvements now?**

They're both excellent optimizations that will:
- Reduce duplicate finding
- Enable earlier stopping
- Better resource usage
- Cleaner results
