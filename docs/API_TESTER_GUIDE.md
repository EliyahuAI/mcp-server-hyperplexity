# Hyperplexity API — Human Tester Guide

You are testing whether someone handed only the API guide (`docs/API_GUIDE.md`)
can successfully follow it and use the Hyperplexity API. Your job is not to
verify that the API works technically — it is to verify that the **guide is
clear, complete, and followable** by a new user.

---

## Credentials

```
API Key:      hpx_live_r0GWnJjjCHBKWP45ZzZkB28_MvUBREuOJfTLb4Mm
Dev Endpoint: https://07w4n09m95.execute-api.us-east-1.amazonaws.com/v1
```

Set these before running any example scripts:

```bash
export HYPERPLEXITY_API_KEY=hpx_live_r0GWnJjjCHBKWP45ZzZkB28_MvUBREuOJfTLb4Mm
export HYPERPLEXITY_API_URL=https://07w4n09m95.execute-api.us-east-1.amazonaws.com/v1
```

---

## Your Role

Read the guide as a **first-time user**. For each test below, attempt to follow
the guide's instructions without help. Note every moment where you:

- Were confused or unsure what to do next
- Had to guess at something the guide didn't explain
- Got an unexpected result compared to what the guide described
- Got an error and couldn't tell what it meant

These observations are the primary output of this test. A "pass" with confusion
along the way is still a finding worth reporting.

---

## Setup

Requirements: Python 3.10+ and `pip install requests`

Download the example scripts as described in the guide under **Download
Examples**. You should end up with:
- `hyperplexity_client.py`
- `01_validate_table.py`
- `02_generate_table.py`
- `03_update_table.py`
- `04_reference_check.py`

**First question for your report:** Was the download step clear from the guide?
Did the curl command work as shown?

---

## Test 1 — Verify Your API Key Works

Before anything else, confirm the key and endpoint are working by checking your
account balance. The guide documents this under **Account** in the API Endpoint
Reference section:

```bash
curl -s https://07w4n09m95.execute-api.us-east-1.amazonaws.com/v1/account/balance \
  -H "Authorization: Bearer hpx_live_r0GWnJjjCHBKWP45ZzZkB28_MvUBREuOJfTLb4Mm"
```

**What you should see:** A JSON response with `"success": true`, your email
address, and a credit balance above $0.

**Report:**
- Did it work on the first try?
- Was it clear from the guide how to construct this request (auth header format,
  base URL, path)?
- Did the response match what the guide describes?

---

## Test 2 — Fact-Check Text (Reference Check)

Follow **Workflow 4** in the guide ("Fact-Check Text or Documents").

Run the example script with a short piece of text you want to fact-check:

```bash
python 04_reference_check.py --text "Albert Einstein was born in Germany in 1879. \
The Amazon River is the longest river in the world."
```

Reference check has a **two-phase flow** (documented in the guide under Workflow 4):
- Phase 1 (claim extraction) is free and runs automatically, stopping at `preview_complete`
- The script then shows a claims summary and cost estimate, and asks you to approve
- Phase 2 (validation, charged) runs after approval

**What you should see:**
1. The script submits the job and polls until `preview_complete`
2. A summary of detected claims and estimated cost appear
3. You are asked to approve — type `yes` to trigger Phase 2
4. After Phase 2 completes, it prints download URLs including an **Excel (.xlsx)** file
5. Open the Excel — it should contain one row per claim with columns including
   `Statement`, `Support Level`, and `Validation Notes`

**Report:**
- Was the two-phase flow (Phase 1 free → pause → Phase 2 charged) clearly explained
  in the guide? Or did the script pausing at `preview_complete` seem unexpected?
- Did the script output match what the guide described?
- Did you get an XLSX with populated validation columns (Support Level, sources,
  notes)? Or were those columns empty?
