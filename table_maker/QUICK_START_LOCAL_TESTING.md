# Quick Start - Local Testing

**Run your first Independent Row Discovery test in 5 minutes!**

---

## Step 1: Set Up Environment (2 minutes)

```bash
cd table_maker
cp .env.example .env
```

Edit `.env` and add your API key:
```bash
ANTHROPIC_API_KEY=sk-ant-api03-YOUR-KEY-HERE
```

Get your API key at: https://console.anthropic.com/

---

## Step 2: Install Dependencies (1 minute)

```bash
pip install -r requirements.txt
```

---

## Step 3: Run Test (2-3 minutes)

```bash
# On Linux/Mac:
python3 test_local_e2e_sequential.py

# On Windows WSL (use python.exe):
python.exe test_local_e2e_sequential.py
```

---

## What You'll See

```
============================================================
INDEPENDENT ROW DISCOVERY - LOCAL E2E TEST (SEQUENTIAL)
============================================================

[SUCCESS] API keys found

[1/3] Initializing components...
[SUCCESS] All components initialized

[2/3] Defining columns and search strategy (with subdomains)...
[SUCCESS] Defined 5 columns in 16.2s
[SUCCESS] Search strategy with 3 subdomains...

[3/3] Discovering rows (SEQUENTIAL mode)...
Stream 1/3: AI Research Companies
  [SUCCESS] Found 5 candidates in 42.3s

[CONSOLIDATION]
  Final count: 10

============================================================
RESULTS
============================================================

[ROWS DISCOVERED] (10 total, sorted by score):
  1. Anthropic (0.95)
  2. Scale AI (0.91)
  ... [8 more]

[SUCCESS] LOCAL E2E TEST COMPLETE
```

---

## Costs

Expected cost: **~$0.10** per test run

---

## Need Help?

**API key not working?**
```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
python3 test_local_e2e_sequential.py
```

**Import errors?**
- Make sure you're in the `table_maker/` directory
- Run: `pip install -r requirements.txt`

**More help:**
- See `README_LOCAL_TESTING.md` for detailed troubleshooting
- See `LOCAL_TEST_SETUP_SUMMARY.md` for complete setup details

---

## Next Steps

1. **Review quality** - Check the match scores and rationales
2. **Test parallel** - Modify script to use `max_parallel_streams=2`
3. **Deploy to AWS** - Once quality validates

---

That's it! You're testing Independent Row Discovery locally.
