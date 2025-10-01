# SQS Setup Status Check

## What We Didn't Remove
The interface lambda STILL uses SQS for self-triggering:
- Preview queue → Interface Lambda
- Standard queue → Interface Lambda  

## What We DID Remove
Only validator-related SQS:
- ~~Async queue → Validator~~ (now direct invoke)
- ~~Completion queue → Interface~~ (now direct invoke)

## Why Preview Not Processing

Possible issues:
1. **Event Source Mapping Not Created**
   - Check: `aws lambda list-event-source-mappings --function-name perplexity-interface-function-dev`
   - Should show mapping for preview queue

2. **Event Source Mapping Disabled**
   - State might be "Disabled" instead of "Enabled"

3. **Queue Doesn't Exist**
   - Check: `aws sqs list-queues | grep preview`

4. **Permissions Issue**
   - Lambda needs `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`

5. **Wrong Queue ARN**
   - Mapping points to wrong queue

## How to Check

```bash
# Check if event source mapping exists
aws lambda list-event-source-mappings \
  --function-name perplexity-interface-function-dev \
  --region us-east-1

# Check queue exists
aws sqs list-queues --region us-east-1 | grep preview

# Get queue attributes  
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/400232868802/perplexity-validator-preview-queue \
  --attribute-names All \
  --region us-east-1
```

## Solution
Run deployment with proper SQS setup:
```bash
python.exe deployment/create_interface_package.py --env dev --deploy
```

This will:
1. Create/verify queues exist
2. Create event source mappings
3. Enable the mappings
