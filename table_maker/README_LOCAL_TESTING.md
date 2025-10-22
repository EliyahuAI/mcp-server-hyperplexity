# Local Testing Guide - Independent Row Discovery

This guide helps you test the Table Maker's Independent Row Discovery system locally with real API keys before deploying to AWS.

---

## Quick Start

### 1. Setup Environment

Copy the environment template:
```bash
cp .env.example .env
```

Edit `.env` and add your API keys:
```bash
# Required
ANTHROPIC_API_KEY=sk-ant-api03-...

# Optional (recommended for better web search)
PERPLEXITY_API_KEY=pplx-...
```

**Where to get API keys:**
- Anthropic: https://console.anthropic.com/
- Perplexity: https://www.perplexity.ai/settings/api

### 2. Install Dependencies

```bash
# From the table_maker directory
cd table_maker
pip install -r requirements.txt
```

### 3. Run Sequential Test

```bash
# On Linux/Mac:
python3 test_local_e2e_sequential.py

# On Windows WSL (use python.exe):
python.exe test_local_e2e_sequential.py
```

**What to expect:**
- Duration: ~2-3 minutes
- Cost: ~$0.10-0.15
- Output: Finds 10 AI companies with quality scores

---

## What the Test Does

The `test_local_e2e_sequential.py` script tests the complete Independent Row Discovery pipeline:

### Step 1: Column Definition (with Subdomains)
- Takes a user request for a table about AI companies
- Defines 5 columns (2 ID columns, 3 data columns)
- Creates 3 subdomains for parallel search:
  - AI Research Companies
  - Healthcare AI
  - Enterprise AI
- Each subdomain gets specific search queries and target row counts

**Time:** ~15-20 seconds

### Step 2: Row Discovery (Sequential Mode)
- Processes one subdomain at a time (max_parallel_streams=1)
- For each subdomain:
  - Executes integrated scoring search using `sonar-pro`
  - Finds candidate companies with match scores (0-1.0)
  - Returns scored candidates with rationales
- Uses the **3-dimension scoring rubric:**
  - **Relevancy** (40%): How well it matches requirements
  - **Source Reliability** (30%): Quality of information sources
  - **Recency** (30%): How recent the information is

**Time:** ~90-120 seconds

### Step 3: Consolidation
- Combines all candidates from all streams (~15 found)
- Removes duplicates using fuzzy matching
- Filters out low-quality candidates (score < 0.6)
- Returns top 10 best candidates sorted by score

**Time:** ~2-5 seconds

---

## Understanding the Output

### Successful Run Example

```
============================================================
INDEPENDENT ROW DISCOVERY - LOCAL E2E TEST (SEQUENTIAL)
============================================================

[INFO] Checking environment...
[SUCCESS] API keys found

[1/3] Initializing components...
[SUCCESS] All components initialized

[2/3] Defining columns and search strategy (with subdomains)...
[SUCCESS] Defined 5 columns in 16.2s
[INFO] Table: AI Companies Hiring Status
[SUCCESS] Search strategy with 3 subdomains:
  - AI Research Companies (target: 5 rows)
  - Healthcare AI (target: 5 rows)
  - Enterprise AI (target: 5 rows)
  - Total target: 15 rows (will keep best 10)

[3/3] Discovering rows (SEQUENTIAL mode)...

Stream 1/3: AI Research Companies
  [INFO] Executing integrated scoring search...
  [SUCCESS] Found 5 candidates in 42.3s
  [INFO] Top candidate: Anthropic (score: 0.95)

Stream 2/3: Healthcare AI
  [INFO] Executing integrated scoring search...
  [SUCCESS] Found 5 candidates in 38.7s
  [INFO] Top candidate: Tempus AI (score: 0.89)

Stream 3/3: Enterprise AI
  [INFO] Executing integrated scoring search...
  [SUCCESS] Found 5 candidates in 41.2s
  [INFO] Top candidate: Scale AI (score: 0.91)

[CONSOLIDATION]
  Total candidates: 15
  Duplicates removed: 2
  Below threshold (<0.6): 1
  Final count: 10

============================================================
RESULTS
============================================================

[COLUMNS] (5 total):
  [ID] Company Name
  [ID] Website
  [DATA] Is Hiring for AI?
  [DATA] Team Size
  [DATA] Recent Funding

[ROWS DISCOVERED] (10 total, sorted by score):

  1. Anthropic (0.95)
     Website: anthropic.com
     Scores: Relevancy=0.95, Reliability=0.93, Recency=0.97
     Rationale: Leading AI safety company. Source: anthropic.com. Updated Oct 2025.

  2. Scale AI (0.91)
     Website: scale.com
     Scores: Relevancy=0.92, Reliability=0.90, Recency=0.91
     Rationale: Enterprise AI platform. Source: Crunchbase. Recent funding news.

  ... [8 more companies]

[STATISTICS]
  Total execution time: 138.4s
  Column definition: 16.2s
  Row discovery (sequential): 122.2s
    - Individual streams:
      Stream 1: 42.3s
      Stream 2: 38.7s
      Stream 3: 41.2s
    - (Note: Sequential = sum of all streams)
  Candidates found: 15
  Deduplication: 2 removed
  Below threshold: 1 filtered
  Final rows: 10
  Avg match score: 0.84

[INFO] Results saved to: table_maker/output/local_tests/sequential_test_20251021_143527.json

============================================================
[SUCCESS] LOCAL E2E TEST COMPLETE
============================================================

Next steps:
  1. Review the results above
  2. Check match scores and quality
  3. If quality looks good, test parallel mode (max_parallel_streams=2)
  4. Then scale up to full parallelization (max_parallel_streams=5)
```

