# API Gateway Configuration for Email Endpoints

## Overview
This guide shows how to configure API Gateway to support the email validation endpoints that the GPT Actions require.

## New Endpoints to Add

### 1. /validate-email (POST)
**Purpose**: Request email validation code

**Integration Configuration**:
- Integration Type: Lambda Function
- Lambda Function: perplexity-validator-interface
- Use Lambda Proxy Integration: NO (unchecked)

**Mapping Template** (Content-Type: application/json):
```vtl
{
  "httpMethod": "POST",
  "path": "/validate",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": "{\"action\": \"requestEmailValidation\", \"email\": \"$input.path('$.email')\"}"
}
```

### 2. /verify-email (POST)
**Purpose**: Verify email validation code

**Integration Configuration**:
- Integration Type: Lambda Function
- Lambda Function: perplexity-validator-interface
- Use Lambda Proxy Integration: NO (unchecked)

**Mapping Template** (Content-Type: application/json):
```vtl
{
  "httpMethod": "POST",
  "path": "/validate",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": "{\"action\": \"validateEmailCode\", \"email\": \"$input.path('$.email')\", \"code\": \"$input.path('$.code')\"}"
}
```

### 3. /check-email (POST)
**Purpose**: Check if email is already validated

**Integration Configuration**:
- Integration Type: Lambda Function
- Lambda Function: perplexity-validator-interface
- Use Lambda Proxy Integration: NO (unchecked)

**Mapping Template** (Content-Type: application/json):
```vtl
{
  "httpMethod": "POST",
  "path": "/validate",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": "{\"action\": \"checkEmailValidation\", \"email\": \"$input.path('$.email')\"}"
}
```

### 4. /check-or-send (POST)
**Purpose**: Check if email is validated, automatically send code if not

**Integration Configuration**:
- Integration Type: Lambda Function
- Lambda Function: perplexity-validator-interface
- Use Lambda Proxy Integration: NO (unchecked)

**Mapping Template** (Content-Type: application/json):
```vtl
{
  "httpMethod": "POST",
  "path": "/validate",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": "{\"action\": \"checkOrSendValidation\", \"email\": \"$input.path('$.email')\"}"
}
```

## Step-by-Step Instructions

### Using AWS Console:

1. **Open API Gateway**
   - Navigate to your API (should be named something like "perplexity-validator-api")

2. **Create /validate-email Resource**
   - Click on "/" root resource
   - Actions → Create Resource
   - Resource Name: validate-email
   - Resource Path: /validate-email
   - Click "Create Resource"

3. **Create POST Method for /validate-email**
   - Select the new /validate-email resource
   - Actions → Create Method → POST
   - Integration type: Lambda Function
   - Lambda Region: us-east-1 (or your region)
   - Lambda Function: perplexity-validator-interface
   - Use Lambda Proxy Integration: **UNCHECKED**
   - Save

4. **Configure Integration Request**
   - Click on "Integration Request"
   - Mapping Templates → Add mapping template
   - Content-Type: application/json
   - Generate template: No
   - Paste the mapping template from above

5. **Repeat for /verify-email**
   - Follow steps 2-4 for /verify-email endpoint

6. **Deploy API**
   - Actions → Deploy API
   - Deployment stage: prod
   - Deploy

### Using AWS CLI:

```bash
# Create /validate-email resource
aws apigateway create-resource \
  --rest-api-id YOUR_API_ID \
  --parent-id YOUR_ROOT_RESOURCE_ID \
  --path-part validate-email

# Create POST method
aws apigateway put-method \
  --rest-api-id YOUR_API_ID \
  --resource-id NEW_RESOURCE_ID \
  --http-method POST \
  --authorization-type NONE

# Configure integration
aws apigateway put-integration \
  --rest-api-id YOUR_API_ID \
  --resource-id NEW_RESOURCE_ID \
  --http-method POST \
  --type AWS \
  --integration-http-method POST \
  --uri arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/YOUR_LAMBDA_ARN/invocations \
  --request-templates '{"application/json": "{\"httpMethod\": \"POST\", \"path\": \"/validate\", \"headers\": {\"Content-Type\": \"application/json\"}, \"body\": \"{\\\"action\\\": \\\"requestEmailValidation\\\", \\\"email\\\": \\\"$input.path('"'"'$.email'"'"')\\\"}\"}"}' 
```

## Testing

After deployment, test the endpoints:

```bash
# Request validation code
curl -X POST https://YOUR_API_URL/prod/validate-email \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Verify code
curl -X POST https://YOUR_API_URL/prod/verify-email \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "code": "123456"}'

# Check if email is validated
curl -X POST https://YOUR_API_URL/prod/check-email \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Check or send (combined operation)
curl -X POST https://YOUR_API_URL/prod/check-or-send \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'
```

## Important Notes

1. **Lambda Proxy Integration MUST be disabled** - We need to transform the request
2. **The Lambda function expects the original /validate path** - The mapping template handles this
3. **CORS headers** - May need to be configured if calling from a browser
4. **IAM Permissions** - API Gateway needs permission to invoke the Lambda function 