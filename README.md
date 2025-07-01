# Perplexity Validator

A serverless system that validates Excel data using the Perplexity.AI API, with synchronous and asynchronous processing options.

## Features

- **Multi-mode Processing**: Synchronous preview, asynchronous preview, and full validation modes
- **Excel Processing**: Handles large Excel files with batch processing
- **Intelligent Caching**: S3-based caching to reduce API calls and costs
- **Comprehensive Tracking**: DynamoDB tracking of all validation sessions
- **Email Delivery**: Automatic email delivery of validation results
- **History Tracking**: Maintains validation history for trend analysis
- **API Gateway Interface**: REST API for easy integration

## Architecture

```
API Gateway → Interface Lambda → Validator Lambda
                    ↓
                  SQS (for async)
                    ↓
             Background Processing
```

## Quick Start

See [QUICK_START.md](QUICK_START.md) for detailed setup and usage instructions.

### Test Script

```bash
# Run all tests
python test_validation.py

# Test specific mode
python test_validation.py --mode async_preview --name "my_test"

# Use custom files
python test_validation.py --excel "data.xlsx" --config "config.json"
```

## API Endpoints

- **POST** `/validate` - Main validation endpoint
- **GET** `/status/{sessionId}` - Check validation status
- **POST** `/validate-config` - Validate configuration file

## Configuration

Create a JSON configuration file specifying validation targets:

```json
{
  "validation_targets": [
    {
      "column": "Product Name",
      "description": "Official product name",
      "importance": "CRITICAL",
      "format": "String"
    }
  ]
}
```

## Output

The system produces:

1. **Enhanced Excel File**: Original data with color-coded validation results
2. **Validation Details**: Comprehensive validation results with sources
3. **DynamoDB Records**: Session tracking and metrics
4. **Email Report**: Summary sent to specified email

## Deployment

For administrators deploying the system:

```bash
cd deployment

# Deploy core validator
python create_package.py --deploy --force-rebuild

# Deploy interface with API Gateway
python create_interface_package.py --deploy --force-rebuild
```

## Project Structure

```
perplexityValidator/
├── src/                      # Source code
│   ├── interface_lambda_function.py
│   ├── lambda_function.py
│   ├── validator.py
│   └── ...
├── deployment/               # Deployment scripts
│   ├── create_package.py
│   └── create_interface_package.py
├── test_validation.py        # Main test script
├── tables/                   # Example data
└── test_results/            # Test outputs
```

## Requirements

- Python 3.8+
- AWS Account with appropriate permissions
- Perplexity API key (stored in AWS Parameter Store)

## Cost Optimization

- Intelligent caching reduces API calls by ~80%
- Batch processing for efficiency
- Configurable row limits
- Preview mode for testing

## Monitoring

- CloudWatch Logs for Lambda execution
- DynamoDB for session tracking
- S3 for result storage
- Email notifications for completion

## License

MIT License 