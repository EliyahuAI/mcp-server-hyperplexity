# AWS Perplexity Validator

A serverless AWS Lambda function that validates data using the Perplexity.AI API with caching support.

## Features

- Parallel validation of multiple data points
- S3-based caching to reduce API calls
- Configurable validation rules and targets
- Automatic next check date calculation
- Comprehensive error handling
- Local testing support

## Prerequisites

- Python 3.8 or higher
- AWS CLI configured with appropriate credentials
- Perplexity.AI API key
- AWS S3 bucket for caching
- AWS Systems Manager Parameter Store for API key storage

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd perplexity-validator
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up AWS resources:
   - Create an S3 bucket for caching
   - Store your Perplexity API key in AWS Systems Manager Parameter Store:
     ```bash
     aws ssm put-parameter \
         --name "/Perplexity_API_Key" \
         --value "your-api-key" \
         --type SecureString
     ```

4. Configure Lambda function:
   - Set environment variables:
     - `PERPLEXITY_API_KEY` (optional, if not using SSM)
   - Configure IAM role with permissions for:
     - S3 access
     - SSM Parameter Store access
     - CloudWatch Logs

## Local Testing

1. Run automated tests:
```bash
pytest
```

2. Run local test script:
```bash
python tests/local_test.py
```

## Deployment

1. Create a deployment package:
```bash
pip install -r requirements.txt -t package/
cp src/*.py package/
cd package
zip -r ../deployment.zip .
```

2. Deploy to AWS Lambda:
```bash
aws lambda create-function \
    --function-name perplexity-validator \
    --runtime python3.9 \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://deployment.zip \
    --role arn:aws:iam::<account-id>:role/<role-name>
```

## Usage

Invoke the Lambda function with the following event structure:

```json
{
    "config": {
        "primary_key": ["id"],
        "cache_ttl_days": 30,
        "validation_targets": [
            {
                "column": "name",
                "validation_type": "string",
                "rules": {
                    "min_length": 2,
                    "max_length": 100
                },
                "description": "Validate name length"
            }
        ]
    },
    "validation_data": {
        "rows": [
            {
                "id": 1,
                "name": "John Doe"
            }
        ]
    },
    "bucket_name": "your-cache-bucket"
}
```

### Response Format

```json
{
    "statusCode": 200,
    "body": {
        "results": {
            "name": ["John Doe", 0.95, "Name is valid"],
            "1_next_check": ["2024-03-20T00:00:00Z", 1.0, ["All validations passed"]]
        }
    }
}
```

## Error Handling

The function handles various error scenarios:
- Invalid API responses
- Cache access failures
- Configuration errors
- Validation failures

Errors are logged to CloudWatch Logs and returned in the response with appropriate status codes.

## Monitoring

Monitor the function using:
- CloudWatch Logs
- CloudWatch Metrics
- X-Ray traces (if enabled)

## Cost Optimization

- Caching reduces API calls
- Configurable cache TTL
- Parallel processing for efficient execution
- Automatic retry logic for transient failures

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License 