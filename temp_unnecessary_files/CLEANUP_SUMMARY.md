# Cleanup Summary

## Files to KEEP

### Core Files (Used by both Local and Lambda)
- `src/schema_validator.py` - Core schema validation
- `src/schema_validator_simplified.py` - Simplified schema validation
- `src/perplexity_schema.py` - Schema definitions
- `src/prompt_loader.py` - Prompt loading utilities
- `src/row_key_utils.py` - Row key generation
- `src/url_extractor.py` - URL extraction utilities
- `src/prompts.yml` - Prompt templates
- `src/sample_config.yml` - Sample configuration

### Local Execution Files
- `src/batch_validate.py` - Entry point for local batch processing
- `src/excel_batch_processor.py` - Excel batch processing
- `src/excel_processor.py` - Core Excel processing
- `src/excel_history_manager.py` - Validation history management
- `src/excel_validator_cli.py` - CLI interface
- `src/validator.py` - Core validation logic

### Lambda-Specific Files
- `src/lambda_function.py` - Core Lambda handler
- `src/interface_lambda_function.py` - Interface Lambda handler
- `src/lambda_test_json_clean.py` - Lambda test utilities
- `src/email_sender.py` - Email functionality

### Deployment Files
- `deployment/create_package.py` - Core Lambda deployment
- `deployment/create_interface_package.py` - Interface Lambda deployment
- `deployment/*.json` - Test configurations

### Project Files
- `requirements.txt` - Python dependencies
- `requirements-lambda.txt` - Lambda-specific dependencies
- `README.md` - Project documentation
- `.gitignore` - Git ignore rules

## Files to MOVE to temp_unnecessary_files/

### Test/Debug Scripts
- All `test_*.py` files
- All `debug_*.py` files
- All `check_*.py` files
- All `show_*.py` files

### Old Documentation
- `CLEAN_ROW_KEY_HISTORY_SOLUTION.md`
- `ROW_KEY_AND_VALIDATION_HISTORY_REFERENCE.md`
- `interface-requirements.md`
- `QUICK_START.md`
- `temp_validation_fixes_tracker.md`

### Example/Demo Files
- `examples/` directory
- `tables/` directory
- `test_cases/` directory
- `prompts/` directory (old version)

### Redundant Files
- `src/excel_history_processor.py` (replaced by excel_history_manager.py)
- `src/schema_validator_enhanced.py` (using simplified version)
- `src/multiplex_parser.py` (not currently used)
- `src/column_config_template.json` (example file)
- `src/README_EXCEL_VALIDATOR.md` (old documentation)

## Files to DELETE (Build Artifacts)
- `deployment/package/` directory
- `deployment/interface_package/` directory
- `deployment/*.zip` files
- All `__pycache__/` directories
- All `.pyc` files 