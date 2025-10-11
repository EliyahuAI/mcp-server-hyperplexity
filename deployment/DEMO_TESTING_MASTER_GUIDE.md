# Demo Testing System - Master Guide

**Version:** 1.0
**Date:** 2025-10-10
**Author:** Demo Testing System
**Branch:** demo-testing

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Requirements](#requirements)
4. [Component Documentation](#component-documentation)
5. [Testing Workflow](#testing-workflow)
6. [Step-by-Step Testing Guide](#step-by-step-testing-guide)
7. [Validation Criteria](#validation-criteria)
8. [Troubleshooting](#troubleshooting)
9. [Success Metrics](#success-metrics)

---

## Overview

### Purpose
Automated end-to-end testing system for all 10 demo tables in the Hyperplexity Validator. Tests preview and full validation workflows, downloads results, and overwrites output files in the `demos/` directory.

### Key Features
- **Automated Testing**: Runs preview and full validation on all demos
- **Dev Environment**: Uses `hyperplexity-storage-dev` bucket and dev API
- **No Email Spam**: Configured to avoid sending emails (preview_email=false)
- **Balance Check**: Verifies account balance before starting
- **Error Handling**: Stops on first error with detailed reporting
- **Result Verification**: Downloads and validates output Excel files
- **Comprehensive Reports**: Generates text, JSON, and HTML reports

### Test Environment
- **Environment**: dev
- **API Gateway**: `https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev`
- **S3 Bucket**: `hyperplexity-storage-dev`
- **Test Email**: `eliyahu@eliyahu.ai`
- **Current Balance**: $21.00 (verified)

---

## System Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    test_all_demos.py                        │
│                  (Main Orchestrator)                        │
│  - Discovers demos                                          │
│  - Coordinates workflow                                     │
│  - Generates reports                                        │
└─────────────────┬───────────────────────────────────────────┘
                  │
        ┌─────────┼─────────┬─────────────────┐
        │         │         │                 │
        ▼         ▼         ▼                 ▼
┌───────────┐ ┌──────────┐ ┌─────────────┐ ┌──────────────┐
│   API     │ │ Session  │ │   Report    │ │    S3        │
│  Client   │ │ Manager  │ │  Generator  │ │  Storage     │
└───────────┘ └──────────┘ └─────────────┘ └──────────────┘
     │              │              │               │
     │              │              │               │
     ▼              ▼              ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│              External Dependencies                          │
│  - API Gateway (dev)                                        │
│  - Interface Lambda (dev)                                   │
│  - Validator Lambda (dev)                                   │
│  - S3 Storage (hyperplexity-storage-dev)                    │
│  - DynamoDB (shared tables)                                 │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Demo Discovery
   └─> Scan demos/ directory
       └─> Validate folder structure

2. For Each Demo:
   ├─> Load Demo (Demo Management API)
   │   └─> Copies files from demos/ to user session in S3
   │
   ├─> Preview Validation
   │   ├─> Trigger via API (processExcel?preview_first_row=true&async=true)
   │   ├─> Poll status every 10s (timeout: 5 min)
   │   └─> Verify completion
   │
   ├─> Full Validation
   │   ├─> Trigger via API (processExcel?async=false)
   │   ├─> Poll status every 30s (timeout: 30 min)
   │   └─> Verify completion
   │
   ├─> Download Results
   │   ├─> Find result file in S3 (v{N}_results/)
   │   ├─> Download enhanced_validation.xlsx
   │   └─> Overwrite demo/*_Output.xlsx
   │
   └─> Verify Integrity
       └─> Open with openpyxl to validate

3. Generate Report
   └─> Create text/JSON/HTML reports
```

---

## Requirements

### System Requirements

**Software:**
- Python 3.8+
- boto3 (AWS SDK)
- requests (HTTP client)
- openpyxl (Excel validation)
- argparse (CLI parsing)

**AWS Access:**
- AWS credentials configured (via `~/.aws/credentials` or environment)
- Read/write access to `hyperplexity-storage-dev` S3 bucket
- API Gateway invoke permissions for dev environment

**Account:**
- Validated email: `eliyahu@eliyahu.ai`
- Account balance: Minimum $2.00 (Current: $21.00)
- Domain multiplier configured (eliyahu.ai domain)

### Demo Folder Structure

Each demo folder must contain:
```
demos/
├── 01. Investment Research/
│   ├── InvestmentResearch.xlsx          # Input data file
│   ├── InvestmentResearch_config.json   # Validation config
│   ├── description.md                   # Demo description
│   └── Investment_Research_Hyperplexity_Output.xlsx  # Output (overwritten)
```

**Required Files:**
1. **Data File** - `.xlsx`, `.xls`, or `.csv`
2. **Config File** - `*_config.json` with validation configuration
3. **Description File** - `description.md` with demo metadata

---

## Component Documentation

### 1. test_all_demos.py (Main Orchestrator)

**Location:** `deployment/test_all_demos.py`

**Purpose:** Coordinates the entire testing workflow

**Key Functions:**
- `discover_demos()` - Finds all demo folders
- `validate_demo_structure()` - Checks required files exist
- `test_single_demo()` - Runs complete workflow for one demo
- `run_all_tests()` - Orchestrates all demo tests

**CLI Options:**
```bash
python test_all_demos.py [OPTIONS]

Options:
  --demos-dir PATH       Path to demos directory (default: ./demos)
  --email EMAIL          Test email (default: eliyahu@eliyahu.ai)
  --environment ENV      Target environment (default: dev)
  --output-dir PATH      Results directory (default: ./test_results)
  --stop-on-error        Stop on first error (default: True)
  --no-stop-on-error     Continue on errors
  --skip-preview         Skip preview validation step
  --skip-validation      Skip full validation step
```

### 2. demo_api_client.py (API Client)

**Location:** `deployment/demo_api_client.py`

**Purpose:** HTTP client for dev API Gateway

**Key Methods:**
- `call_demo_api(demo_name, email)` - Load demo from S3
- `trigger_preview(session_id, email)` - Start preview validation
- `trigger_full_validation(session_id, email)` - Start full validation
- `check_status(session_id)` - Poll validation status
- `get_results_info(session_id)` - Get result metadata

**Configuration:**
```python
DemoAPIClient(
    api_base='https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev',
    timeout=30,
    retries=3
)
```

### 3. demo_session_manager.py (Session Manager)

**Location:** `deployment/demo_session_manager.py`

**Purpose:** Manages S3 session lifecycle

**Key Methods:**
- `create_test_session(demo_name, email)` - Generate session ID
- `check_session_status(email, session_id)` - Check S3 session state
- `verify_results_exist(email, session_id)` - Find result files
- `download_results(email, session_id, output_path)` - Download Excel
- `cleanup_session(email, session_id)` - Remove test data

**S3 Path Structure:**
```
hyperplexity-storage-dev/
└── users/
    └── {email}/
        └── sessions/
            └── {session_id}/
                ├── session_info.json
                ├── {filename}_input.xlsx
                ├── config_v1_demo.json
                └── v1_results/
                    ├── enhanced_validation.xlsx
                    └── validation_results.json
```

### 4. demo_test_reporter.py (Report Generator)

**Location:** `deployment/demo_test_reporter.py`

**Purpose:** Generates comprehensive test reports

**Key Methods:**
- `create_report(email, environment)` - Initialize report
- `add_demo_result(report, demo_name, result_data)` - Add test result
- `generate_summary(report)` - Calculate statistics
- `save_report(report, output_dir, format)` - Save to file
- `print_report(report)` - Display in console

**Output Formats:**
- **TEXT**: Console-friendly ASCII report
- **JSON**: Machine-readable structured data
- **HTML**: Rich web interface with styling

---

## Testing Workflow

### Phase 1: Pre-Test Validation

**Steps:**
1. Check branch: `git branch` (should show `demo-testing`)
2. Verify balance: `python src/manage_dynamodb_tables.py check-balance eliyahu@eliyahu.ai`
3. List demos: `ls demos/` (should show 10 folders)
4. Verify API connectivity: `python deployment/demo_api_client.py list`

**Expected Output:**
```
Current Branch: demo-testing
Current Balance: $21.0000
Demo Count: 10
API Status: Connected
```

### Phase 2: Single Demo Test (Validation)

**Purpose:** Validate system with one demo before full run

**Commands:**
```bash
# Test single demo
python deployment/test_all_demos.py \
  --demos-dir demos/ \
  --output-dir test_results/single_test \
  --stop-on-error

# Should test only first demo found
```

**Expected Results:**
- Demo loaded successfully from S3
- Preview completes in < 5 minutes
- Full validation completes in < 10 minutes
- Results downloaded to `test_results/single_test/`
- Output file overwritten in `demos/01. Investment Research/`

**Validation Checks:**
- [ ] Session created in S3
- [ ] Preview results generated
- [ ] Full validation results generated
- [ ] Excel file downloaded
- [ ] File size > 0 bytes
- [ ] openpyxl can open file
- [ ] Report generated in all formats

### Phase 3: Full Test Run

**Purpose:** Test all 10 demos end-to-end

**Commands:**
```bash
# Run complete test suite
python deployment/test_all_demos.py \
  --demos-dir demos/ \
  --output-dir test_results/full_run \
  --stop-on-error \
  --email eliyahu@eliyahu.ai \
  --environment dev
```

**Expected Duration:**
- Preview Phase: ~8-10 minutes (45-60s per demo)
- Validation Phase: ~30-50 minutes (3-5 min per demo)
- Total: ~40-60 minutes

**Progress Monitoring:**
```
[1/10] Testing: 01. Investment Research
  [LOAD] Loading demo from S3... SUCCESS (2.3s)
  [PREVIEW] Running preview validation... SUCCESS (48.5s)
  [VALIDATE] Running full validation... SUCCESS (4.2 min)
  [DOWNLOAD] Downloading results... SUCCESS (1.8s)
  [VERIFY] Verifying file integrity... SUCCESS

[2/10] Testing: 02. Competitive Intelligence
  ...
```

### Phase 4: Result Verification

**Steps:**
1. Check test report: `cat test_results/full_run/report.txt`
2. Verify all demos passed: Look for `Passed: 10/10`
3. Check output files updated: `ls -lh demos/*/\*Output.xlsx`
4. Validate file sizes: All files should be > 50KB
5. Spot-check Excel files: Open 2-3 files in Excel/LibreOffice

---

## Step-by-Step Testing Guide

### Test 1: Environment Setup Verification

**Goal:** Confirm system is ready for testing

```bash
# 1. Check branch
git branch
# Expected: * demo-testing

# 2. Verify Python dependencies
python -c "import boto3, requests, openpyxl; print('OK')"
# Expected: OK

# 3. Check AWS credentials
aws sts get-caller-identity
# Expected: Valid AWS account info

# 4. Verify S3 access
aws s3 ls s3://hyperplexity-storage-dev/demos/ | head -5
# Expected: List of demo folders

# 5. Check account balance
python src/manage_dynamodb_tables.py check-balance eliyahu@eliyahu.ai
# Expected: Balance >= $2.00
```

**Pass Criteria:**
- ✅ All commands execute without errors
- ✅ Balance shows $21.00 or more
- ✅ S3 bucket accessible

### Test 2: Component Unit Tests

**Goal:** Verify each component works independently

```bash
# 1. Test API Client
python deployment/demo_api_client.py list
# Expected: Lists available demos

# 2. Test Session Manager
python deployment/demo_session_manager.py list --email eliyahu@eliyahu.ai
# Expected: Lists existing sessions

# 3. Test Reporter
python -c "from deployment.demo_test_reporter import create_report, print_report; r = create_report('test@test.com', 'dev'); print_report(r)"
# Expected: Prints empty report template
```

**Pass Criteria:**
- ✅ API client connects to dev environment
- ✅ Session manager accesses S3
- ✅ Reporter generates output

### Test 3: Single Demo Integration Test

**Goal:** End-to-end test with one demo

```bash
# Run test on first demo only
python deployment/test_all_demos.py \
  --demos-dir demos/ \
  --output-dir test_results/integration_test \
  --stop-on-error
```

**Monitor Output:**
```
[1/1] Testing: 01. Investment Research
  [LOAD] Loading demo from S3...
  [PREVIEW] Running preview validation...
  [VALIDATE] Running full validation...
  [DOWNLOAD] Downloading results...
  [VERIFY] Verifying file integrity...

Test Results:
  Total: 1
  Passed: 1
  Failed: 0
  Duration: 5.2 minutes
```

**Pass Criteria:**
- ✅ Demo loads successfully
- ✅ Preview completes without errors
- ✅ Full validation completes without errors
- ✅ Results downloaded
- ✅ Output file overwritten
- ✅ Report generated

### Test 4: Full Suite Test

**Goal:** Test all 10 demos

```bash
# Run complete test suite
python deployment/test_all_demos.py \
  --demos-dir demos/ \
  --output-dir test_results/full_suite \
  --stop-on-error \
  --email eliyahu@eliyahu.ai
```

**Expected Timeline:**
```
00:00 - Test Start
00:01 - Demo 1: Load
00:02 - Demo 1: Preview
00:05 - Demo 1: Validate
00:10 - Demo 1: Complete
00:11 - Demo 2: Load
...
00:60 - All Tests Complete
```

**Pass Criteria:**
- ✅ All 10 demos tested
- ✅ 10/10 passed
- ✅ 0 failures
- ✅ All output files updated
- ✅ Report generated in all formats

### Test 5: Error Recovery Test

**Goal:** Verify error handling works

```bash
# Test with invalid demo (should fail gracefully)
python deployment/test_all_demos.py \
  --demos-dir demos/ \
  --stop-on-error
# Temporarily rename a config file to cause error
```

**Pass Criteria:**
- ✅ Error detected and reported
- ✅ Test stops if --stop-on-error is set
- ✅ Error details in report
- ✅ No crash or exception

---

## Validation Criteria

### Per-Demo Validation

Each demo must pass these checks:

**1. Load Phase**
- [ ] Demo found in `demos/` folder
- [ ] All 3 required files present (data, config, description)
- [ ] Demo loaded successfully via API
- [ ] Session ID returned
- [ ] Session created in S3

**2. Preview Phase**
- [ ] Preview triggered successfully
- [ ] Preview completes within 5 minutes
- [ ] Preview status = "COMPLETED"
- [ ] Preview results stored in S3
- [ ] No errors in preview response

**3. Validation Phase**
- [ ] Validation triggered successfully
- [ ] Validation completes within 30 minutes
- [ ] Validation status = "COMPLETED"
- [ ] Validation results stored in S3
- [ ] No errors in validation response

**4. Download Phase**
- [ ] Result file found in S3
- [ ] File downloaded successfully
- [ ] File size > 0 bytes
- [ ] File overwrites existing output
- [ ] Downloaded file is valid Excel format

**5. Verification Phase**
- [ ] openpyxl can open file
- [ ] File contains expected sheets
- [ ] No corruption detected

### Overall Test Validation

The complete test run must meet:

**Success Metrics:**
- [ ] 10/10 demos tested
- [ ] 10/10 demos passed
- [ ] 0 failures
- [ ] Total time < 90 minutes
- [ ] All output files updated
- [ ] Report generated successfully

**Report Validation:**
- [ ] TEXT report exists and is readable
- [ ] JSON report is valid JSON
- [ ] HTML report opens in browser
- [ ] All demo results in report
- [ ] Summary statistics correct
- [ ] Error details (if any) complete

**File System Validation:**
```bash
# Check all output files updated
find demos/ -name "*Output.xlsx" -mmin -120 | wc -l
# Expected: 10 (all files modified in last 2 hours)

# Check file sizes reasonable
find demos/ -name "*Output.xlsx" -size +50k | wc -l
# Expected: 10 (all files > 50KB)
```

---

## Troubleshooting

### Common Issues

#### Issue 1: API Connection Failure

**Symptoms:**
```
[ERROR] Failed to connect to API: Connection timeout
```

**Diagnosis:**
```bash
# Check API connectivity
curl -I https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev/health

# Check AWS credentials
aws sts get-caller-identity
```

**Solution:**
- Verify internet connection
- Check AWS credentials configured
- Confirm API Gateway endpoint correct
- Try manual curl to test connectivity

#### Issue 2: Insufficient Balance

**Symptoms:**
```
[ERROR] Insufficient account balance: $1.50 < $2.00
```

**Diagnosis:**
```bash
python src/manage_dynamodb_tables.py check-balance eliyahu@eliyahu.ai
```

**Solution:**
```bash
# Add balance
python src/manage_dynamodb_tables.py add-balance eliyahu@eliyahu.ai 25.00
```

#### Issue 3: Demo Load Failure

**Symptoms:**
```
[ERROR] Demo not found in S3: competitive_intelligence
```

**Diagnosis:**
```bash
# Check S3 demos
aws s3 ls s3://hyperplexity-storage-dev/demos/

# Verify demo folder structure
ls -la demos/
```

**Solution:**
- Verify demo exists in `demos/` directory
- Check demo name format (spaces vs underscores)
- Upload demo to S3 if missing: `python deployment/upload_demos.py --bucket hyperplexity-storage-dev --upload`

#### Issue 4: Validation Timeout

**Symptoms:**
```
[ERROR] Validation timeout after 30 minutes
```

**Diagnosis:**
- Check DynamoDB for run status
- Check CloudWatch logs for errors
- Verify validator lambda is running

**Solution:**
- Increase timeout: `--validation-timeout 45`
- Check lambda not hitting memory limits
- Verify no stuck async processes

#### Issue 5: Download Failure

**Symptoms:**
```
[ERROR] Result file not found in S3
```

**Diagnosis:**
```bash
# Check session in S3
python deployment/demo_session_manager.py verify \
  --email eliyahu@eliyahu.ai \
  --session-id SESSION_ID
```

**Solution:**
- Verify validation actually completed
- Check correct S3 path format
- Verify S3 read permissions
- Look for result in different version folder

---

## Success Metrics

### Quantitative Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Success Rate | 100% (10/10) | Passed demos / Total demos |
| Average Demo Time | < 6 minutes | Total time / 10 |
| Preview Success | 100% | Preview completions / Attempts |
| Validation Success | 100% | Validation completions / Attempts |
| Download Success | 100% | Downloads / Validation completions |
| Total Runtime | < 90 minutes | Start to finish time |
| File Size | > 50KB each | Size of downloaded files |
| API Response Time | < 5s | Average API response time |

### Qualitative Metrics

- [ ] **Code Quality**: All components follow Python best practices
- [ ] **Documentation**: Comprehensive docs for all components
- [ ] **Error Handling**: Graceful failure with informative messages
- [ ] **User Experience**: Clear progress indicators and feedback
- [ ] **Maintainability**: Code is clean and well-structured
- [ ] **Reliability**: Tests can be run repeatedly with same results
- [ ] **Performance**: Efficient use of API and S3 resources

### Acceptance Criteria

**The system is considered successful if:**

1. ✅ All 10 demos pass validation
2. ✅ No errors or exceptions thrown
3. ✅ All output files updated with valid Excel data
4. ✅ Complete reports generated in all 3 formats
5. ✅ Total runtime under 90 minutes
6. ✅ Account balance remains sufficient ($21 → ~$19)
7. ✅ No emails sent to user (preview_email=false working)
8. ✅ System can be re-run for regression testing
9. ✅ Documentation is complete and accurate
10. ✅ Code is committed to `demo-testing` branch

---

## Next Steps

### After Successful Testing

1. **Review Results**
   - Check all demo output files
   - Verify report accuracy
   - Spot-check Excel files for data quality

2. **Documentation**
   - Update any issues found
   - Document any workarounds
   - Record performance metrics

3. **Code Review**
   - Review all component code
   - Check for improvements
   - Ensure best practices followed

4. **Integration**
   - Merge `demo-testing` branch to `develop`
   - Tag release version
   - Update changelog

5. **Automation**
   - Add to CI/CD pipeline
   - Schedule regular regression runs
   - Set up monitoring alerts

### Future Enhancements

- [ ] Parallel demo testing (run multiple demos concurrently)
- [ ] Webhook notifications for completion
- [ ] Slack/Discord integration for alerts
- [ ] Historical trend analysis
- [ ] Automated comparison with previous runs
- [ ] Performance benchmarking
- [ ] Cost optimization analysis
- [ ] Integration with monitoring dashboards

---

## Quick Reference Card

### Essential Commands

```bash
# Check balance
python src/manage_dynamodb_tables.py check-balance eliyahu@eliyahu.ai

# List available demos
python deployment/demo_api_client.py list

# Test single demo
python deployment/test_all_demos.py --demos-dir demos/ --stop-on-error

# Test all demos
python deployment/test_all_demos.py

# View latest report
cat test_results/*/report.txt

# Check output files
ls -lh demos/*/\*Output.xlsx
```

### File Locations

| Component | Path |
|-----------|------|
| Orchestrator | `deployment/test_all_demos.py` |
| API Client | `deployment/demo_api_client.py` |
| Session Manager | `deployment/demo_session_manager.py` |
| Reporter | `deployment/demo_test_reporter.py` |
| Master Guide | `deployment/DEMO_TESTING_MASTER_GUIDE.md` |
| Demo Folders | `demos/01. Investment Research/` ... `demos/10. Trend Monitoring/` |
| Test Results | `test_results/<timestamp>/` |

### Key URLs

- Dev API: `https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev`
- S3 Bucket: `s3://hyperplexity-storage-dev`
- CloudWatch Logs: `/aws/lambda/perplexity-validator-interface-dev`

---

**End of Master Guide**

For detailed component documentation, see:
- `TEST_ALL_DEMOS_README.md` - Orchestrator docs
- `DEMO_API_CLIENT_README.md` - API client docs
- `DEMO_SESSION_MANAGER.md` - Session manager docs
- `DEMO_TEST_REPORTER_README.md` - Reporter docs
