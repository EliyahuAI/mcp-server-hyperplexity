# Excel Validator

A tool for processing Excel/CSV data and updating it with validation results from Perplexity API.

## Features

- Convert Excel/CSV files to JSON
- Process validation results from Perplexity API
- Update Excel files with validation results, color-coded by confidence level
- Add validation quotes and sources as cell comments
- Create a detailed view sheet with all validation information
- Compatible with existing lambda function's column_config.yml format

## Installation

Make sure you have the required packages installed:

```bash
pip install pandas openpyxl pyyaml
```

For using the AWS Lambda function by ARN, you'll also need:

```bash
pip install boto3
```

## Environment Setup

For Lambda function integration, set ONE of the following environment variables:

### Option 1: Using Lambda Function ARN (Recommended)

```bash
# Windows
set LAMBDA_FUNCTION_ARN=arn:aws:lambda:us-east-1:400232868802:function:perplexity-validator

# Linux/Mac
export LAMBDA_FUNCTION_ARN=arn:aws:lambda:us-east-1:400232868802:function:perplexity-validator
```

When using the Lambda ARN, you must also have AWS credentials configured:
- AWS credentials in `~/.aws/credentials`
- Or environment variables `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- Or use an AWS EC2 instance with an IAM role that has permissions to invoke the Lambda

### Option 2: Using Lambda Function URL

```bash
# Windows
set LAMBDA_FUNCTION_URL=https://your-lambda-function-url.lambda-url.us-east-1.on.aws/
set PERPLEXITY_API_KEY=your-api-key

# Linux/Mac
export LAMBDA_FUNCTION_URL=https://your-lambda-function-url.lambda-url.us-east-1.on.aws/
export PERPLEXITY_API_KEY=your-api-key
```

For testing without Lambda integration, use the `--local` flag which will use the mock validator included in the project.

## Usage

The Excel Validator provides both a Python API and a command-line interface.

### Command Line Interface

#### Convert Excel/CSV to JSON

```bash
python excel_validator_cli.py to-json input_file.xlsx --output data.json --config config.yml
```

#### Process Validation Results

```bash
python excel_validator_cli.py process input_file.xlsx --validation validation_results.json --output validated_data.xlsx
```

#### End-to-End Processing

```bash
python excel_validator_cli.py end-to-end input_file.xlsx --output validated_data.xlsx --api-key your_api_key
```

#### Process Only Selected Rows

You can process only specific rows by adding the `--rows` argument:

```bash
python excel_validator_cli.py end-to-end input_file.xlsx --rows 0,1,2  # Process rows 0, 1, and 2
python excel_validator_cli.py end-to-end input_file.xlsx --rows 0-5    # Process rows 0 through 5
```

#### Quick Test with RatioCompetitiveIntelligence Data

To quickly test with the RatioCompetitiveIntelligence dataset:

```bash
python excel_validator_cli.py test --rows 0-2 --api-key your_api_key
```

This will process the first 3 rows of the RatioCompetitiveIntelligence.xlsx file and generate an output file in the same directory.

For testing without using the lambda function (using local mock validation):

```bash
python excel_validator_cli.py test --rows 0-2 --api-key your_api_key --local
```

### Python API

You can also use the Excel Validator directly in your Python code:

```python
from excel_processor import ExcelProcessor, process_file, end_to_end_process

# Convert Excel to JSON
processor = ExcelProcessor("input_file.xlsx", "config.yml")
json_data = processor.to_json("output.json")

# Process validation results
process_file(
    input_file="input_file.xlsx",
    config_file="config.yml",
    validation_json="validation_results.json",
    output_file="validated_data.xlsx"
)

# End-to-end processing
end_to_end_process(
    input_file="input_file.xlsx",
    config_file="config.yml",
    output_file="validated_data.xlsx",
    api_key="your_api_key"
)
```

## Working with RatioCompetitiveIntelligence Files

The validator is specially configured to work with the RatioCompetitiveIntelligence dataset:

1. It automatically detects and uses the `column_config.yml` file in the same directory as the input file
2. It properly handles the specific column configuration format used by the existing lambda function
3. It maps importance levels from the config (critical, interesting, ignored) to confidence colors

### Example End-to-End Test:

This example processes the first 2 rows of the RatioCompetitiveIntelligence.xlsx file:

```bash
cd src
python excel_validator_cli.py test --rows 0-1 --api-key your_api_key
```

### Step-by-Step with RatioCompetitiveIntelligence Files:

1. Convert the Excel file to JSON:
   ```bash
   python excel_validator_cli.py to-json "../tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence.xlsx" --rows 0-2 --output "../tables/RatioCompetitiveIntelligence/data.json"
   ```

2. Process the validation results (if you already have them):
   ```bash
   python excel_validator_cli.py process "../tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence.xlsx" --validation "../tables/RatioCompetitiveIntelligence/validation_results.json" --output "../tables/RatioCompetitiveIntelligence/validated.xlsx"
   ```

3. Or run the complete end-to-end process:
   ```bash
   python excel_validator_cli.py end-to-end "../tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence.xlsx" --rows 0-2 --output "../tables/RatioCompetitiveIntelligence/validated.xlsx" --api-key your_api_key
   ```

4. Open the generated `validated.xlsx` file to view the results 

## Output Format

The output Excel file will contain:

1. **Validated Data Sheet**: The original data with color-coding based on confidence levels:
   - Green: High confidence
   - Yellow: Medium confidence
   - Red: Low confidence
   - White: Not validated

2. **Detailed View Sheet**: A table with all validation details, including:
   - Original and validated values
   - Confidence scores
   - Quotes from sources
   - Source links
   - Update requirements

## Configuration

The validator works with two types of configuration files:

1. **column_config.yml** (used by the lambda function):
   ```yaml
   primary_key: ["Product Name", "Developer", "Target"]
   
   model_name: sonar-pro
   
   columns:
     Product Name:
       description: Official code or INN of the radiopharmaceutical
       examples: ["FAP-2286", "225Ac-PSMA-617", "TLX250-CDx"]
       format: String
       importance: ignored
   ```

2. **config.yml** (standard format):
   ```yaml
   primary_key:
     - id
     
   columns_to_validate:
     - name
     - email
     - status
     
   column_importance:
     id: HIGH
     name: MEDIUM
     email: HIGH
     
   detailed_view: true
   ```

## Notes

- If no configuration file is specified, the tool will look for `column_config.yml` or `config.yml` in the same directory as the input file
- The validator prioritizes finding `column_config.yml` (the lambda format) before looking for `config.yml`
- The validator automatically maps importance levels from the lambda format to our standard confidence levels
- For Lambda integration, set either `LAMBDA_FUNCTION_ARN` (recommended) or `LAMBDA_FUNCTION_URL`
- When using the ARN option, ensure AWS credentials are properly configured
- The `--local` flag uses a built-in mock validator for testing without Lambda access 