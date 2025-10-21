# Progressive Escalation - Example Execution

This shows what you'll see when running `test_local_e2e_sequential.py` with progressive escalation enabled.

---

## Expected Console Output

```
============================================================
INDEPENDENT ROW DISCOVERY - LOCAL E2E TEST (SEQUENTIAL)
============================================================

[INFO] Checking environment...
[SUCCESS] API keys found
[INFO] Using Perplexity API for web search

[1/3] Initializing components...
[SUCCESS] All components initialized

[2/3] Defining columns and search strategy (with subdomains)...
[SUCCESS] Defined 5 columns in 15.3s ($0.0012)
[INFO] Table: AI Companies Hiring Tracker
[INFO]   ID columns: 2
    - Company Name
    - Website
[INFO]   Data columns: 3
    - Is hiring for AI roles?
    - Team size (approximate)
    - Recent funding (last round)
[SUCCESS] Search strategy with 3 subdomains:
  - AI Research Companies (target: 10 rows)
    Focus: Academic and research-focused AI organizations
  - Healthcare AI Startups (target: 10 rows)
    Focus: AI companies in healthcare and medical applications
  - Enterprise AI Solutions (target: 10 rows)
    Focus: B2B AI platforms and enterprise tools
[INFO]   Total target: 30 rows (will keep best 10)

[3/3] Discovering rows (SEQUENTIAL mode with progressive escalation)...
[INFO] Starting sequential row discovery with progressive escalation...
[INFO] (Processing one subdomain at a time)
[INFO] Progressive escalation strategy: 3 rounds
[INFO]   Round 1: sonar (low) - stop at 50% if set
[INFO]   Round 2: sonar (high) - stop at 75% if set
[INFO]   Round 3: sonar-pro (high) - stop at None if set

Stream 1/3: AI Research Companies
  [INFO] Progressive escalation: 2 round(s) executed, 1 skipped
  [INFO] Candidates by model: sonar(low): 6, sonar(high): 4
  [SUCCESS] Found 10 candidates in 52.3s
  [INFO] Top candidate: Anthropic (score: 0.92, from sonar(high))

Stream 2/3: Healthcare AI Startups
  [INFO] Progressive escalation: 1 round(s) executed, 2 skipped
  [INFO] Candidates by model: sonar(low): 7
  [SUCCESS] Found 7 candidates in 23.1s
  [INFO] Top candidate: Tempus AI (score: 0.88, from sonar(low))

[INFO] Early stop between subdomains: 17 candidates >= 12.0 threshold (120% of 10). Skipping 1 remaining subdomain(s)

[CONSOLIDATION]
  Total candidates: 17
  Duplicates removed: 3
  Below threshold (<0.6): 2
  Final count: 10

[SUCCESS] Row discovery completed in 75.4s

============================================================
                         RESULTS
============================================================

[COLUMNS] (5 total):
  [ID] Company Name
  [ID] Website
  [DATA] Is hiring for AI roles?
  [DATA] Team size (approximate)
  [DATA] Recent funding (last round)

[ROWS DISCOVERED] (10 total, sorted by score):

  1. Anthropic (score: 0.92, quality_rank: 3)
     Website: https://anthropic.com
     Scores: Relevancy=0.95, Reliability=0.90, Recency=0.88
     Model: sonar(high)
     [MERGED] Found by: sonar(low), sonar(high)
     Rationale: Leading AI safety research company with active hiring for research scientists and engineers

  2. OpenAI (score: 0.90, quality_rank: 3)
     Website: https://openai.com
     Scores: Relevancy=0.93, Reliability=0.90, Recency=0.85
     Model: sonar(high)
     Rationale: Creator of ChatGPT and GPT-4, actively hiring across all AI roles

  3. Tempus AI (score: 0.88, quality_rank: 2)
     Website: https://tempus.com
     Scores: Relevancy=0.90, Reliability=0.85, Recency=0.88
     Model: sonar(low)
     Rationale: Healthcare AI platform using genomics and clinical data, recently IPO'd with strong hiring

  4. DeepMind (score: 0.87, quality_rank: 2)
     Website: https://deepmind.google
     Scores: Relevancy=0.92, Reliability=0.85, Recency=0.82
     Model: sonar(low)
     [MERGED] Found by: sonar(low), sonar(high)
     Rationale: Google's AI research lab, known for AlphaFold and AlphaGo, actively hiring researchers

  5. Cohere (score: 0.85, quality_rank: 3)
     Website: https://cohere.ai
     Scores: Relevancy=0.88, Reliability=0.83, Recency=0.83
     Model: sonar(high)
     Rationale: Enterprise AI platform focusing on NLP and language models for businesses

  ... (5 more rows)

[STATISTICS]
  Total execution time: 1m 30.7s
  Column definition: 15.3s ($0.0012)
  Row discovery (sequential): 75.4s ($0.0018)
    - Individual streams:
      Stream 1: 52.3s
      Stream 2: 23.1s
    - (Note: Sequential = sum of all streams)
  Candidates found: 17
  Deduplication: 3 removed
  Below threshold: 2 filtered
  Final rows: 10
  Avg match score: 0.84
  Total cost: $0.0030

[INFO] Results saved to: table_maker/output/local_tests/sequential_test_20251021_143052.json

============================================================
                  [SUCCESS] LOCAL E2E TEST COMPLETE
============================================================

Next steps:
  1. Review the results above
  2. Check match scores and quality
  3. If quality looks good, test parallel mode (max_parallel_streams=2)
  4. Then scale up to full parallelization (max_parallel_streams=5)

============================================================
                       TEST PASSED
============================================================
```

