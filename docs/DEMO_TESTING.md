# Demo Testing System

**Quick Guide** | [Detailed Documentation](demo_testing_detailed_docs/)

---

## What is This?

Automated end-to-end testing system for all 10 Hyperplexity Validator demo tables. Runs preview and full validation workflows, downloads results, and verifies everything works correctly.

**Key Features:**
- Tests all 10 demos automatically
- Uses dev environment (no production impact)
- Downloads and overwrites output Excel files
- Stops on first error with detailed reporting
- Generates comprehensive test reports

---

## Quick Start (5 Minutes)

### Prerequisites

```bash
# 1. Switch to demo-testing branch
git checkout demo-testing

# 2. Verify account balance (need ~$2 minimum)
python src/manage_dynamodb_tables.py check-balance eliyahu@eliyahu.ai
# Expected: Balance >= $2.00

# 3. Check Python dependencies
python -c "import boto3, requests, openpyxl; print('OK')"
# Expected: OK
```

### Run Tests

```bash
# Test single demo (recommended first run)
cd testing
python test_all_demos.py --demos-dir ../demos --stop-on-error

# Test all 10 demos (~40-60 minutes)
python test_all_demos.py --demos-dir ../demos --email eliyahu@eliyahu.ai
```

### View Results

```bash
# Check test report
cat test_results/*/report.txt

# Verify output files updated
ls -lh ../demos/*/\*Output.xlsx
```

---

## System Architecture

### Components

```
testing/
├── test_all_demos.py          # Main orchestrator
├── demo_api_client.py          # API Gateway client
├── demo_session_manager.py     # S3 session management
└── demo_test_reporter.py       # Report generation
```

### Workflow

```
For each demo:
  1. Load demo from S3 → Creates session
  2. Run preview validation → First row only
  3. Run full validation → All rows
  4. Download results → enhanced_validation.xlsx
  5. Overwrite output file → demos/XX. Demo Name/*_Output.xlsx
  6. Verify integrity → Open with openpyxl
```

### Environment

| Resource | Value |
|----------|-------|
| Environment | dev |
| API Gateway | `https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev` |
| S3 Bucket | `hyperplexity-storage-dev` |
| Test Email | `eliyahu@eliyahu.ai` |

---

## Command Reference

### Test Commands

```bash
# Test specific demo
python test_all_demos.py --demos-dir ../demos --stop-on-error

# Test all demos
python test_all_demos.py

# Skip preview phase
python test_all_demos.py --skip-preview

# Continue on errors (don't stop)
python test_all_demos.py --no-stop-on-error

# Custom output directory
python test_all_demos.py --output-dir ../custom_results
```

### Utility Commands

```bash
# Check account balance
python ../src/manage_dynamodb_tables.py check-balance eliyahu@eliyahu.ai

# List available demos via API
python demo_api_client.py list

# List existing sessions
python demo_session_manager.py list --email eliyahu@eliyahu.ai

# Cleanup old sessions
python demo_session_manager.py cleanup --email eliyahu@eliyahu.ai --older-than 7
```

---

## Validation Criteria

### Per-Demo Success Criteria

Each demo must pass:
- ✅ Demo loads from S3 successfully
- ✅ Preview completes within 5 minutes
- ✅ Full validation completes within 30 minutes
- ✅ Results downloaded successfully
- ✅ Output file overwritten
- ✅ Excel file is valid (openpyxl can open)

### Overall Success Criteria

Complete test run must achieve:
- ✅ 10/10 demos tested
- ✅ 10/10 demos passed
- ✅ 0 failures
- ✅ Total time < 90 minutes
- ✅ All output files updated
- ✅ Report generated in TEXT, JSON, and HTML formats

---

## Expected Output

### Console Output

```
[SUCCESS] Demo Testing System - Starting
[SUCCESS] Environment: dev
[SUCCESS] Email: eliyahu@eliyahu.ai
[SUCCESS] Found 10 demos in ../demos

[1/10] Testing: 01. Investment Research
  [LOAD] Loading demo from S3... SUCCESS (2.3s)
  [PREVIEW] Running preview validation... SUCCESS (48.5s)
  [VALIDATE] Running full validation... SUCCESS (4.2 min)
  [DOWNLOAD] Downloading results... SUCCESS (1.8s)
  [VERIFY] Verifying file integrity... SUCCESS

[2/10] Testing: 02. Competitive Intelligence
  ...

[SUCCESS] All Tests Complete!
  Total: 10
  Passed: 10
  Failed: 0
  Duration: 52.4 minutes
```

### Test Report (test_results/*/report.txt)

```
=================================================================
                    DEMO TESTING REPORT
=================================================================

Test Information:
  Email: eliyahu@eliyahu.ai
  Environment: dev
  Start Time: 2025-10-11 14:30:00
  End Time: 2025-10-11 15:22:24
  Duration: 52.4 minutes

Summary:
  Total Demos: 10
  Passed: 10
  Failed: 0
  Success Rate: 100.0%

Results:
  [PASS] 01. Investment Research (5.2 min)
  [PASS] 02. Competitive Intelligence (4.8 min)
  [PASS] 03. Market Analysis (5.5 min)
  ...
```