---

## Troubleshooting

### "ANTHROPIC_API_KEY not set"

**Problem:** The script can't find your Anthropic API key.

**Solutions:**
1. Check that `.env` file exists in the `table_maker/` directory
2. Verify the API key is correctly formatted: `ANTHROPIC_API_KEY=sk-ant-...`
3. Try exporting directly in your shell:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-api03-...
   python3 test_local_e2e_sequential.py
   ```
4. Verify your API key works:
   ```bash
   curl https://api.anthropic.com/v1/messages \
     -H "x-api-key: $ANTHROPIC_API_KEY" \
     -H "anthropic-version: 2023-06-01" \
     -H "content-type: application/json" \
     -d '{"model":"claude-haiku-4-5","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}'
   ```

### "ImportError: No module named 'ai_api_client'"

**Problem:** Python can't find the required modules.

**Solutions:**
1. Make sure you're running from the `table_maker/` directory:
   ```bash
   cd table_maker
   python3 test_local_e2e_sequential.py
   ```
2. Verify the file exists:
   ```bash
   ls ../src/shared/ai_api_client.py
   ```
3. Check sys.path setup in the script (should be automatic)
4. Try installing in development mode:
   ```bash
   pip install -e ..
   ```

### "No subdomains defined in search_strategy!"

**Problem:** The column definition isn't returning subdomains.

**This means you're using the OLD architecture.** The test requires the REVISED architecture where subdomains are defined during column definition.

**Solution:**
1. Check that your `column_definition.md` prompt includes subdomain instructions
2. Verify `column_definition_response.json` schema includes `subdomains` in `search_strategy`
3. See `docs/REVISED_ARCHITECTURE_ROW_DISCOVERY.md` for details

### "Web search failed" or Perplexity API errors

**Problem:** Web search isn't working.

**Solutions:**
1. Check your internet connection
2. If you have `PERPLEXITY_API_KEY` set:
   - Verify it's valid and active
   - Check you have API credits remaining
   - Try without it (comment it out in `.env`)
3. Without Perplexity key, Anthropic's search will be used instead
4. Check API rate limits - wait a minute and retry

### Script runs but finds 0 candidates

**Problem:** Row discovery completes but no candidates found.

**Possible causes:**
1. Web search returning no results (check search queries in output)
2. All candidates scored below threshold (0.6)
3. AI model having trouble with the prompt format

**Solutions:**
1. Check the subdomains and search queries being used
2. Try lowering `MIN_MATCH_SCORE` from 0.6 to 0.4 in the script
3. Add more detailed logging to see raw search results
4. Check that `row_discovery_stream.py` is using integrated scoring

### Test takes too long (>5 minutes)

**Problem:** The test is taking much longer than expected.

**Normal timing:**
- Column definition: 15-20s
- Each stream: 30-50s
- Total: 2-3 minutes

**If it's taking longer:**
1. Check your internet connection speed
2. Perplexity API might be slow - try without it
3. Check API rate limiting (look for retry messages)
4. Verify you're in sequential mode (max_parallel_streams=1)

---

## Configuration Options

You can modify these variables at the top of `test_local_e2e_sequential.py`:

```python
# Test parameters
TARGET_ROW_COUNT = 10          # Final number of rows (default: 10)
DISCOVERY_MULTIPLIER = 1.5     # Overshoot factor (default: 1.5 = find 15, keep 10)
MIN_MATCH_SCORE = 0.6          # Quality threshold (default: 0.6)

# Models
COLUMN_DEFINITION_MODEL = "claude-sonnet-4-5"  # For column definition
WEB_SEARCH_MODEL = "sonar-pro"                  # For web search + scoring

