# Quick Setup Guide - Perplexity Validator

Get up and running in 5 minutes!

## Prerequisites

- AWS CLI installed and configured
- Python 3.8+
- Perplexity API key

## 1. Clone and Setup (1 minute)

```bash
git clone <repository-url>
cd perplexityValidator
pip install requests boto3
```

## 2. Store API Key (1 minute)

```bash
aws ssm put-parameter \
    --name "/Perplexity_API_Key" \
    --value "YOUR_API_KEY_HERE" \
    --type SecureString
```

## 3. Deploy Lambdas (3 minutes)

```bash
cd deployment

# Deploy core validator
python create_package.py --deploy --force-rebuild

# Deploy interface with API Gateway
python create_interface_package.py --deploy --force-rebuild
```

## 4. Test It! (1 minute)

```bash
cd ..
python test_validation.py --mode sync_preview --preview-rows 1
```

## That's It! 🎉

You now have a working Perplexity Validator system with email validation enabled.

⚠️ **Note**: All users must validate their email address before processing Excel files. The system will automatically prompt for email validation during testing.

## What You Can Do Now

### Test with Example Data
```bash
# Test Congress Master List validation
python test_validation.py --name "congress_test"
```

### Validate Your Own Data
```bash
python test_validation.py \
    --excel "your_data.xlsx" \
    --config "your_config.json" \
    --mode full_validation \
    --max-rows 10
```

### Check Results
- Look in `test_results/` for detailed output
- Check your email for validation results
- View DynamoDB for session tracking

## API Endpoint

Your API is now available at:
```
https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod
```

## Next Steps

- Read [INFRASTRUCTURE_GUIDE.md](INFRASTRUCTURE_GUIDE.md) for detailed documentation
- Check [QUICK_START.md](QUICK_START.md) for more examples
- Review example configurations in `tables/` 