- Was the output format (XLSX, not CSV) explained clearly enough in the guide?
- Did the guide explain whether this workflow has a cost? Was anything charged?
- **Key question:** Did Phase 2 actually complete after you approved? If the job
  stayed stuck at `preview_complete` indefinitely, that is a known bug — report it.

---

## Test 3 — Generate a Table from a Prompt

Follow **Workflow 2** in the guide ("Generate a Table from a Prompt").

Run the generate table script with your own prompt describing a table you want:

```bash
python 02_generate_table.py --auto-start \
  "Top 5 pharmaceutical companies: company name, annual revenue, HQ city, founding year, CEO"
```

The `--auto-start` flag skips clarifying questions — use it if your prompt is
specific enough that no Q&A is needed.

**What you should see:**
1. The script starts a table-maker session and waits for the table to build
2. It pauses at a **preview** showing the first 3 rows with confidence indicators
3. It shows an estimated cost and asks you to type `yes` to approve
4. After approval, it runs full validation and prints result URLs

**Report:**
- Was it clear from the guide when to use `--auto-start` vs. not?
- Did the preview table appear as described? Did the confidence indicators
  (colored circles) make sense?
- Was the cost estimate present and reasonable?
- After completion, did you receive:
  - A download link for an **Excel file** (.xlsx)?
  - A link to an **interactive viewer** (open it in a browser — you'll need to
    log in with the account email `eliyahu@eliyahu.ai`)?
  - A `metadata_url` link to a `table_metadata.json` file?
- Open the Excel file. Do the cells contain citation comments? Are they readable?
- Open `metadata.json` from the `metadata_url`. Can you find `rows[].row_key` and
  match a row from the markdown preview table to its per-cell citations in the JSON?
- **Key question:** The guide describes `metadata.json` as having a `row_key` field
  that lets you drill into per-row citations. Was this explained clearly enough that
  you would know how to use it without outside help?

---

## Test 4 — Upload and Validate an Existing Table

Follow **Workflow 1** in the guide ("Validate an Existing Table").

Create a small CSV file with a few rows of data you want validated. For example,
save this as `my_table.csv`:

```
Company,Founded,CEO,HQ City
Apple,1976,Tim Cook,Cupertino
Microsoft,1975,Satya Nadella,Redmond
Google,1999,Sundar Pichai,Mountain View
```

Then run:

```bash
python 01_validate_table.py my_table.csv \
  --instructions "This table lists major tech companies. Validate founding year, current CEO, and HQ city."
```

The `--instructions` flag skips the AI interview. Without it, the AI will ask
you questions about your table before generating a validation config.

**What you should see:**
1. File uploads and the config generates automatically from your instructions
2. A preview table appears with confidence indicators for the first 3 rows
3. You are asked to approve the full validation cost
4. Full results are returned with the same three output URLs as Test 3

**Report:**
- Was the upload flow clear from the guide? Did the two-step upload (presigned
  URL → confirm) make sense?
- Did `--instructions` successfully skip the interview as described?
- Did the validator catch any errors in your data? Were corrections well-explained
  with citations?
- Were the three output URLs (Excel, viewer, metadata) all present?
- **Key question:** The guide describes config reuse — if you upload the same
  table a second time, a matching config is detected and the preview is
  auto-queued immediately (no interview, no manual step). Try running the script
  again on the same file. Did the guide explain this clearly enough that you'd
  know what to expect?

---

## Test 5 — Re-run Validation (Update Table)

Follow **Workflow 3** ("Update a Table"). Use the job ID from Test 4 or Test 3.

```bash
python 03_update_table.py <session_id_from_previous_test>
```

**What you should see:** The same table re-validated with fresh source data.
Preview appears, you approve, full results returned.

**Report:**
- Was it clear from the guide what `update_table` does and when you'd use it?
- Did any values change between the original run and the update?
- Did you receive the same three output URLs?

---

## Test 6 — Below-Minimum Inputs

