# Perplexity Validator Interface - Refactored Architecture

This document outlines the new, modular architecture of the Perplexity Validator Interface Lambda. The original monolithic `interface_lambda_function.py` has been refactored into a structured package to improve maintainability, testability, and performance.

## 1. High-Level Overview

The interface lambda is the primary entry point for all validation requests. Its main responsibilities are:
-   **Request Routing**: Handling requests from different AWS services (API Gateway, SQS).
-   **Orchestration**: Managing the validation workflow, which includes uploading files to S3, invoking a separate processing lambda, and generating reports.
-   **User Interaction**: Handling API actions for status checks, email validation, and diagnostics.

The core design principle of this refactoring is the **Single Responsibility Principle**. Each module and function now has a single, well-defined purpose.

## 2. Code Structure

All the refactored code resides within the `src/interface_lambda/` directory, which is structured as a Python package.

```
src/
├── interface_lambda/
│   ├── __init__.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── http_handler.py      # Handles API Gateway events
│   │   ├── sqs_handler.py       # Handles SQS queue messages
│   │   └── background_handler.py  # Handles the core processing logic
│   ├── actions/
│   │   ├── __init__.py
│   │   ├── process_excel.py     # Orchestrates the main validation workflow
│   │   ├── email_validation.py  # Handles all email verification steps
│   │   ├── status_check.py      # Provides job status to clients
│   │   ├── user_stats.py        # Retrieves user statistics
│   │   ├── config_validation.py # Validates configuration files
│   │   └── diagnostics.py       # Provides system health info
│   ├── core/
│   │   ├── __init__.py
│   │   ├── s3_manager.py        # Manages all interactions with S3
│   │   ├── validator_invoker.py # Handles invoking the separate validator lambda
│   │   └── sqs_service.py       # Manages sending messages to SQS queues
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── excel_report.py      # Creates enhanced .xlsx reports
│   │   ├── zip_report.py        # Creates .zip archives
│   │   └── markdown_report.py   # Creates Markdown summary tables
│   └── utils/
│       ├── __init__.py
│       ├── helpers.py           # General-purpose helper functions
│       ├── parsing.py           # Multipart form data parsing
│       └── history_loader.py    # Loads validation history from Excel files
└── interface_lambda_function.py # The main Lambda entry point (now a simple router)
```

### 2.1. Main Services (Top-Level)

These services are shared across the application and remain at the top level of the `src/` directory.

-   `email_sender.py`: A shared service for sending emails. It's used by both the interface lambda and `dynamodb_schemas`.
-   `dynamodb_schemas.py`: Manages all interactions with DynamoDB, including tracking validation jobs, user stats, and email validation codes. It's a core data service for the entire application.

### 2.2. The New `interface_lambda` Package

-   **`handlers/`**: These are the entry points for different event sources.
    -   `http_handler.py`: The router for all API Gateway requests. It inspects the request and delegates to the appropriate module in the `actions/` directory.
    -   `sqs_handler.py`: Processes messages from SQS, transforms them, and passes them to the `background_handler.py`.
    -   `background_handler.py`: Contains the main orchestration logic for a validation run. It calls the validator, generates reports, and sends notifications.

-   **`actions/`**: Each module in this directory corresponds to a specific user-facing action.
    -   `process_excel.py`: Handles the core file submission workflow, whether from a multipart form or a JSON request. It uploads files and triggers the background handler.
    -   `status_check.py`: Provides the status of a running validation job.
    -   `email_validation.py`, `user_stats.py`, `config_validation.py`, `diagnostics.py`: Handle their respective API actions.

-   **`core/`**: Contains the central, business-agnostic logic.
    -   `s3_manager.py`: A client for all S3 operations (uploads, presigned URLs).
    -   `validator_invoker.py`: A dedicated module to handle the complex logic of preparing and invoking the separate `perplexity-validator` lambda.
    -   `sqs_service.py`: A client for sending messages to the SQS standard and preview queues.

-   **`reporting/`**: This package isolates all report-generation logic. This is crucial for performance, as it allows heavy libraries like `xlsxwriter` and `openpyxl` to be imported only when needed.

-   **`utils/`**: Contains small, reusable helper functions that don't fit elsewhere.

## 3. Request Flow Example: Multipart File Upload

