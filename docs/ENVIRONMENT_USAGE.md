# Environment Management Guide

This guide explains how to use the new environment management system to deploy to different environments (dev, test, staging, prod).

## Overview

The system now supports multiple deployment environments with separate AWS resources for each environment. This allows you to:

- Develop and test changes without affecting production
- Maintain stable production while working on new features
- Run parallel testing in different environments
- Use git branches to match deployment environments

## Supported Environments

- **dev**: Development environment for active development
- **test**: Testing environment for QA and integration testing  
- **staging**: Pre-production environment for final validation
- **prod**: Production environment (default, maintains existing behavior)

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

## Git-Based Workflow

Use git branches to match your deployment environments:

```bash
# Work on main branch, deploy to production
git checkout main
./deploy_all.sh

# Switch to develop branch, deploy to dev environment
git checkout develop
./deploy_all.sh --environment dev

# Create feature branch from develop, test in dev
git checkout -b feature/new-validation develop
# Make changes...
./deploy_all.sh --environment dev

# Test in staging before merging
git checkout staging
git merge feature/new-validation
./deploy_all.sh --environment staging
```

## Frontend Environment Support

The frontend automatically detects the environment and uses the appropriate API endpoints:

### Access Different Environments

The frontend automatically detects the environment in multiple ways:

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

## Resource Naming Convention

Resources are automatically named with environment suffixes:

### Lambda Functions
- **Production**: `perplexity-validator-interface`
- **Development**: `perplexity-validator-interface-dev`
- **Test**: `perplexity-validator-interface-test`
- **Staging**: `perplexity-validator-interface-staging`

### S3 Buckets
- **Production**: `hyperplexity-storage`, `hyperplexity-downloads`
- **Development**: `hyperplexity-storage-dev`, `hyperplexity-downloads-dev`
- **Test**: `hyperplexity-storage-test`, `hyperplexity-downloads-test`
- **Staging**: `hyperplexity-storage-staging`, `hyperplexity-downloads-staging`

## Configuration Files

### deployment/environments.json
Contains environment-specific configurations:
- Resource suffixes
- S3 bucket names
- API Gateway stages
- Environment tags

### deployment/environment_config.py
Helper module that:
- Loads environment configurations
- Applies environment-specific naming to resources
- Provides environment-aware configuration objects

## API Gateway Setup

**Note**: The current implementation includes placeholder API Gateway IDs for dev/test/staging environments. You'll need to:

1. Create separate API Gateway deployments for each environment
2. Update the API Gateway IDs in `deployment/environment_config.py`
3. Update the corresponding URLs in the frontend environment configuration

## Examples

### Deploy Everything to Development
```bash
./deploy_all.sh --environment dev
```

### Test Configuration Changes in Staging
```bash
# Deploy only config lambda to staging
python.exe deployment/deploy_config_lambda.py --deploy --environment staging --force-rebuild
```

### Access Development Frontend
Visit: `https://your-domain.com/validator-dev` (or `https://your-domain.com/validator?env=dev`)

## Troubleshooting

### Check Environment Configuration
```bash
# Test environment configuration
python.exe deployment/environment_config.py dev
```

### Verify Deployment
After deployment, check the AWS console to ensure resources were created with the correct environment suffixes.

### Environment Not Working
- Verify the environment parameter is one of: dev, test, staging, prod
- Check that the environments.json file exists and is valid
- Ensure environment_config.py is properly imported in deployment scripts

## Backward Compatibility

All existing deployment commands continue to work exactly as before:
- `./deploy_all.sh` still deploys to production
- All Lambda function names and S3 bucket names remain unchanged for production
- No breaking changes to existing workflows