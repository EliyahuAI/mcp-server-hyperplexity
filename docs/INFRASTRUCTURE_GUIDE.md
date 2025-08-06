# Perplexity Validator Infrastructure Guide

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Infrastructure Components](#infrastructure-components)
3. [Setup Guide](#setup-guide)
4. [API Reference](#api-reference)
5. [Testing Guide](#testing-guide)
6. [Troubleshooting](#troubleshooting)

## Architecture Overview

The Perplexity Validator is a serverless application that validates Excel data using either the Perplexity AI API or Anthropic's Claude API. It supports both synchronous and asynchronous processing modes.

### Request Flow

1. **Synchronous Mode**:
   ```
   Client → API Gateway → Interface Lambda → Validator Lambda → Response
   ```

2. **Asynchronous Mode**:
   ```
   Client → API Gateway → Interface Lambda → SQS → Interface Lambda → Validator Lambda → S3/Email
   ```

### Key Design Decisions

- **Dual Lambda Architecture**: Separation of concerns between interface handling and validation logic
- **SQS Integration**: Enables reliable async processing and automatic retries
- **DynamoDB Tracking**: Comprehensive session tracking and metrics
- **S3 Storage**: Persistent storage for results and caching
- **Email Delivery**: Automatic notification when validation completes

## Infrastructure Components

### 1. API Gateway
- **Endpoint**: `https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod`
- **Stage**: `prod`
- **Integration Types**:
  - Lambda proxy integration for `/validate` and `/status/*`
  - Direct Lambda integration for config validation

### 2. Lambda Functions

#### Interface Lambda (`perplexity-validator-interface`)
- **Runtime**: Python 3.9
- **Memory**: 2048 MB
- **Timeout**: 900 seconds (15 minutes)
- **Responsibilities**:
  - Handle API Gateway requests
  - Process SQS messages
  - Manage file uploads to S3
  - Track sessions in DynamoDB
  - Coordinate with Validator Lambda

#### Validator Lambda (`perplexity-validator`)
- **Runtime**: Python 3.9
- **Memory**: 1024 MB
- **Timeout**: 600 seconds (10 minutes)
- **Responsibilities**:
  - Process Excel files
  - Call Perplexity API or Anthropic API
  - Generate validation results
  - Send email notifications
  - Update DynamoDB metrics

### 3. SQS Queues
- **Preview Queue**: `perplexity-validator-preview-queue.fifo`
  - Type: FIFO queue
  - For preview requests
- **Standard Queue**: `perplexity-validator-standard-queue`
  - Type: Standard queue
  - For full validation requests
- **Message Retention**: 4 days
- **Visibility Timeout**: 960 seconds
- **Event Source Mapping**: Triggers Interface Lambda

### 4. DynamoDB Tables

#### Core Processing Tables
- **Main Table**: `perplexity-validator-call-tracking`
  - Primary Key: `session_id` (String)
  - GSI: EmailDomainIndex, StatusIndex
  - Tracks all validation sessions
- **Token Usage Table**: `perplexity-validator-token-usage`
  - Composite Key: `session_id` (Hash), `timestamp` (Range)
  - Detailed API usage tracking

#### Email Validation Tables (New)
- **User Validation Table**: `perplexity-validator-user-validation`
  - Primary Key: `email` (String)
  - GSI: ValidationCodeIndex
  - Stores temporary validation codes (10-minute TTL)
  - Tracks validation attempts and expiry
- **User Tracking Table**: `perplexity-validator-user-tracking`
  - Primary Key: `email` (String)
  - GSI: EmailDomainIndex (email_domain + last_access)
  - Comprehensive user activity tracking

#### User Tracking Attributes
- **Identity**: `email`, `email_domain`, `created_at`
- **Validation History**:
  - `first_email_validation_request` - First time user requested validation
  - `most_recent_email_validation_request` - Most recent validation request
  - `first_email_validation` - First successful validation completion
  - `most_recent_email_validation` - Most recent successful validation
- **Usage Metrics**: 
  - `total_preview_requests`, `total_full_requests`
  - `total_tokens_used`, `total_cost_usd`
  - `perplexity_tokens`, `perplexity_cost`
  - `anthropic_tokens`, `anthropic_cost`
- **Access Tracking**: `last_access`

#### Processing Session Attributes
- **Status tracking**: Processing state and completion status
- **Processing metrics**: Time, rows processed, cost breakdown
- **API usage**: Perplexity and Anthropic token/cost tracking
- **Email delivery status**: Notification delivery confirmation
- **File metadata**: S3 keys, file sizes, reference PINs

### 5. S3 Buckets
- **Cache Bucket**: `perplexity-cache`
  - `/validation_cache/` - API response caching
  - `/lambda-packages/` - Lambda deployment packages
- **Results Bucket**: `perplexity-results`
  - `/uploads/{email_folder}/` - Original Excel and config files
  - `/results/{email_folder}/` - Validation result ZIPs
  - `/preview_results/{email_folder}/` - Preview JSON results
  - `/email/{email_folder}/` - Email content
  
Note: `{email_folder}` is derived from email domain (e.g., `eliyahu.ai/eliyahu` for `eliyahu@eliyahu.ai`)

### 6. IAM Roles

#### Lambda Execution Role
Required permissions:
- S3: Read/Write to validator bucket
- DynamoDB: Read/Write to validation table
- SQS: Receive/Delete messages
- SES: Send emails
- CloudWatch: Write logs
- Parameter Store: Read API keys

## Setup Guide

### Prerequisites
- AWS CLI configured with credentials
- Python 3.8+ installed
- Git repository cloned
- API key (Perplexity or Anthropic)

### Step 1: Store API Key
For Perplexity:
```bash
aws ssm put-parameter \
    --name "/Perplexity_API_Key" \
    --value "YOUR_PERPLEXITY_API_KEY" \
    --type SecureString
```

For Anthropic:
```bash
aws ssm put-parameter \
    --name "/Anthropic_API_Key" \
    --value "YOUR_ANTHROPIC_API_KEY" \
    --type SecureString
```

### Step 2: Deploy Validator Lambda
```bash
cd deployment
python create_package.py --deploy --force-rebuild
```

This will:
- Build the deployment package
- Create/update the Lambda function
- Configure environment variables
- Set up logging

### Step 3: Deploy Interface Lambda
```bash
python create_interface_package.py --deploy --force-rebuild
```

This will:
- Build the interface package
- Create/update the Lambda function
- Create API Gateway if needed
- Set up SQS event source mapping
- Configure all integrations
- **Create DynamoDB tables for email validation**

### Step 4: Verify Deployment
```bash
# Check Lambda functions
aws lambda list-functions --query "Functions[?contains(FunctionName, 'perplexity')].[FunctionName,State]"

# Check API Gateway
aws apigatewayv2 get-apis --query "Items[?Name=='PerplexityValidatorAPI']"

# Test with sample data
cd ..
python test_validation.py --mode sync_preview --preview-rows 1
```

## API Reference

### Base URL
```
https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod
```

### Authentication
Currently no authentication required (can be added via API Gateway)

### Endpoints

#### 1. POST /validate
Main validation endpoint supporting both sync and async modes.

**Request**:
- Method: `POST`
- Content-Type: `multipart/form-data`

**Form Fields**:
- `excel_file` (required): Excel file to validate
- `config` (required): JSON configuration file
- `email` (required): Email for results delivery

**Query Parameters**:
- `preview_first_row=true`: Enable preview mode
- `async=true`: Force asynchronous processing
- `max_rows=N`: Limit rows to process
- `batch_size=N`: Rows per batch (default: 5)

**Synchronous Response** (preview mode):
```json
{
  "statusCode": 200,
  "session_id": "20250701123456_abc123",
  "preview_results": {
    "results": {
      "Column1": ["value", 0.95, "validation message"],
      "Column2": ["value", 0.87, "validation message"]
    },
    "summary": {
      "total_cost": 0.05,
      "total_tokens": 1234,
      "processing_time": 2.5,
      "cache_hit_rate": 0.8
    },
    "markdown_table": "| Column | Value | Confidence | Message |\n|--------|-------|------------|---------|..."
  }
}
```

The `markdown_table` field contains a formatted table ready for display:
```markdown
| Column | Value | Confidence | Message |
|--------|-------|------------|---------|
| Product Name | Aspirin | HIGH (0.95) | Validated as correct pharmaceutical name |
| Development Stage | Phase 3 | MEDIUM (0.89) | Confirmed clinical trial phase |
```

**Asynchronous Response**:
```json
{
  "statusCode": 202,
  "message": "Validation job queued",
  "session_id": "20250701123456_abc123",
  "reference_pin": "ABC123"
}
```

#### 2. GET /status/{sessionId}
Check validation job status.

**Request**:
- Method: `GET`
- Path Parameter: `sessionId` - Session ID from async response

**Query Parameters**:
- `preview=true`: Check preview status instead of full validation

**Response**:
```json
{
  "session_id": "20250701123456_abc123",
  "status": "completed",
  "created_at": "2025-07-01T12:34:56Z",
  "completed_at": "2025-07-01T12:36:30Z",
  "result_s3_key": "results/20250701123456_abc123.zip",
  "email_sent": true,
  "metrics": {
    "processed_rows": 100,
    "total_cost_usd": 1.23,
    "processing_time_seconds": 94
  }
}
```

#### 3. POST /validate (Email Validation Actions)
Email validation endpoints using JSON actions.

##### Request Email Validation Code
**Request**:
```json
{
  "action": "requestEmailValidation",
  "email": "user@company.com"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Validation code sent to email",
  "expires_at": "2025-07-02T18:44:33.316871+00:00"
}
```

##### Validate Email Code
**Request**:
```json
{
  "action": "validateEmailCode",
  "email": "user@company.com", 
  "code": "123456"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Email validated successfully"
}
```

##### Get User Statistics
**Request**:
```json
{
  "action": "getUserStats",
  "email": "user@company.com"
}
```

**Response**:
```json
{
  "success": true,
  "stats": {
    "email": "user@company.com",
    "email_domain": "company.com",
    "first_email_validation_request": "2025-07-02T18:28:06.935505+00:00",
    "most_recent_email_validation_request": "2025-07-02T18:34:33.316871+00:00",
    "first_email_validation": "2025-07-02T18:33:36.857713+00:00",
    "most_recent_email_validation": "2025-07-02T18:34:51.226114+00:00",
    "total_preview_requests": 1,
    "total_full_requests": 0,
    "total_tokens_used": 100,
    "total_cost_usd": 0.01
  }
}
```

#### 4. POST /validate-config
Validate configuration file format.

**Request**:
- Method: `POST`
- Content-Type: `application/json`
- Body: Configuration JSON

**Response**:
```json
{
  "valid": true,
  "validation_targets": 5,
  "message": "Configuration is valid"
}
```

### Error Responses

All endpoints return consistent error format:

```json
{
  "statusCode": 400,
  "error": "ValidationError",
  "message": "Detailed error message",
  "details": {}
}
```

Common status codes:
- `400`: Bad Request (invalid input)
- `403`: Forbidden (email not validated)
- `404`: Not Found (session not found)
- `500`: Internal Server Error
- `504`: Gateway Timeout (sync request too long)

### Email Validation Error Responses

#### Email Not Validated
```json
{
  "statusCode": 403,
  "error": "email_not_validated", 
  "message": "Email address must be validated before processing. Please request and enter a validation code first."
}
```

#### Invalid Validation Code
```json
{
  "success": false,
  "error": "invalid_code",
  "message": "Invalid validation code"
}
```

#### Code Expired
```json
{
  "success": false,
  "error": "code_expired",
  "message": "Validation code has expired"
}
```

#### Too Many Attempts
```json
{
  "success": false,
  "error": "too_many_attempts", 
  "message": "Too many validation attempts"
}
```

## Testing Guide

### Using test_validation.py

The main test script provides comprehensive testing capabilities:

```bash
# Basic usage - runs all tests
python test_validation.py

# Test specific mode
python test_validation.py --mode sync_preview

# Use custom files
python test_validation.py \
    --excel "path/to/data.xlsx" \
    --config "path/to/config.json" \
    --name "my_test"

# Advanced options
python test_validation.py \
    --mode full_validation \
    --max-rows 50 \
    --preview-rows 5 \
    --output-dir "test_results" \
    --name "production_test"
```

### Test Modes

1. **sync_preview**: Tests synchronous preview (1-3 rows)
   - Immediate response
   - Good for config validation
   - Subject to 29-second timeout

2. **async_preview**: Tests asynchronous preview
   - Returns session ID
   - Polls for completion
   - Better for larger previews

3. **full_validation**: Tests complete validation
   - Always asynchronous
   - Sends email with results
   - Handles large datasets

### Test Output

Test results are saved in timestamped directories:
```
test_results/
└── 20250701_123456_my_test/
    ├── 00_test_config.json
    ├── 00_test_summary.json
    ├── 01_sync_preview_response.json
    ├── 01_sync_preview_table.md
    ├── 02_async_preview_response.json
    ├── 02_async_preview_table.md
    ├── 03_full_validation_response.json
    └── 03_full_validation_dynamodb.json
```

### Manual Testing

```python
import requests

base_url = "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod"

# Step 1: Validate email
email = "test@example.com"

# Request validation code
response = requests.post(f"{base_url}/validate", json={
    "action": "requestEmailValidation",
    "email": email
})
print("Validation code sent:", response.json())

# Validate with code (replace with actual code from email)
response = requests.post(f"{base_url}/validate", json={
    "action": "validateEmailCode", 
    "email": email,
    "code": "123456"
})
print("Validation result:", response.json())

# Step 2: Process files
files = {
    'excel_file': open('data.xlsx', 'rb'),
    'config': open('config.json', 'rb')
}
data = {'email': email}

# Sync preview  
response = requests.post(
    f'{base_url}/validate?preview_first_row=true',
    files=files,
    data=data
)

if response.status_code == 403:
    print("Email validation required!")
else:
    print("Processing successful:", response.json())

# Check status
session_id = response.json()['session_id']
status = requests.get(f'{base_url}/status/{session_id}')
```

### Email Validation Testing

```python
import requests

def test_email_validation_flow(base_url, email):
    """Test complete email validation flow"""
    
    print(f"🔐 Testing email validation for: {email}")
    
    # 1. Request validation code
    response = requests.post(f"{base_url}/validate", json={
        "action": "requestEmailValidation",
        "email": email
    })
    
    if not response.json().get('success'):
        print(f"❌ Failed to request validation: {response.json()}")
        return False
    
    print(f"✅ Validation code sent, expires at: {response.json()['expires_at']}")
    
    # 2. Simulate validation (in real testing, get code from email)
    code = input("📧 Enter 6-digit code from email: ")
    
    response = requests.post(f"{base_url}/validate", json={
        "action": "validateEmailCode",
        "email": email, 
        "code": code
    })
    
    if not response.json().get('success'):
        print(f"❌ Validation failed: {response.json()}")
        return False
    
    print("✅ Email validated successfully")
    
    # 3. Check user stats
    response = requests.post(f"{base_url}/validate", json={
        "action": "getUserStats",
        "email": email
    })
    
    if response.json().get('success'):
        stats = response.json()['stats']
        print(f"📊 User Stats:")
        print(f"  - First validation request: {stats.get('first_email_validation_request')}")
        print(f"  - First validation: {stats.get('first_email_validation')}")
        print(f"  - Total requests: {stats.get('total_preview_requests', 0) + stats.get('total_full_requests', 0)}")
        print(f"  - Total cost: ${stats.get('total_cost_usd', 0):.4f}")
    
    return True

# Test it
test_email_validation_flow(
    "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod",
    "test@example.com"
)
```

## Troubleshooting

### Common Issues

1. **504 Gateway Timeout**
   - Cause: Sync request exceeding 29-second limit
   - Solution: Use async mode or reduce row count

2. **Session Not Found**
   - Cause: Invalid session ID or timestamp mismatch
   - Solution: Check DynamoDB for correct session ID

3. **No Email Received**
   - Check: SES configuration and verified domains
   - Check: Email address in S3 path (lowercase)
   - Check: DynamoDB for email_sent status

4. **Processing Stuck**
   - Check: CloudWatch logs for Lambda errors
   - Check: SQS dead letter queue
   - Check: Lambda concurrent execution limits

### Debugging Tools

1. **CloudWatch Logs**:
   ```bash
   # Interface Lambda logs
aws logs tail /aws/lambda/perplexity-validator-interface --follow

# Validator Lambda logs
aws logs tail /aws/lambda/perplexity-validator --follow
   ```

2. **DynamoDB Console**:
   - Check session status
   - View processing metrics
   - Track error messages

3. **S3 Browser**:
   - Verify file uploads
   - Check result files
   - Review email content

### Performance Optimization

1. **Batch Size**: Adjust based on complexity
   - Simple validations: 10-20 rows
   - Complex validations: 3-5 rows

2. **Caching**: Leverage S3 cache
   - Cache TTL: 30 days default
   - Hit rate typically 70-80%

3. **Concurrency**: Lambda limits
   - Reserved concurrency: 10
   - Can be increased if needed

### Monitoring Metrics

Key metrics to track:
- Lambda invocation count
- Lambda duration
- API Gateway 4xx/5xx errors
- SQS message age
- DynamoDB read/write capacity
- S3 storage usage

## Maintenance

### Updating Lambda Code

```bash
# Update validator
cd deployment
python create_package.py --deploy --no-rebuild

# Update interface (rebuild if dependencies changed)
python create_interface_package.py --deploy --force-rebuild
```

### Clearing Cache

```bash
# Clear old cache entries
aws s3 rm s3://perplexity-validator-bucket/cache/ --recursive --exclude "*" --include "*2024*"
```

### Monitoring Costs

Track costs via:
- Lambda invocation costs
- API Gateway request costs
- S3 storage and transfer
- DynamoDB capacity (Pay-per-request mode)
- API usage (Perplexity or Anthropic)
  - Tracked in DynamoDB per session
  - Separate cost tracking for each provider 