To illustrate how the new components work together, here is the flow for a typical file upload request:

1.  **Entry Point**: A `POST` request with a `multipart/form-data` body hits API Gateway. The event is received by the main `lambda_handler` in `src/interface_lambda_function.py`.

2.  **Routing**: The `lambda_handler` sees it's an HTTP event and passes it to `src/interface_lambda/handlers/http_handler.py`.

3.  **Action Handling**: `http_handler.py` detects the `multipart/form-data` content type and calls the `handle_multipart_form` function in `src/interface_lambda/actions/process_excel.py`.

4.  **Processing**: `process_excel.py` performs the following steps:
    a.  It uses `utils/parsing.py` to parse the files and form data from the request body.
    b.  It validates the user's email using `dynamodb_schemas`.
    c.  It uses `utils/helpers.py` to generate a unique session ID.
    d.  It uses `core/s3_manager.py` to upload the Excel and config files to an S3 bucket.
    e.  It determines if this is a preview or full run and if it should be asynchronous.
    f.  It uses `core/sqs_service.py` to send a message to the appropriate SQS queue, triggering the background process.
    g.  It returns an immediate `200 OK` response to the user with the session ID.

5.  **Background Processing**:
    a.  SQS triggers the Lambda again. The main `lambda_handler` routes the event to `handlers/sqs_handler.py`.
    b.  `sqs_handler.py` parses the message and calls `handlers/background_handler.py`.
    c.  `background_handler.py` orchestrates the rest of the workflow:
        i.  It calls `core/validator_invoker.py` to invoke the separate validator lambda and get the results.
        ii. It uses `reporting/zip_report.py`, `reporting/excel_report.py`, and `reporting/markdown_report.py` to generate the final reports.
        iii. It uses `core/s3_manager.py` to upload the final report archive.
        iv. It uses `email_sender.py` to notify the user.
        v.  It uses `dynamodb_schemas.py` to update the job status and metrics.

This modular design ensures a clean separation of concerns, making the system more robust, scalable, and easier to understand. 

## 3. API Endpoints and Lazy Loading

A key design goal of this refactoring is to improve performance by only loading the code necessary for a specific request. This is especially important for AWS Lambda to minimize cold-start times. The application uses a "just-in-time" import strategy.

The API is now simplified to two main resource paths, which are handled by a single Lambda function using proxy integration.

### 3.1. `POST /validate`

This single, versatile endpoint handles all primary actions, which are specified in the JSON request body.

-   **Description**: This is the main workhorse endpoint. It handles file processing, email validation, user stats, and more based on the `action` field in the request.
-   **Execution Path**:
    1.  The `POST` request hits the `/validate` endpoint.
    2.  API Gateway, via **Lambda Proxy Integration**, passes the entire request to `interface_lambda_function.lambda_handler`.
    3.  The router passes the event to `handlers.http_handler`.
    4.  `http_handler` inspects the `Content-Type` and JSON `action` field, **loading only the required action module**.
        -   **`action: "processExcel"`**: Loads `actions.process_excel` for file submissions. This is the most heavyweight action.
        -   **`action: "requestEmailValidation"`**: Loads `actions.email_validation`. This is a lightweight action.
        -   **`action: "getUserStats"`**: Loads `actions.user_stats`. This is a lightweight action.
        -   ...and so on for all other actions.
-   **Result**: The backend logic is perfectly aligned with the API structure. A single, clean endpoint provides access to all features, while the lazy-loading mechanism ensures that simple requests (like email validation) are not slowed down by the code required for complex actions (like file processing).

### 3.2. `GET /status/{sessionId}`

This remains a lightweight, dedicated endpoint for polling.

-   **Description**: Allows the frontend to poll for the status of a validation job.
-   **Execution Path**:
    1.  A `GET` request to `/status/...` is passed via proxy integration to the `http_handler`.
    2.  The handler sees the path and imports only **`actions.status_check`**.
-   **Result**: This path remains highly optimized for fast, frequent polling.

### 3.3. SQS Message (Background Processing)

The background processing flow remains unchanged, providing a robust, isolated environment for the most intensive tasks.

This simplified API structure, combined with the lazy-loading backend, provides a clean, maintainable, and highly performant architecture. 