# Quick Start Guide - Demo Test Orchestrator

## 5-Minute Setup

### Step 1: Install Dependencies

```bash
pip install requests openpyxl boto3
```

### Step 2: Configure AWS (if using S3 features)

```bash
aws configure
# Enter your AWS credentials when prompted
```

### Step 3: Run the Test Orchestrator

```bash
cd deployment
python test_all_demos.py
```

That's it! The orchestrator will:
1. Discover all demos in `../demos/`
2. Load each demo from S3
3. Run preview validation (5 rows)
4. Run full validation (all rows)
5. Download result files
6. Generate comprehensive reports

## Output

Results will be saved to `./test_results/` including:
- **Log file** - Detailed execution log
- **Text report** - Human-readable summary
- **JSON report** - Machine-readable data
- **HTML report** - Rich web report

## Common Commands

```bash
# Run all tests with default settings
python test_all_demos.py

# Continue on errors (don't stop at first failure)
python test_all_demos.py --no-stop-on-error

# Skip preview (only run full validation)
python test_all_demos.py --skip-preview

# Test with different email
python test_all_demos.py --email your@email.com

# Custom output directory
python test_all_demos.py --output-dir ./my_results
```

## Expected Runtime

- **Preview per demo**: ~45-60 seconds
- **Full validation per demo**: ~3-5 minutes
- **Total for 10 demos**: ~40-60 minutes

## Interpreting Results

### Success

```
[SUCCESS] Demo test completed: Investment Research
```

All steps passed:
- Demo loaded from S3
- Preview validation completed
- Full validation completed
- Result file downloaded and verified

### Failure

```
[ERROR] Demo test failed: Validation timeout after 1800s
```

Check the error details in:
- Console output (real-time)
- Log file (detailed trace)
- JSON report (structured data)

## Troubleshooting

### "No module named 'demo_api_client'"

Run from the `deployment/` directory:
```bash
cd deployment
python test_all_demos.py
```

### "Demo 'investment_research' not found"

The demo hasn't been uploaded to S3 yet. Upload it first:
```bash
python upload_demos.py --demos-folder ../demos --bucket hyperplexity-storage-dev --upload
```

### "No AWS credentials found"

Configure AWS:
```bash
aws configure
# Or set environment variables:
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
```

## Next Steps

1. **Review Reports** - Check HTML report in browser for detailed results
2. **Verify Output Files** - Ensure `*_Output.xlsx` files were updated in demo folders
3. **Track Metrics** - Compare costs and timing across runs
4. **Integrate CI/CD** - Add to GitHub Actions or Jenkins pipeline

For full documentation, see: `TEST_ALL_DEMOS_README.md`