# User request
USER_REQUEST = """
Your custom table request here...
"""
```

**Example modifications:**

Find more rows:
```python
TARGET_ROW_COUNT = 20          # Find 20 companies instead of 10
DISCOVERY_MULTIPLIER = 1.5     # Will find 30, keep best 20
```

Be more selective:
```python
MIN_MATCH_SCORE = 0.75         # Only keep high-quality matches
DISCOVERY_MULTIPLIER = 2.0     # Find more to choose from
```

Different use case:
```python
USER_REQUEST = """
Create a table of machine learning conferences in 2024.
Columns: Conference name, location, date, submission deadline.
Find about 15 conferences.
"""
TARGET_ROW_COUNT = 15
```

---

## Next Steps

### After Successful Sequential Test

1. **Review Quality:**
   - Check the match scores (should be 0.7-0.95 range)
   - Read the rationales - do they make sense?
   - Verify the sources are reliable
   - Check for duplicates that weren't caught

2. **Test Parallel Mode:**
   - Modify the script to use `max_parallel_streams=2`
   - Should be ~30-40% faster
   - Verify results are still good quality

3. **Full Parallelization:**
   - Use `max_parallel_streams=5`
   - Should complete in ~60-80 seconds
   - Performance target met

4. **Deploy to AWS:**
   - Update Lambda functions with revised architecture
   - Test with WebSocket queue for user feedback
   - Monitor costs and performance

---

## Understanding Costs

Approximate costs per test run:

| Component | Model | Calls | Cost per Call | Total |
|-----------|-------|-------|---------------|-------|
| Column Definition | claude-sonnet-4-5 | 1 | ~$0.02 | $0.02 |
| Stream 1 Search | sonar-pro | 1 | ~$0.02 | $0.02 |
| Stream 2 Search | sonar-pro | 1 | ~$0.02 | $0.02 |
| Stream 3 Search | sonar-pro | 1 | ~$0.02 | $0.02 |
| **Total** | | **4** | | **~$0.08** |

**Notes:**
- Actual costs depend on input/output token counts
- Perplexity's sonar-pro includes search context (may be higher)
- Sequential vs parallel doesn't affect cost (same number of calls)
- Costs shown are estimates, check your API dashboards for actuals

---

## Architecture Notes

### Why Sequential First?

Testing in sequential mode (one subdomain at a time) helps us:

1. **Validate each component independently**
   - Each stream works correctly
   - Scoring produces good results
   - No race conditions to debug

2. **Easier debugging**
   - Clear linear flow
   - Easier to trace errors
   - Can see exact timing per stream

3. **Baseline for comparison**
   - Sequential time = sum of all streams
   - Parallel should be ~3x faster (for 3 streams)
   - Can measure parallelization benefits

### Integrated Scoring

The **REVISED architecture** uses integrated scoring where:
- One call to `sonar-pro` does both web search AND scoring
- Scoring happens during search (not after)
- Faster and cheaper than separate calls
- Scoring rubric aware of search context

### Subdomains in Column Definition

The **REVISED architecture** includes subdomains in column definition:
- One fewer AI call (saves time and money)
- Subdomains designed with column context in mind
- More coherent search strategy

---

## Files Created by Test

The test saves results to `table_maker/output/local_tests/`:

```
sequential_test_20251021_143527.json    # Full results with all data
```

This JSON file contains:
- User request
- Configuration used
- All columns defined
- Search strategy with subdomains
- All discovered rows with scores
- Complete statistics

**Use this for:**
- Analyzing quality trends
- Debugging specific issues
- Sharing results with team
- Comparing different configurations

---

## Getting Help

### Check Documentation
- `docs/REVISED_ARCHITECTURE_ROW_DISCOVERY.md` - Architecture details
- `table_maker/TESTING.md` - Testing strategy
- `table_maker/README.md` - General overview

### Common Issues
- Most problems are environment setup (API keys)
- Check that you're using the REVISED architecture (subdomains in column definition)
- Verify all imports work before running tests

### Debug Logging
To see more details, modify the test script:

```python
import logging
logging.basicConfig(level=logging.DEBUG)  # Was INFO
```

This shows:
- API call details
- Prompt content
- Raw responses
- Timing breakdown

---

## Summary

This local testing setup allows you to:
- ✓ Test complete pipeline with real API keys
- ✓ Validate Independent Row Discovery works correctly
- ✓ Verify integrated scoring produces good results
- ✓ Measure timing and costs accurately
- ✓ Debug issues before AWS deployment
- ✓ Iterate on prompts and configuration locally

Once sequential tests pass consistently with good quality results, proceed to parallel testing and then AWS deployment.
