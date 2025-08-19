
# Codebase Cleanup Proposal

This document outlines a proposal for cleaning up and restructuring the codebase of the Hyperplexity Table Validator application. The goal is to improve the organization, reduce redundancy, and make the project easier to maintain and scale.

## 1. Directory Structure

The current directory structure is a bit cluttered and could be improved by consolidating related files and directories. Here is a proposed new directory structure:

```
perplexityValidator/
├── .gitignore
├── agent_logs.md
├── backend_architecture.md
├── cleanup_proposal.md
├── docs/
│   ├── AI_CONFIG_GENERATOR_LAMBDA_INTEGRATION_PROMPT.md
│   ├── API_EXAMPLES.md
│   ├── CONFIG_INTERFACE_SPECIFICATION.md
│   ├── CONFIG_LAMBDA_README.md
│   └── ...
├── frontend/
│   └── perplexity_validator_interface.html
├── src/
│   ├── lambdas/
│   │   ├── interface/
│   │   │   ├── __init__.py
│   │   │   ├── actions/
│   │   │   ├── core/
│   │   │   ├── handlers/
│   │   │   ├── reporting/
│   │   │   └── utils/
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   ├── config_lambda_function.py
│   │   │   ├── prompts/
│   │   │   └── ...
│   │   └── validation/
│   │       ├── __init__.py
│   │       ├── lambda_function.py
│   │       └── websocket_handler.py
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── ai_api_client.py
│   │   ├── dynamodb_schemas.py
│   │   └── ...
│   └── ...
├── tables/
│   └── ...
└── tests/
    ├── __init__.py
    ├── test_cases/
    └── ...
```

### Key Changes:

*   **`docs/`**: A new directory to store all the documentation files, including the `.md` files that are currently in the root directory.
*   **`frontend/`**: A new directory to store the frontend files, including the `perplexity_validator_interface.html` file.
*   **`src/lambdas/`**: A new directory to store the source code for the Lambda functions. Each Lambda function will have its own subdirectory.
*   **`src/shared/`**: A new directory to store the shared code that is used across multiple Lambda functions.
*   **`tests/`**: A new directory to store all the test files.

## 2. Consolidate Common Code

Currently, there is a lot of duplicate code across the different Lambda functions. For example, the `ai_api_client.py` and `dynamodb_schemas.py` files are present in multiple directories. This code should be moved to the `src/shared/` directory and imported by the Lambda functions that need it.

## 3. Update Build and Deployment Process

The build and deployment process should be updated to reflect the new directory structure. The `create_package.py`, `create_interface_package.py`, and `deploy_config_lambda.py` scripts should be updated to package the Lambda functions and their dependencies from the `src/lambdas/` and `src/shared/` directories.

## 4. Update Documentation

All the documentation files should be moved to the `docs/` directory. The `README.md` file in the root directory should be updated to provide a high-level overview of the project and link to the documentation in the `docs/` directory.

By implementing these changes, we can significantly improve the organization and maintainability of the codebase. 