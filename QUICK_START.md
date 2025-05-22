# Quick Start Guide

## Create and Deploy Lambda Function

From the `deployment` directory, run:

```bash
python create_package.py --force-rebuild --deploy --run-test --test-event ratio_competitive_intelligence_test.json
```

This will:
- Force rebuild the Lambda package
- Deploy to AWS Lambda
- Run a test with the specified test event file
- Use API Gateway format for request/response

## Run Excel File Validation

From the `src` directory, run:

```bash
python batch_validate.py ../tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence.xlsx ../tables/RatioCompetitiveIntelligence/column_config.json --max-rows 5 --batch-size 5
```

This will:
- Process the specified Excel file
- Use the specified column configuration file
- Limit processing to 5 rows maximum
- Process rows in batches of 5 