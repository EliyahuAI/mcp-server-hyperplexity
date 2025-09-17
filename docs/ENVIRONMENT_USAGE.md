# Environment Management Guide

This guide explains how to use the environment management system to deploy to different environments (dev, test, staging, prod).

## Overview

The system supports multiple deployment environments with separate AWS resources for each environment. This allows you to:

- Develop and test changes without affecting production
- Maintain stable production while working on new features
- Run parallel testing in different environments
- Use git branches to match deployment environments

## Supported Environments

- **dev**: Development environment for active development
- **test**: Testing environment for QA and integration testing  
- **staging**: Pre-production environment for final validation
- **prod**: Production environment (default, maintains existing behavior)

## Architecture Overview

### Environment Isolation Strategy

The system uses a **hybrid isolation approach** optimized for development workflow:

**Isolated Resources (Environment-Specific):**
- Lambda functions with `-dev`, `-test`, `-staging` suffixes
- API Gateway REST APIs with environment-specific stages
- S3 unified storage buckets for validation data

**Shared Resources (Cross-Environment):**
- DynamoDB tables (user tracking, validation runs, WebSocket connections)
- WebSocket API Gateway (shared API using /prod stage for all environments)
- Downloads S3 bucket (public download files)
- Cache S3 bucket (AI responses, validation cache - shared for efficiency)

This approach provides development isolation while maintaining centralized user data and connection tracking.

## Quick Start

### Deploy to Different Environments

```bash
# Deploy to production (default)
./deploy_all.sh

# Deploy to development environment
./deploy_all.sh --environment dev

# Deploy to test environment with force rebuild
./deploy_all.sh --environment test --force-rebuild

# Deploy to staging
./deploy_all.sh -e staging
```

### Deploy Individual Lambdas

```bash
# Deploy just the interface lambda to dev
python.exe deployment/create_interface_package.py --deploy --environment dev

# Deploy just the validation lambda to test
python.exe deployment/create_package.py --deploy --environment test

# Deploy just the config lambda to staging
python.exe deployment/deploy_config_lambda.py --deploy --environment staging
```

### Test Deployments

```bash
# Test specific environment lambdas
python.exe deployment/create_package.py --test-only --environment dev
python.exe deployment/create_interface_package.py --test-websocket --environment dev
python.exe deployment/deploy_config_lambda.py --test --environment staging
```

## Environment Resource Mapping

### Current Implementation (Dev Environment)

| Resource Type | Production | Development | Notes |
|---------------|------------|-------------|-------|
| **Interface Lambda** | `perplexity-validator-interface` | `perplexity-validator-interface-dev` | ✅ Isolated |
| **Validation Lambda** | `perplexity-validator` | `perplexity-validator-dev` | ✅ Isolated |
| **Config Lambda** | `perplexity-validator-config` | `perplexity-validator-config-dev` | ✅ Isolated |
| **REST API Gateway** | `a0tk95o95g` (prod stage) | `wqamcddvub` (dev stage) | ✅ Isolated |
| **WebSocket API** | `xt6790qk9f` (prod stage) | `xt6790qk9f` (prod stage) | 🔗 Shared API & Stage |
| **S3 Unified Storage** | `hyperplexity-storage` | `hyperplexity-storage-dev` | ✅ Isolated |
| **S3 Downloads** | `hyperplexity-downloads` | `hyperplexity-downloads` | 🔗 Shared |
| **S3 Cache** | `hyperplexity-storage` | `hyperplexity-storage` | 🔗 Shared |
| **DynamoDB Tables** | All tables | All tables | 🔗 Shared |

### Lambda Environment Variables

**Dev Interface Lambda** (`perplexity-validator-interface-dev`):
```bash
DEPLOYMENT_ENVIRONMENT=dev
VALIDATOR_LAMBDA_NAME=perplexity-validator-dev  # Calls dev validation lambda
CONFIG_LAMBDA_NAME=perplexity-validator-config-dev  # Calls dev config lambda
S3_UNIFIED_BUCKET=hyperplexity-storage-dev      # Uses dev storage
S3_DOWNLOAD_BUCKET=hyperplexity-downloads       # Shared downloads
S3_CACHE_BUCKET=hyperplexity-storage           # Shared cache
WEBSOCKET_API_URL=wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod  # Shared WebSocket
```