---

## Troubleshooting

### Common Issues

**API Connection Failure**
```bash
# Test API connectivity
curl -I https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev/health

# Check AWS credentials
aws sts get-caller-identity
```

**Insufficient Balance**
```bash
# Check balance
python ../src/manage_dynamodb_tables.py check-balance eliyahu@eliyahu.ai

# Add balance if needed
python ../src/manage_dynamodb_tables.py add-balance eliyahu@eliyahu.ai 25.00
```

**Demo Not Found**
```bash
# Verify demo exists
ls -la ../demos/

# Check S3 for demos
aws s3 ls s3://hyperplexity-storage-dev/demos/
```

**Validation Timeout**
```bash
# Increase timeout
python test_all_demos.py --validation-timeout 45

# Check CloudWatch logs
aws logs tail /aws/lambda/perplexity-validator-interface-dev --follow
```

---

## Testing Workflow

### 1. Pre-Test Validation
- [ ] On demo-testing branch
- [ ] Account balance >= $2.00
- [ ] AWS credentials configured
- [ ] S3 bucket accessible
- [ ] Python dependencies installed

### 2. Single Demo Test
```bash
python testing/test_all_demos.py --demos-dir demos --stop-on-error
```
- [ ] Demo loads successfully
- [ ] Preview completes
- [ ] Validation completes
- [ ] Results downloaded
- [ ] Report generated

### 3. Full Test Run
```bash
python testing/test_all_demos.py --demos-dir demos
```
- [ ] All 10 demos tested
- [ ] All passed
- [ ] Output files updated
- [ ] Report shows 10/10

### 4. Result Verification
- [ ] Check `test_results/*/report.txt`
- [ ] Verify all output files updated: `ls -lh demos/*/\*Output.xlsx`
- [ ] Spot-check 2-3 Excel files manually

---

## File Locations

| Component | Path |
|-----------|------|
| **Testing Scripts** | |
| Main orchestrator | `testing/test_all_demos.py` |
| API client | `testing/demo_api_client.py` |
| Session manager | `testing/demo_session_manager.py` |
| Test reporter | `testing/demo_test_reporter.py` |
| **Documentation** | |
| This guide | `docs/DEMO_TESTING.md` |
| Detailed docs | `docs/demo_testing_detailed_docs/` |
| **Demo Files** | |
| Demo folders | `demos/01. Investment Research/` ... `demos/10. Trend Monitoring/` |
| **Test Results** | |
| Test reports | `test_results/<timestamp>/` |

---

## Detailed Documentation

For in-depth information, see:

### Core Documentation
- [**Master Guide**](demo_testing_detailed_docs/DEMO_TESTING_MASTER_GUIDE.md) - Comprehensive testing guide with all details
- [**Testing Workflow**](demo_testing_detailed_docs/DEMO_TESTING_WORKFLOW.md) - Complete testing process and data flow

### Component Documentation
- [**Test Orchestrator**](demo_testing_detailed_docs/TEST_ALL_DEMOS_README.md) - Main test script documentation
- [**API Client**](demo_testing_detailed_docs/DEMO_CLIENT_README.md) - HTTP client for dev API
  - [Quick Start](demo_testing_detailed_docs/DEMO_API_QUICK_START.md)
- [**Session Manager**](demo_testing_detailed_docs/DEMO_SESSION_MANAGER.md) - S3 session lifecycle
  - [Quick Reference](demo_testing_detailed_docs/DEMO_SESSION_MANAGER_QUICK_REF.md)
  - [Summary](demo_testing_detailed_docs/DEMO_SESSION_MANAGER_SUMMARY.md)
- [**Test Reporter**](demo_testing_detailed_docs/DEMO_TEST_REPORTER_README.md) - Report generation
  - [Quick Reference](demo_testing_detailed_docs/DEMO_TEST_REPORTER_QUICK_REFERENCE.md)

---

## Quick Reference

### Essential Commands

```bash
# Check balance
python src/manage_dynamodb_tables.py check-balance eliyahu@eliyahu.ai

# Test single demo
cd testing && python test_all_demos.py --demos-dir ../demos --stop-on-error

# Test all demos
cd testing && python test_all_demos.py --demos-dir ../demos

# View latest report
cat test_results/*/report.txt
```

### Key Metrics

| Metric | Target |
|--------|--------|
| Success Rate | 100% (10/10) |
| Average Demo Time | < 6 minutes |
| Total Runtime | < 90 minutes |
| File Size | > 50KB each |

---

**Need Help?** See [Master Guide](demo_testing_detailed_docs/DEMO_TESTING_MASTER_GUIDE.md) for comprehensive documentation and troubleshooting