---

## Key Observations

### 1. Early Stopping Within Subdomain
**Stream 1:** Executed 2 rounds, skipped 1
- Round 1 (sonar-low): 6 candidates
- Round 2 (sonar-high): 4 candidates → Total 10 >= 75% of 10 target
- **Skipped Round 3 (sonar-pro-high)** → Saved ~$0.002 + 45s

### 2. Early Stopping Within Subdomain (Extreme)
**Stream 2:** Executed 1 round, skipped 2
- Round 1 (sonar-low): 7 candidates >= 50% of 10 target
- **Skipped Rounds 2-3** → Saved ~$0.004 + 75s

### 3. Early Stopping Between Subdomains
After Stream 2: 17 candidates >= 120% of 10 target (12 threshold)
- **Skipped entire Stream 3** → Saved ~$0.005 + 75s

### 4. Model Preference on Deduplication
3 duplicates found:
- Example: "Anthropic" found by sonar(low) AND sonar(high)
- **Kept:** sonar(high) version (rank 3 > rank 2)
- **Merged:** Source URLs from both

### 5. Cost Savings
**Without Progressive Escalation:**
- 3 subdomains × sonar-pro(high) = ~$0.009 + 135s

**With Progressive Escalation:**
- Stream 1: 2 rounds = ~$0.002 + 52s
- Stream 2: 1 round = ~$0.001 + 23s
- Stream 3: SKIPPED = $0.000 + 0s
- **Total: ~$0.003 + 75s**

**Savings: 67% cost, 44% time**

---

## Model Quality Ranking in Action

Notice the `quality_rank` values:

| Candidate | Model Used | Context | Quality Rank | Why? |
|-----------|-----------|---------|--------------|------|
| Anthropic | sonar | high | 3 | sonar + high context |
| OpenAI | sonar | high | 3 | sonar + high context |
| Tempus AI | sonar | low | 2 | sonar + low context |
| DeepMind | sonar | low | 2 | Found by both, kept sonar(high) = rank 3, but shown as low due to merge logic bug (will fix) |
| Cohere | sonar | high | 3 | sonar + high context |

Higher rank = better quality model/context used.

---

## Deduplication Example

**"Anthropic" found by multiple rounds:**

```json
{
  "id_values": {"Company Name": "Anthropic", "Website": "https://anthropic.com"},
  "match_score": 0.92,
  "model_used": "sonar",
  "context_used": "high",
  "found_by_models": ["sonar(low)", "sonar(high)"],
  "model_quality_rank": 3,
  "source_urls": [
    "https://anthropic.com/careers",
    "https://techcrunch.com/anthropic-hiring",
    "...merged from both rounds..."
  ]
}
```

**Benefits:**
- Keep highest quality version (sonar-high > sonar-low)
- Merge all source URLs (more evidence)
- Track which models found it (transparency)

---

## Next: Run the Test!

```bash
cd /mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator/table_maker
python.exe test_local_e2e_sequential.py
```

Compare your actual output to this example to validate the implementation!
