
# Backend Architecture

This document outlines the backend architecture of the Hyperplexity Table Validator application. The backend is built on a serverless architecture using AWS Lambda, API Gateway, and S3. It consists of three main Lambda functions:

1.  **Interface Lambda**: Handles user-facing interactions, including email validation, file uploads, and initiating validation processes.
2.  **Config Lambda**: Manages the creation, modification, and validation of configuration files.
3.  **Validation Lambda**: Performs the core data validation and enrichment tasks.

## 1. Interface Lambda (`src/interface_lambda`)

The Interface Lambda serves as the primary entry point for the frontend. It is responsible for handling user authentication, file uploads, and orchestrating the validation workflow.

### Key Components:

*   **`actions/`**: Contains the business logic for various user actions, such as creating a new session, uploading a file, and initiating a validation process.
*   **`core/`**: Holds the core components of the lambda, such as the main handler and utility functions.
*   **`handlers/`**: Manages the different types of requests that the lambda can receive, such as HTTP requests from API Gateway.
*   **`reporting/`**: Handles the generation of reports and sending them to the user.
*   **`utils/`**: Contains utility functions that are used across the lambda.

## 2. Config Lambda (`config_lambda/`)

The Config Lambda is responsible for managing the configuration files that define the validation rules for each table. It can generate a new configuration file based on the table structure, modify an existing one, or validate a configuration file against the table.

### Key Components:

*   **`config_lambda_function.py`**: The main entry point for the lambda. It contains the logic for handling the different types of requests that the lambda can receive.
*   **`prompts/`**: Contains the prompts that are used to generate the configuration files.
*   **`ai_generation_schema.json`**: Defines the schema for the AI-generated configuration files.

## 3. Validation Lambda (`src/lambda_function.py`)

The Validation Lambda is the workhorse of the application. It takes a table and a configuration file as input and performs the validation and enrichment tasks. It can be run in either synchronous or asynchronous mode. In asynchronous mode, it uses a WebSocket connection to send progress updates to the frontend.

### Key Components:

*   **`lambda_function.py`**: The main entry point for the lambda. It contains the logic for handling the validation requests.
*   **`websocket_handler.py`**: Manages the WebSocket connection and sends progress updates to the frontend.

## Data Flow

1.  The user uploads an Excel file through the frontend.
2.  The frontend sends a request to the Interface Lambda to create a new session and upload the file to S3.
3.  The Interface Lambda returns a session ID to the frontend.
4.  The user can then choose to either generate a new configuration file or use an existing one.
5.  If the user chooses to generate a new configuration file, the frontend sends a request to the Config Lambda.
6.  The Config Lambda generates a new configuration file and saves it to S3.
7.  The user can then modify the configuration file and save the changes.
8.  Once the user is satisfied with the configuration file, they can start the validation process.
9.  The frontend sends a request to the Validation Lambda with the session ID and the configuration file.
10. The Validation Lambda reads the Excel file and the configuration file from S3 and starts the validation process.
11. The Validation Lambda sends progress updates to the frontend through a WebSocket connection.
12. Once the validation is complete, the Validation Lambda saves the results to S3 and sends a notification to the user.

This is a high-level overview of the backend architecture. For more detailed information, please refer to the source code and the documentation in the respective directories. 