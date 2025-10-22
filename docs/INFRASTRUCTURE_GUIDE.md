# Hyperplexity Validator Infrastructure Guide

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Infrastructure Components](#infrastructure-components)
3. [Setup Guide](#setup-guide)
4. [Workflow Overview](#workflow-overview)
5. [Table Maker System](#table-maker-system)
6. [Testing Guide](#testing-guide)
7. [Troubleshooting](#troubleshooting)

## Architecture Overview

The Hyperplexity Validator is a serverless application that validates and enriches Excel data using AI. It has been refactored into a three-lambda architecture to separate concerns and improve maintainability. The system is designed around a conversational interface that allows users to generate and refine validation configurations using natural language.

### Request Flow

The primary interaction flow is as follows:

```
Client → API Gateway → Interface Lambda → (User Interaction)
                             ↓
                       Config Lambda (for AI config generation/refinement)
                             ↓
                     Validation Lambda (for preview and full processing) → S3/Email
```
A WebSocket connection is established for real-time progress updates during long-running operations.

### Key Design Decisions

- **Three-Lambda Architecture**: Separation of concerns between the user-facing interface, configuration management, and core validation logic.
- **Unified S3 Storage**: A single, well-structured S3 bucket (`hyperplexity-storage`) simplifies data management and access control.
- **Conversational AI**: Users can interact with the system in natural language to create and modify complex validation rules.
- **DynamoDB Tracking**: Comprehensive session tracking, user stats, and validation metrics.
- **WebSocket Integration**: Provides real-time feedback to the user during asynchronous operations.

## Infrastructure Components

### 1. API Gateway
- **Endpoint**: `https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod`
- **Integration**: Acts as a proxy for the Interface Lambda, which handles all incoming HTTP requests.

### 2. Lambda Functions

#### Interface Lambda (`src/lambdas/interface`)
- **Responsibilities**:
  - Handles all API Gateway requests.
  - Manages user sessions and email validation.
  - Orchestrates the workflow between the user, the Config Lambda, and the Validation Lambda.
  - Manages WebSocket connections for real-time updates.

#### Config Lambda (`src/lambdas/config`)
- **Responsibilities**:
  - Handles all aspects of AI-powered configuration generation.
  - Interprets user instructions to create and refine validation rules.
  - Interacts with the AI model (e.g., Anthropic's Claude) to produce structured configuration files.

#### Validation Lambda (`src/lambdas/validation`)
- **Responsibilities**:
  - Executes the core data validation logic based on a given configuration.
  - Processes Excel files in batches.
  - Performs data enrichment by calling external AI APIs.
  - Generates preview results and final validation reports.

### 3. S3 Bucket (`hyperplexity-storage`)
A single bucket organized as follows:
- `results/{domain}/{email_prefix}/{session_id}/`: Stores all session-related artifacts, including uploaded files, generated configs, and validation results. (1-year retention)
- `downloads/{uuid}/`: Temporary public storage for downloadable files like configs. (7-day retention)
- `cache/{service}/{hash}/`: Caches AI API responses to reduce cost and latency. (30-day retention)

### 4. DynamoDB Tables
The system uses several DynamoDB tables to manage validation sessions, user data, and more. For a detailed schema of each table, see `docs/DYNAMODB_TABLES.md`.

**Core Tables:**
- **`perplexity-validator-runs`**: Modern session tracking with real-time progress updates.
- **`perplexity-validator-user-tracking`**: Aggregates user analytics and lifetime usage statistics.
- **`perplexity-validator-user-validation`**: Manages the email verification workflow.
- **`perplexity-validator-account-transactions`**: Provides a financial audit trail for credit purchases and deductions.
- **`perplexity-validator-domain-multipliers`**: Stores domain-specific cost multipliers for pricing.
- **`perplexity-validator-ws-connections`**: Manages WebSocket connections for real-time progress updates.
- **`perplexity-validator-batch-audit`**: Audit log for dynamic batch size changes.
- **`perplexity-validator-model-config`**: Centralized model configuration management.

**Legacy Tables:**
- **`perplexity-validator-call-tracking`**: Legacy session tracking (cleared and unused).
- **`perplexity-validator-token-usage`**: Legacy token usage tracking (empty and unused).

## Setup Guide

### Prerequisites
- AWS CLI configured
- Python 3.9+
- Git repository cloned
- Perplexity and/or Anthropic API key

### Step 1: Store API Keys in SSM
Store your AI service API keys in AWS Systems Manager Parameter Store as `SecureString` values.
- `/Perplexity_API_Key`
- `/Anthropic_API_Key`

### Step 2: Deploy All Lambdas
A unified deployment script has been created to simplify the deployment process.

```bash
# Run the deployment script from the project root
./deploy_all.sh
```
This script will:
- Build the deployment package for each lambda (Interface, Config, and Validation).
- Include the shared code from `src/shared` in each package.
- Create or update the Lambda functions and their configurations.

### Step 3: Verify Deployment
Check the AWS console to ensure that the three Lambda functions (`...-interface`, `...-config`, `...-validation`) and the API Gateway have been deployed or updated successfully.

## Workflow Overview

The primary user workflow is as follows:
1.  **Email Validation**: The user validates their email address to start a session.
2.  **File Upload**: The user uploads an Excel or CSV file.
3.  **Configuration**: The user chooses one of three paths:
    - **Use a Recent Config**: If a matching configuration from a previous session is found, it can be used directly.
    - **Upload a Config**: The user can upload a pre-existing JSON configuration file.
    - **Create with AI**: The user provides natural language instructions, and the **Config Lambda** generates a new configuration.
4.  **Refinement (Optional)**: The user can refine the AI-generated configuration by providing further instructions.
5.  **Preview**: The **Validation Lambda** runs a quick validation on the first few rows of the table and returns a preview with cost and time estimates.
6.  **Full Processing**: Upon approval, the **Validation Lambda** processes the entire table asynchronously.
7.  **Results**: The results are delivered to the user via email and stored in the S3 bucket.

## Table Maker System

The **Table Maker** is an independent system integrated into the Interface Lambda that generates research tables by discovering entities through web search and validating them through progressive model escalation and quality control.

### Purpose

Creates research tables from natural language requests (e.g., "Track AI companies that are hiring") by:
1. Defining column structure and search strategy
2. Discovering entities through progressive web search escalation
3. Validating and prioritizing results through QC review
4. Generating CSV templates and validation configs

### Architecture

The Table Maker uses a **4-step pipeline**:

```
Column Definition → Row Discovery (+ Config Gen) → QC Review → CSV + Config Output
     (10-40s)           (60-120s parallel)          (8-15s)       (instant)
```

**Key Features:**
- **Progressive Escalation**: Start cheap (sonar), escalate if needed (sonar-pro)
- **Parallel Config Generation**: Validation config generated during row discovery
- **Quality Over Quantity**: QC layer ensures relevance, no artificial row limits
- **Cost Optimization**: Early stopping when targets met ($0.05-0.20 per table)

### Integration Points

**Location:** `src/lambdas/interface/actions/table_maker/`

**Entry Points:**
- `conversation.py` - Interview and conversation management
- `execution.py` - Main pipeline orchestrator

**Local Components:** `table_maker/src/`
- Used directly in Lambda (no modifications)
- Tested independently before Lambda integration

### Documentation

**Primary Guide:** [TABLE_MAKER_GUIDE.md](TABLE_MAKER_GUIDE.md)

**Detailed Documentation:**
- Architecture: `table_maker/architecture/overview.md`
- Deployment: `table_maker/deployment/lambda_integration.md`
- Configuration: `table_maker/configuration/`

### Quick Start

**Local Testing:**
```bash
cd table_maker
export ANTHROPIC_API_KEY="sk-ant-..."
python test_local_e2e_sequential.py
```

**Lambda Flow:**
1. User requests table via conversational interface
2. Interview phase gathers requirements
3. Execution phase (1-3 minutes):
   - Column definition
   - Row discovery (parallel with config generation)
   - QC review
   - CSV + config output
4. User receives CSV template with ID columns filled

## Testing Guide

- **Unit and Integration Tests**: All tests have been moved to the `tests/` directory. These can be run to verify the functionality of individual components.
- **End-to-End Testing**: After deployment, perform a full workflow test using the web interface to ensure all components are working together correctly.

## Troubleshooting

- **CloudWatch Logs**: Check the logs for each of the three Lambda functions to debug issues.
- **DynamoDB Console**: Inspect the DynamoDB tables to track session status and user data.
- **S3 Browser**: Verify that files are being stored correctly in the `hyperplexity-storage` bucket. 