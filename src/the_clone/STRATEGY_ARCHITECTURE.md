# Strategy-Based Architecture Design

## Flow

```
1. Initial Decision
   ↓
   breadth, depth, search_terms

2. Get Strategy
   ↓
   strategy = get_strategy(breadth, depth)
   - sources_per_batch
   - extraction_mode
   - stop_condition

3. Search & Triage (Once)
   ↓
   For each search_term:
     - Search → get 10 results
     - Triage → rank ALL results [best→worst]

   Result: ranked_sources = [[0,5,2,...], [3,1,7,...]]

4. Iterative Extraction
   ↓
   sources_pulled = 0
   snippets = []

   For iteration in 1..global_max_iterations:
     # Get next batch
     batch_size = strategy.sources_per_batch
     sources_this_iter = ranked_sources[sources_pulled : sources_pulled + batch_size]

     # Extract
     new_snippets = extract(sources_this_iter, mode=strategy.extraction_mode)
     snippets.extend(new_snippets)
     sources_pulled += len(sources_this_iter)

     # Check stop conditions
     if strategy.stop_condition_met(snippets):
       break  # Found what we need

     if sources_pulled >= len(ranked_sources):
       break  # No more sources

     if iteration >= global_max_iterations:
       break  # Hard cap

5. Synthesize
   ↓
   answer = synthesize(snippets, mode=from strategy)
```

## Strategy Matrix

| Strategy | Breadth | Depth | Batch Size | Mode | Tokens/Page | Batch Extract | Stop When |
|----------|---------|-------|------------|------|-------------|---------------|-----------|
| Targeted | narrow | shallow | 5 | simple_facts | 512 | Yes (5/call) | Reliable answer found (p≥0.85) |
| Focused Deep | narrow | deep | 10 | nuanced | 2048 | No | All sources (1 iter) |
| Survey | broad | shallow | 15 | simple_facts | 512 | Yes (3x5) | All sources (1 iter) |
| Comprehensive | broad | deep | 15 | nuanced | 2048 | No | All sources (1 iter) |

**Dimensions:**
- **Tokens/Page**: Controls Perplexity max_tokens_per_page (512 for shallow = faster/smaller, 2048 for deep = comprehensive)
- **Batch Extract**: If true, extract multiple sources in single API call (shallow strategies = 5 sources/call); if false, individual extraction calls (deep)
- **Stop Condition**:
  - "reliable_answer_found" = stop when reliable answer to EXACT query found (p≥0.85, search_ref=1) - targeted only
  - null = process all sources (broad or deep strategies)

## Example: Targeted (narrow + shallow)

Query: "What is DeepSeek V3's parameter count?"

```
Initial: breadth=narrow, depth=shallow, terms=["DeepSeek V3 parameters"]
Strategy: targeted (batch=5, mode=simple_facts, stop=reliable_answer_found)

Search: 10 results
Triage: Ranked [5, 0, 8, 2, 7, 1, 9, 3, 4, 6]

Iteration 1:
  Pull sources [5, 0, 8, 2, 7] (5 sources - batch extraction)
  Extract (batch mode: single API call for all 5)
  → Got 3 snippets: p=0.95 (search_ref=1), p=0.85 (search_ref=1), p=0.65 (search_ref=2)
  Check stop: YES (≥1 reliable answer to exact query, search_ref=1) → STOP

Synthesize from 3 snippets
Total: 1 iteration, 5 sources, 1 extraction API call
```

## Example: Comprehensive (broad + deep)

Query: "Comprehensive analysis of transformer architecture"

```
Initial: breadth=broad, depth=deep, terms=["transformer architecture"]
Strategy: comprehensive (batch=15, mode=nuanced, stop=null)

Search: 10 results
Triage: Ranked [2, 5, 0, 8, 7, 1, 9, 3, 4, 6]

Iteration 1:
  Pull sources [2,5,0,8,7,1,9,3,4,6] (all 10)
  Extract (nuanced mode)
  → Got 45 snippets: varied p-scores
  Check stop: null (pull all) → Continue
  No more sources → STOP

Synthesize from 45 snippets
Total: 1 iteration, 10 sources
```

## Key Points

1. **Triage happens once** - ranks all sources upfront
2. **Extraction is iterative** - pull batches based on strategy
3. **Stop conditions** - strategy-specific + global max
4. **Clean separation** - strategy config separate from iteration logic
