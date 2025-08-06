# Detailed Codebase Cleanup and Refactoring Plan

This document provides a phased approach to refactoring the Hyperplexity Table Validator codebase. The goal is to improve maintainability, reduce complexity, and establish a clear project structure without breaking functionality.

## Potential Breaking Changes & Mitigations

A deep dive into the proposed refactoring reveals the following potential issues:

1.  **Broken Python Imports**: Moving modules will break `import` statements.
    *   **Problem**: Python scripts use relative imports (e.g., `from actions import ...`) or expect a specific directory structure. When we move files, these imports will fail.
    *   **Mitigation**: We will need to adjust Python's import path. In each Lambda's entry point, we will add logic to include the `src` directory in the path. This allows for consistent absolute imports from the project root (e.g., `from shared.ai_api_client import ...`). All existing import statements within the application code will be updated to use this new absolute path convention.

2.  **Hardcoded File Paths**: Scripts might contain hardcoded relative paths to assets like prompts or schemas.
    *   **Problem**: A script in `src/interface_lambda/actions/` might try to open `../prompts/some_prompt.md`. After moving, this path will be incorrect.
    *   **Mitigation**: All file access will be standardized to use paths relative to the script's location or an absolute path derived from a known root directory. This will be a major part of the code update process.

3.  **Deployment Script Logic**: The deployment scripts (`create_package.py`, `create_interface_package.py`, etc.) are written for the old directory structure.
    *   **Problem**: The scripts expect to find source files and dependencies in specific locations. They will fail when trying to package the new, restructured lambdas.
    *   **Mitigation**: These scripts will be rewritten in Phase 3 to correctly locate the lambda source code in `src/lambdas/<lambda_name>/` and bundle the `src/shared/` directory into each deployment package.

## Phased Refactoring Plan

### Phase 1: Project Scaffolding & Initial File Migration

This phase sets up the new structure without modifying application logic. It is easily reversible.

1.  **Create New Directories**:
    ```bash
    mkdir -p docs frontend src/lambdas/interface src/lambdas/config src/lambdas/validation src/shared tests
    ```

2.  **Move Documentation**: All `.md` files will be moved from the root into the `docs/` directory.
    ```bash
    mv *.md docs/
    # Move the newly created planning files as well
    mv backend_architecture.md detailed_cleanup_plan.md cleanup_proposal.md README.md docs/
    # Create a new top-level README
    touch README.md
    ```
    *(I will update the root `README.md` later to be a proper entry point).*

3.  **Move Frontend**: The main HTML interface will be moved.
    ```bash
    mv perplexity_validator_interface2.html frontend/
    ```

4.  **Create Deployment Script**: A new `deploy_all.sh` script will be created in the root directory. This script will not be executed until Phase 4.

    ```bash
    #!/bin/bash
    # This script deploys all lambda functions sequentially.
    
    set -e # Exit immediately if a command exits with a non-zero status.
    
    echo "--- Deploying Interface Lambda ---"
    python deployment/create_interface_package.py --deploy --force-rebuild
    
    echo "--- Deploying Validation Lambda ---"
    python deployment/create_package.py --deploy --force-rebuild
    
    echo "--- Deploying Config Lambda ---"
    python deployment/deploy_config_lambda.py --deploy --force-rebuild
    
    echo "--- All lambdas deployed successfully! ---"
    ```
    I will also create a `deploy_all.bat` for Windows compatibility.

### Phase 2: Core Code Migration and Refactoring

This is the most intensive phase where we will move and refactor the core application code.

1.  **Move Lambda-Specific Code**:
    *   The contents of `src/interface_lambda/` will be moved to `src/lambdas/interface/`.
    *   The contents of `config_lambda/` will be moved to `src/lambdas/config/`.
    *   `src/lambda_function.py`, `src/websocket_handler.py`, and other related validation logic will be moved to `src/lambdas/validation/`.

2.  **Consolidate Shared Code**:
    *   Identify common files like `ai_api_client.py`, `dynamodb_schemas.py`, etc., from the various lambda packages.
    *   Move a single copy of each of these files into `src/shared/`.
    *   Delete the duplicate copies from their old locations.

3.  **Update All Python Imports**:
    *   Systematically go through every Python file in `src/lambdas/` and `src/shared/`.
    *   Update all import statements to be absolute from the `src` root (e.g., `from shared.dynamodb_schemas import ...`, `from lambdas.interface.utils import ...`).

### Phase 3: Update Build and Deployment Scripts

With the code restructured, we now update the automation that packages it.

1.  **Modify `deployment/create_interface_package.py`**:
    *   Change the source code path from `src/interface_lambda/` to `src/lambdas/interface/`.
    *   Add logic to include the `src/shared/` directory in the deployment zip file.

2.  **Modify `deployment/create_package.py`** (for Validation Lambda):
    *   Change the source code path to `src/lambdas/validation/`.
    *   Add logic to include the `src/shared/` directory in the deployment zip file.

3.  **Modify `deployment/deploy_config_lambda.py`**:
    *   Change the source code path from `config_lambda/` to `src/lambdas/config/`.
    *   Add logic to include the `src/shared/` directory in the deployment zip file.

### Phase 4: Testing, Deployment, and Finalization

This final phase ensures the refactored code works correctly.

1.  **Move and Refactor Tests**:
    *   Move all test-related files and directories (e.g., `test_cases/`, `test_validation.py`) into the `tests/` directory.
    *   Update all imports within the test files to match the new `src` structure.

2.  **Execute Tests**:
    *   Run the entire test suite from the `tests/` directory to confirm that all refactored code passes its original tests.

3.  **Execute Deployment Script**:
    *   Run the new `deploy_all.sh` or `deploy_all.bat` script to deploy the refactored lambdas to AWS.

4.  **Perform End-to-End (E2E) Testing**:
    *   Manually test the deployed application by using the web interface to perform a full validation workflow. This will catch any integration issues missed by the automated tests.

5.  **Cleanup**:
    *   Remove all the old, now-empty directories (`config_lambda/`, `src/interface_lambda/`, etc.).
    *   Update the `.gitignore` file to reflect the new directory structure if needed.

This phased plan will allow us to methodically and safely refactor the codebase, with clear steps and mitigation strategies for potential issues.

I am ready to proceed with Phase 1. Please confirm if you would like me to start. 