# Quick Start Guide

## Create and Deploy Lambda Function

From the `deployment` directory, run:

```bash
python create_package.py --force-rebuild --deploy --run-test --test-event ratio_competitive_intelligence_history_test.json
```

This will:
- Force rebuild the Lambda package
- Deploy to AWS Lambda
- Run a test with the updated simplified format test event file
- Use API Gateway format for request/response

## Alternative Test Events

For basic testing without history:
```bash
python create_package.py --force-rebuild --deploy --run-test --test-event ratio_competitive_intelligence_test.json
```

## Run Excel File Validation with Simplified Config

From the `src` directory, run:

```bash
python batch_validate.py ../tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence.xlsx ../tables/RatioCompetitiveIntelligence/column_config_simplified.json --max-rows 5 --batch-size 5
```

This will:
- Process the specified Excel file
- Use the simplified column configuration file
- Limit processing to 5 rows maximum
- Process rows in batches of 5

## Alternative with Original Config Format

If you need to use the original format:
```bash
python batch_validate.py ../tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence.xlsx ../tables/RatioCompetitiveIntelligence/column_config.json --max-rows 5 --batch-size 5
```

## Configuration Formats

### Simplified Format (Recommended)
- **File**: `column_config_simplified.json`
- **Features**: Auto-generated primary keys, streamlined structure, default model
- **Benefits**: Cleaner, less redundant, easier to maintain

### Original Format (Legacy)
- **File**: `column_config.json`
- **Features**: Explicit primary keys, validation_type, rules, field_relationships
- **Use**: For backward compatibility

## Test Event Files

- **`ratio_competitive_intelligence_history_test.json`**: Simplified format with validation history
- **`ratio_competitive_intelligence_test.json`**: Original format for compatibility testing 