The guide warns that Hyperplexity is designed for tables with **4 or more data rows**
and text with **4 or more factual claims**, and says fewer "may produce low-quality
results." This test checks what actually happens — does it error, warn, silently
degrade, or produce surprisingly good output?

### 6a — Table with 2 data rows

Create a small CSV with only 2 data rows (below the stated 4-row minimum):

```
Company,Founded,HQ City
Apple,1976,Cupertino
Microsoft,1975,Redmond
```

Save it as `tiny_table.csv` and run:

```bash
python 01_validate_table.py tiny_table.csv \
  --instructions "This table lists tech companies. Validate founding year and HQ city."
```

**What you might see (you tell us):**
- An error at upload, confirm, or job creation
- A warning in the response but the job proceeds
- Normal flow — preview and full results returned with 2 rows

**Report:**
- At what step did the failure or warning occur, if any?
- Was the error message clear about what was wrong and what to do?
- If it proceeded: did the preview and full validation complete correctly?
- Does the guide's warning ("may produce low-quality results") match what you experienced,
  or should the guide be more explicit about the actual behavior?

### 6b — Reference check with 2 claims

Submit a text with only 2 factual claims (below the stated 4-claim minimum):

```bash
python 04_reference_check.py --text \
  "The Eiffel Tower is located in Paris. It was completed in 1889."
```

**What you might see (you tell us):**
- An error at submission or claim extraction
- A warning but Phase 1 completes with 2 claims extracted
- Normal two-phase flow — 2 claims validated, results returned

**Report:**
- At what step did the failure or warning occur, if any?
- Was the error message clear about what was wrong and what to do?
- If it proceeded: were both claims validated correctly in the output?
- Does the guide's wording adequately prepare a user for what actually happens?

---

## How to Report Findings

For each test, write a short note covering:

1. **Followed without issues** — steps that were clear and worked as described
2. **Had to guess** — anything the guide left ambiguous or didn't explain
3. **Unexpected result** — output that didn't match the guide's description
4. **Bug or error** — something that failed or returned an error

Use this format for each finding:

```
Test: [1–5]
Type: [Clear / Had to guess / Unexpected result / Bug]
Step: [what you were doing]
Expected: [what the guide led you to expect]
Actual: [what happened]
Severity: [Blocking / High / Medium / Low]
```

---

## Where to Copy Your Findings

Save your report as a markdown file and copy it to:

```
C:\Users\ellio\OneDrive - Eliyahu.AI\Desktop\src\perplexityValidator\docs\
```

Name it `API_TEST_FINDINGS_<your_name>_<date>.md` — for example:
`API_TEST_FINDINGS_Sarah_20260306.md`

Also update the existing `docs/API_TEST_FINDINGS.md` by appending a new session
section at the bottom following the same format as the existing sessions.

---

## Things to Pay Special Attention To

These are known areas of uncertainty — your observations here are especially valuable:

- **Reference check output format:** Does the guide adequately explain that the
  result is an **Excel (.xlsx)** download (not CSV, not inline JSON)? Is the
  column schema documented clearly enough?
- **Reference check two-phase flow:** Does the guide make it clear that Phase 1
  (claim extraction) is free and pauses for approval before Phase 2 (validation,
  charged) runs? Or did the pause seem unexpected?
- **Reference check Phase 2 completion:** Did Phase 2 actually run to completion
  after you approved? Note if the job stayed stuck at `preview_complete`.
- **`row_key` explanation:** Does the guide explain clearly enough how to use
  `rows[].row_key` to connect the markdown preview table to `metadata.json`
  per-row citations? Could you do it without outside help?
- **Interactive viewer:** Does the guide tell you who can access it and what
  login is required?
- **Cost gate:** Was it always clear before approving exactly how much would be
  charged and what you were approving?
- **Config reuse (auto-preview):** When you re-upload the same file, the guide
  says a match is detected and the preview is auto-queued immediately. Did this
  work as described? Was the behavior clearly explained?