**Dev Validation Lambda** (`perplexity-validator-dev`):
```bash
DEPLOYMENT_ENVIRONMENT=dev
S3_UNIFIED_BUCKET=hyperplexity-storage-dev      # Uses dev storage
S3_CACHE_BUCKET=hyperplexity-storage           # Shared cache
```

**Dev Config Lambda** (`perplexity-validator-config-dev`):
```bash
DEPLOYMENT_ENVIRONMENT=dev
S3_UNIFIED_BUCKET=hyperplexity-storage-dev      # Uses dev storage
S3_CACHE_BUCKET=hyperplexity-storage           # Shared cache
WEBSOCKET_API_URL=wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod  # Shared WebSocket
```

## Frontend Environment Support

The frontend automatically detects the environment and uses the appropriate API endpoints:

### Access Different Environments

#### Method 1: Page Name Detection (Squarespace-friendly)
```
# Production (default)
https://your-domain.com/validator

# Development environment  
https://your-domain.com/validator-dev

# Test environment
https://your-domain.com/validator-test

# Staging environment
https://your-domain.com/validator-staging
```

#### Method 2: URL Parameters (for testing/overrides)
```
# Development environment
https://your-domain.com/validator?env=dev

# Test environment  
https://your-domain.com/validator?environment=test

# Staging environment
https://your-domain.com/validator?env=staging
```

#### Method 3: Console Commands (persistent preference)
```javascript
// Set environment preference (saved in browser)
hyperplexityEnv.set('dev')     // Switch to dev and save preference
hyperplexityEnv.set('test')    // Switch to test and save preference
hyperplexityEnv.clear()        // Clear saved preference

// Check current environment
hyperplexityEnv.current()      // Shows: 'dev', 'test', 'staging', or 'prod'
hyperplexityEnv.available()    // Shows: ['dev', 'test', 'staging', 'prod']
```

### Environment Indicator

When accessing non-production environments, an environment indicator appears in the top-right corner showing which environment you're using.

### Frontend API Configuration

**Current API Endpoints** (as of latest update):

```javascript
const ENV_CONFIGS = {
    dev: {
        apiBase: 'https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev',
        websocketUrl: 'wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod',  // Shared WebSocket
        // ... other config
    },
    prod: {
        apiBase: 'https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod',
        websocketUrl: 'wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod',  // Shared WebSocket
        // ... other config
    }
}
```

## Configuration Files

### deployment/environments.json
Contains environment-specific configurations:
```json
{
  "dev": {
    "resource_suffix": "-dev",
    "s3_unified_bucket": "hyperplexity-storage-dev",
    "s3_download_bucket": "hyperplexity-downloads",
    "api_gateway_stage": "dev",
    "environment_tag": "development"
  },
  "prod": {
    "resource_suffix": "",
    "s3_unified_bucket": "hyperplexity-storage",
    "s3_download_bucket": "hyperplexity-downloads",
    "api_gateway_stage": "prod",
    "environment_tag": "production"
  }
}
```

### deployment/environment_config.py
Helper module that:
- Loads environment configurations
- Applies environment-specific naming to resources
- Provides environment-aware configuration objects
- Handles cross-references (e.g., interface lambda → validation lambda)

## Data Flow Architecture

### Development Environment Request Flow

```
1. Frontend (validator-dev) 
   ↓
2. API Gateway (wqamcddvub.execute-api.us-east-1.amazonaws.com/dev)
   ↓  
3. Interface Lambda (perplexity-validator-interface-dev)
   ↓
4. Validation Lambda (perplexity-validator-dev)
   ↓
5. S3 Storage (hyperplexity-storage-dev) + Cache (hyperplexity-storage, shared)
   ↓
6. Config Lambda (perplexity-validator-config-dev) for AI configuration generation
   ↓
7. DynamoDB Tables (shared: perplexity-validator-runs, etc.)
   ↓
8. WebSocket API (xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod, shared)
   ↓
9. WebSocket Handler (perplexity-validator-ws-handler, shared)
```

### Key Environment Boundaries

- **API Requests**: Completely isolated per environment
- **Processing**: Environment-specific lambdas and storage
- **User Data**: Centralized in shared DynamoDB tables
- **Real-time Updates**: Shared WebSocket infrastructure using production stage for all environments
- **AI Cache**: Shared cache bucket for improved performance across all environments

## CloudWatch Logs

Each environment maintains separate CloudWatch log groups:

```bash
# Production logs
/aws/lambda/perplexity-validator
/aws/lambda/perplexity-validator-interface
/aws/lambda/perplexity-validator-config

# Development logs  
/aws/lambda/perplexity-validator-dev
/aws/lambda/perplexity-validator-interface-dev
/aws/lambda/perplexity-validator-config-dev

# Shared WebSocket logs
/aws/lambda/perplexity-validator-ws-handler
```

## Testing and Verification

### Verify Environment Setup
```bash
# Test environment configuration
python.exe deployment/environment_config.py dev

# Check lambda environment variables
aws lambda get-function-configuration --function-name perplexity-validator-interface-dev

# Test API endpoints
curl https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev/health
```

### End-to-End Testing
```bash
# Test complete dev environment
./deploy_all.sh --environment dev

# Test individual components
python.exe deployment/create_interface_package.py --test-api --environment dev
python.exe deployment/create_package.py --run-test --environment dev
```

## Common Workflows

### Feature Development
```bash
# 1. Create feature branch
git checkout -b feature/new-validator develop

# 2. Deploy to dev for testing
./deploy_all.sh --environment dev

# 3. Test via frontend
# Visit: https://your-domain.com/validator-dev

# 4. Deploy to staging for final validation
./deploy_all.sh --environment staging

# 5. Merge to main and deploy to production
git checkout main
git merge feature/new-validator
./deploy_all.sh
```

### Debugging Environment Issues
```bash
# Check all environment configurations
python.exe deployment/environment_config.py dev
python.exe deployment/environment_config.py prod

# Compare lambda configurations
aws lambda get-function-configuration --function-name perplexity-validator
aws lambda get-function-configuration --function-name perplexity-validator-dev

# Check API Gateway stages
aws apigateway get-stages --rest-api-id wqamcddvub
aws apigateway get-stages --rest-api-id a0tk95o95g
```

## Troubleshooting

### CORS Issues
If you see CORS errors in dev environment:
1. Verify API Gateway stage exists: `aws apigateway get-stages --rest-api-id wqamcddvub`
2. Check frontend points to correct stage: look for `/dev` vs `/prod` in URL
3. Redeploy interface lambda: `python.exe deployment/create_interface_package.py --deploy --environment dev`

### Lambda Cross-References
If dev interface lambda calls production validation lambda:
1. Check `VALIDATOR_LAMBDA_NAME` environment variable
2. Should be `perplexity-validator-dev` not `perplexity-validator`
3. Redeploy with: `python.exe deployment/create_interface_package.py --deploy --environment dev`

### Environment Not Working
- Verify environment parameter is one of: `dev`, `test`, `staging`, `prod`
- Check that `deployment/environments.json` exists and is valid
- Ensure `environment_config.py` is properly imported in deployment scripts
- Check CloudWatch logs for specific error messages

## Recent Fixes and Improvements

### Environment System Fixes (September 2025)
1. **Fixed API Gateway stage routing**: Dev API now correctly uses `/dev` stage instead of `/prod`
2. **Fixed lambda cross-references**: Dev interface lambda now calls `perplexity-validator-dev` and `perplexity-validator-config-dev`
3. **Fixed WebSocket infrastructure**: Shared WebSocket API using `/prod` stage for all environments
4. **Fixed S3 bucket configuration**: Dev config lambda now reads from correct dev storage bucket
5. **Added shared cache**: All environments use shared cache bucket for efficiency
6. **Added environment-aware testing**: All deployment scripts now test correct environment lambdas
7. **Updated frontend API configuration**: Correct dev API Gateway URL and shared WebSocket URL

### Architecture Decisions
- **Shared DynamoDB**: All environments use same tables for centralized user/run tracking
- **Shared WebSocket API**: Single WebSocket API Gateway using `/prod` stage for all environments
- **Shared Downloads**: Single public downloads bucket across environments
- **Shared Cache**: Single cache bucket (`hyperplexity-storage`) for AI responses and validation cache
- **Isolated Processing**: Separate Lambda functions and storage per environment
- **Hybrid Resource Strategy**: Isolate processing while sharing optimization resources

## Backward Compatibility

All existing deployment commands continue to work exactly as before:
- `./deploy_all.sh` still deploys to production
- All Lambda function names and S3 bucket names remain unchanged for production
- No breaking changes to existing workflows