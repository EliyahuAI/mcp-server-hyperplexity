# Quick Start Guide - Perplexity Validator

## Overview

The Perplexity Validator is a system that validates data in Excel tables using the Perplexity AI API. It supports both local execution and cloud-based Lambda processing.

## Two Ways to Use

### 1. Cloud API (Recommended for most users)

Use the deployed API Gateway interface for easy validation without local setup:

```bash
# Test with default files (preview mode)
python test_full_validation.py --preview

# Full validation with email delivery
python test_full_validation.py --email your-email@example.com

# Validate specific files
python test_full_validation.py -e your_data.xlsx -c your_config.json

# Limit rows and custom batch size
python test_full_validation.py --max-rows 50 --batch-size 20
```

**API Endpoint**: `https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate`

### 2. Local Execution

For processing files locally without using the cloud:

```bash
# Basic usage
python src/batch_validate.py your_data.xlsx your_config.json

# With options
python src/batch_validate.py your_data.xlsx your_config.json --batch-size 20 --max-rows 100
```

## Configuration File Format

Create a JSON configuration file that specifies which columns to validate:

```json
{
  "validation_targets": [
    {
      "column": "Product Name",
      "description": "Official name of the product",
      "importance": "ID",
      "format": "String",
      "notes": "Use official nomenclature"
    },
    {
      "column": "Development Stage",
      "description": "Current stage of development",
      "importance": "CRITICAL",
      "format": "String",
      "examples": ["Phase 1", "Phase 2", "Phase 3", "Approved"]
    }
  ]
}
```

**Importance Levels**:
- `ID`: Primary key fields (used to uniquely identify rows)
- `CRITICAL`: Must be validated
- `HIGH`: Important but not critical
- `MEDIUM`/`LOW`: Lower priority fields

## Output

The validator produces an enhanced Excel file with:

- **Results Sheet**: Original data with color-coded validation results
  - Green (HIGH confidence)
  - Yellow (MEDIUM confidence)
  - Red (LOW confidence)
- **Details Sheet**: Detailed validation results with quotes and sources
- **Reasons Sheet**: Explanations for each validation

## Validation History

The system automatically tracks validation history:
- Previous validations are stored in the Details sheet
- When re-validating, historical values are included in prompts
- New results are marked as "New", previous ones as "Historical"

## Requirements

- Python 3.8+
- For cloud API: `requests` library
- For local execution: See `deployment/requirements-dev.txt`

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd perplexityValidator

# Install dependencies for local execution
pip install -r deployment/requirements-dev.txt

# Or just install requests for API usage
pip install requests
```

## Examples

### Example 1: Validate Competitive Intelligence Data

```bash
# Using API
python test_full_validation.py \
  -e tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence.xlsx \
  -c tables/RatioCompetitiveIntelligence/column_config.json \
  --max-rows 10
```

### Example 2: Preview Mode (Test First Row)

```bash
# Quick test to see how validation works
python test_full_validation.py --preview
```

### Example 3: Local Batch Processing

```bash
# Process entire file locally
python src/batch_validate.py data.xlsx config.json --batch-size 5
```

## Troubleshooting

1. **"Excel file not found"**: Ensure the file path is correct
2. **"Config file not found"**: Check the configuration file path
3. **API timeout**: Large files may take time; email delivery ensures you get results
4. **No validation history**: Ensure the Excel file has a Details sheet from previous runs

## Support

For issues or questions:
- Check CloudWatch logs for Lambda execution details
- Review the configuration file format
- Ensure columns in Excel match those in the config file

## Setting Up Lambda Functions (First Time Setup)

If you need to deploy the Lambda functions yourself:

### Prerequisites
- AWS CLI configured with appropriate credentials
- Python 3.8 or higher
- pip package manager

### Step 1: Deploy Core Validator Lambda

```bash
cd deployment
python create_package.py --deploy --force-rebuild
```

This creates and deploys the core validation Lambda function that processes validation requests.

### Step 2: Deploy Interface Lambda with API Gateway

```bash
python create_interface_package.py --deploy --force-rebuild
```

This creates:
- The interface Lambda function for handling file uploads
- API Gateway endpoint for web access
- Note the API URL that's displayed after deployment

### Step 3: Test the Deployment

```bash
# Test with the included test event
python create_package.py --test-only --test-event ratio_competitive_intelligence_test.json

# Or test the API endpoint
cd ..
python test_full_validation.py --preview
```

### Quick Validation Example

Once deployed, validate an Excel file:

```bash
# From the project root
python test_full_validation.py \
  -e tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence.xlsx \
  -c tables/RatioCompetitiveIntelligence/column_config_simplified.json \
  --email your-email@example.com \
  --max-rows 10
```

This will:
1. Upload your Excel file and config to the Lambda
2. Process 10 rows using Perplexity AI
3. Email you the results when complete

### Deployment Options

```bash
# Force rebuild packages (if dependencies changed)
python create_package.py --deploy --force-rebuild
python create_interface_package.py --deploy --force-rebuild

# Deploy without rebuilding (faster)
python create_package.py --deploy --no-rebuild
python create_interface_package.py --deploy --no-rebuild

# Just build packages without deploying
python create_package.py
python create_interface_package.py
```