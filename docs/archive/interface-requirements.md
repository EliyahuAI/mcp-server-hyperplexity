Here’s the revised concise project document, integrating your latest requirements:

---

# **Table Validation Tool: Lambda Interface & Markdown Preview**

## **Overview**

This project migrates Excel table validation to a new AWS Lambda function (`perplexity-validator-interface`), with automated deployment, a Markdown preview feature, and an API Gateway interface.
Each milestone includes a confirming test case.

---

## **Requirements**

### **Lambda Excel Validation Interface**

* **Lambda Function:** `perplexity-validator-interface`

  * Accepts:

    * Excel file and config file (multipart/form-data or S3 reference)
    * Arguments: `max_rows`, `batch_size`, `preview_first_row` (boolean)
  * **Normal workflow** (`preview_first_row=False`):

    * Upload files to S3, return immediate download link (placeholder zip: `Still_Processing.zip`) and password.
    * After processing, overwrite with actual results.
  * **Preview workflow** (`preview_first_row=True`):

    * Wait, process only the first row.
    * Return a Markdown table for the first row (no S3 link).
    * **Estimate Total Processing Time:**
      If a single row is processed, use the number of total rows in the input and the time for one row to estimate and include the total expected processing time in the response.

### **Markdown Table Preview**

* **Returned when `preview_first_row=True`:**

  * Table columns: `Field | Confidence | Value`

    * **Confidence:** Use the value provided directly from the validator, do not map.
    * **Value:** Wide column for long field content.
  * **Example:**

    ```
    | Field   | Confidence | Value                     |
    |---------|------------|--------------------------|
    | Name    | 0.97       | John Smith               |
    | Email   | 0.82       | john.smith@example.com   |
    | Phone   | 0.61       | (555) 123-4567           |
    ```
  * **Also include:**

    * Total number of rows.
    * Time to process first row.
    * Estimated total processing time (`estimated_time = total_rows * time_for_one_row`).

### **Deployment Automation**

* **Packaging Script:**

  * Create a new deployment script for this Lambda, modeled after the existing `deployment/create_package.py`.
  * Script should:

    * Bundle Lambda source and dependencies.
    * Optionally deploy to AWS or output a deployment package.
    * Update environment/configs as needed.
    * Log deployment actions.
  * **Reference:** Existing `deployment/create_package.py`.

### **API Gateway Integration**

* **API Gateway Setup:**

  * Automatically provision an API Gateway (via deployment script or IaC).
  * API Gateway should expose an endpoint to interface with the Lambda function.
  * Ensure CORS and security settings are appropriate.

### **CLI/UX Updates**

* Update CLI/local tool to:

  * Support new API parameters, including `preview_first_row`.
  * Display Markdown table and time estimate if returned, or S3 link and password as before.

### **Security**

* Password-protect download links (e.g., zip with password).
* Use pre-signed S3 URLs with limited access.

---

## **Iterative Development Plan & Test Cases**

### **Milestone 1: Lambda Packaging, API Gateway & Deployment**

* **Goal:** New deployment script for `perplexity-validator-interface` Lambda, modeled after `deployment/create_package.py`, including automated API Gateway setup.
* **Test Case:** Deploy Lambda and API Gateway, invoke with a test event through the API, confirm successful execution and correct routing.

---

### **Milestone 2: Lambda API & S3 Workflow**

* **Goal:** Lambda accepts files and parameters, implements S3 placeholder workflow.
* **Test Case:** Upload test file via API, receive placeholder link, and verify the link updates with the final result after processing.

---

### **Milestone 3: Markdown Table Preview Feature with Time Estimation**

* **Goal:** Add `preview_first_row` param and Markdown output logic, including time estimation.
* **Test Case:** API call with `preview_first_row=True` returns Markdown table, total row count, first-row timing, and estimated total processing time.

---

### **Milestone 4: CLI & UX Updates**

* **Goal:** Update CLI/local tool for both normal and preview workflows.
* **Test Case:** Run CLI in both modes, confirm display of the S3 link/password (normal) and Markdown table plus time estimate (preview).

---

### **Milestone 5: QA, Security & Edge Cases**

* **Goal:** Handle empty or invalid input, enforce password security, finalize S3 and API Gateway access policy.
* **Test Case:** Process edge-case files, verify error handling, password enforcement, and secure S3/API Gateway access.

---

## **Acceptance Criteria**

* Each milestone includes and passes its designated test case.
* Both normal and preview workflows meet requirements, including time estimation in preview mode.
* CLI and Lambda workflows are documented and reproducible.
* API Gateway endpoint is set up, documented, and secure.


