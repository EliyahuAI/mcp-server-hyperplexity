# Security Fixes - Deployment Instructions

## Quick Start Deployment

Follow these steps to deploy the security fixes to your production environment.

---

## Prerequisites

1. AWS CLI configured with appropriate credentials
2. Python 3.9+ installed
3. Access to Lambda functions and S3 buckets
4. PyJWT package installed

---

## Step 1: Install Dependencies

```bash
# Install PyJWT for session token management
pip install PyJWT==2.8.0

# If using Lambda layers, update the layer
cd deployment/lambda_layer/python
pip install -t . PyJWT==2.8.0
cd ../..
zip -r lambda_layer.zip python/

# Upload to Lambda layer
aws lambda publish-layer-version \
  --layer-name hyperplexity-dependencies \
  --zip-file fileb://lambda_layer.zip \
  --compatible-runtimes python3.9 python3.10 python3.11
```

---

## Step 2: Set JWT Secret Key (CRITICAL)

**WARNING:** The default JWT secret MUST be changed before production deployment!

```bash
# Generate a secure random key
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Set as Lambda environment variable
aws lambda update-function-configuration \
  --function-name perplexity-validator-interface \
  --environment Variables="{JWT_SECRET_KEY=$JWT_SECRET}"

# Verify it was set
aws lambda get-function-configuration \
  --function-name perplexity-validator-interface \
  --query 'Environment.Variables.JWT_SECRET_KEY'
```

**Save this key in your password manager - you'll need it if you redeploy!**

---

## Step 3: Deploy Backend Changes

```bash
# Navigate to project root
cd /mnt/c/Users/ellio/OneDrive\ -\ Eliyahu.AI/Desktop/src/perplexityValidator

# Package Lambda function (if you have a deployment script)
# Otherwise, manually zip and upload:

# Create deployment package
cd src/lambdas/interface
zip -r ../../../interface_lambda.zip . -x "*.pyc" -x "__pycache__/*"
cd ../../shared
zip -r ../../interface_lambda.zip . -x "*.pyc" -x "__pycache__/*"
cd ../..

# Upload to Lambda
aws lambda update-function-code \
  --function-name perplexity-validator-interface \
  --zip-file fileb://interface_lambda.zip

# Wait for update to complete
aws lambda wait function-updated \
  --function-name perplexity-validator-interface

echo "✅ Backend deployed successfully"
```

---

## Step 4: Update S3 CORS Configuration

```bash
# Update allowed origins in the file first
# Edit deployment/create_unified_s3_bucket.py lines 269-280
# Replace with your production domains:
#   - https://yourdomain.com
#   - https://www.yourdomain.com

# Then apply CORS configuration
python3 deployment/create_unified_s3_bucket.py --update-cors-only

# Verify CORS was applied
aws s3api get-bucket-cors \
  --bucket perplexity-validator-results

echo "✅ CORS configuration updated"
```

---

## Step 5: Build and Deploy Frontend

```bash
# Build frontend with updated JavaScript
python3 frontend/build.py

# The output will be at:
# frontend/Hyperplexity_FullScript_Temp-dev.html

# Upload to your hosting (adjust bucket name as needed)
aws s3 cp frontend/Hyperplexity_FullScript_Temp-dev.html \
  s3://your-frontend-bucket/index.html \
  --content-type "text/html" \
  --cache-control "max-age=300"

echo "✅ Frontend deployed successfully"
```

---

## Step 6: Verify Deployment

Run these tests to ensure security fixes are working:

### Test 1: Session Token Issuance

```bash
# Request email validation
curl -X POST https://your-api-domain/validate \
  -H "Content-Type: application/json" \
  -d '{"action": "requestEmailValidation", "email": "test@example.com"}'

# Check email for code, then validate (replace CODE with actual code)
curl -X POST https://your-api-domain/validate \
  -H "Content-Type: application/json" \
  -d '{"action": "validateEmailCode", "email": "test@example.com", "code": "CODE"}'

# Expected response should include "session_token" field
# Example: {"success": true, "validated": true, "session_token": "eyJ..."}
```

### Test 2: Ownership Verification

```bash
# Try to access a session you don't own (should fail)
curl -X POST https://your-api-domain/validate \
  -H "Content-Type: application/json" \
  -d '{
    "action": "getViewerData",
    "email": "attacker@example.com",
    "session_id": "session_12345678_123456_abcd1234"
  }'

# Expected: 403 Forbidden - "Access denied: you do not own this session"
```

### Test 3: Rate Limiting

```bash
# Send 15 requests rapidly (should be rate limited after 10)
for i in {1..15}; do
  echo "Request $i:"
  curl -X POST https://your-api-domain/validate \
    -H "Content-Type: application/json" \
    -d '{"action": "getViewerData", "email": "test@example.com", "session_id": "session_test"}' \
    -w "\nHTTP Status: %{http_code}\n\n"
done

# Expected: First ~10 succeed, then 429 Too Many Requests
```

### Test 4: Session ID Format Validation

```bash
# Try path traversal
curl -X POST https://your-api-domain/validate \
  -H "Content-Type: application/json" \
  -d '{
    "action": "getViewerData",
    "email": "test@example.com",
    "session_id": "../../etc/passwd"
  }'

# Expected: 400 Bad Request - "Invalid session ID format"
```

---

## Step 7: Set Up CloudWatch Monitoring

```bash
# Create CloudWatch dashboard (optional but recommended)
cat > cloudwatch-dashboard.json << 'EOF'
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "title": "Security Violations",
        "metrics": [
          ["Hyperplexity/Security", "ownership_violation"],
          [".", "rate_limit_exceeded"],
          [".", "invalid_session_format"],
          [".", "path_traversal_attempt"]
        ],
        "period": 300,
        "stat": "Sum",
        "region": "us-east-1",
        "yAxis": {"left": {"label": "Count"}}
      }
    }
  ]
}
EOF

aws cloudwatch put-dashboard \
  --dashboard-name HyperplexitySecurity \
  --dashboard-body file://cloudwatch-dashboard.json

echo "✅ CloudWatch dashboard created"

# View dashboard
echo "Dashboard URL: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=HyperplexitySecurity"
```

---

## Step 8: Configure CloudWatch Alarms

```bash
# Alarm for ownership violations (>5 per hour is suspicious)
aws cloudwatch put-metric-alarm \
  --alarm-name "Hyperplexity-OwnershipViolations" \
  --alarm-description "Alert when ownership violations exceed threshold" \
  --metric-name ownership_violation \
  --namespace Hyperplexity/Security \
  --statistic Sum \
  --period 3600 \
  --evaluation-periods 1 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold

# Alarm for path traversal attempts (>1 per hour is an attack)
aws cloudwatch put-metric-alarm \
  --alarm-name "Hyperplexity-PathTraversal" \
  --alarm-description "Alert on path traversal attempts" \
  --metric-name path_traversal_attempt \
  --namespace Hyperplexity/Security \
  --statistic Sum \
  --period 3600 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold

echo "✅ CloudWatch alarms configured"
```

---

## Step 9: Test Frontend Integration

1. Open your frontend URL in a browser
2. Validate your email address
3. Check browser DevTools → Application → Session Storage
4. Verify `sessionToken` is stored (should start with "eyJ")
5. Upload a file and check that viewer mode works
6. Verify download links work

---

## Rollback Procedure (If Needed)

If issues arise, follow these steps:

### Quick Rollback (5 minutes)

```bash
# 1. Revert Lambda to previous version
aws lambda update-function-code \
  --function-name perplexity-validator-interface \
  --zip-file fileb://backup/interface_lambda_backup.zip

# 2. Remove JWT environment variable (makes backend accept emails)
aws lambda update-function-configuration \
  --function-name perplexity-validator-interface \
  --environment Variables={}

# 3. Revert frontend
aws s3 cp backup/index.html s3://your-frontend-bucket/index.html

echo "✅ Rollback complete"
```

### Create Backup Before Deployment

```bash
# Backup current Lambda code
aws lambda get-function \
  --function-name perplexity-validator-interface \
  --query 'Code.Location' \
  --output text | xargs wget -O backup/interface_lambda_backup.zip

# Backup current frontend
aws s3 cp s3://your-frontend-bucket/index.html backup/index.html

echo "✅ Backups created in backup/"
```

---

## Post-Deployment Checklist

- [ ] JWT_SECRET_KEY set in Lambda environment
- [ ] PyJWT package installed in Lambda layer
- [ ] Backend Lambda deployed successfully
- [ ] S3 CORS updated with production domains
- [ ] Frontend built and deployed
- [ ] Test 1: Session tokens issued ✓
- [ ] Test 2: Ownership verification works ✓
- [ ] Test 3: Rate limiting works ✓
- [ ] Test 4: Session ID validation works ✓
- [ ] CloudWatch dashboard created
- [ ] CloudWatch alarms configured
- [ ] Frontend session storage contains tokens
- [ ] Viewer mode works with tokens
- [ ] Download links work

---

## Troubleshooting

### "Invalid or missing session token" Error

**Cause:** JWT_SECRET_KEY not set or frontend not sending token

**Fix:**
1. Verify JWT_SECRET_KEY is set: `aws lambda get-function-configuration --function-name perplexity-validator-interface`
2. Check browser DevTools → Application → Session Storage for `sessionToken`
3. Check Network tab → Headers → `X-Session-Token` is being sent

### "Module 'jwt' not found" Error

**Cause:** PyJWT not installed in Lambda environment

**Fix:**
```bash
# Add PyJWT to Lambda layer
cd deployment/lambda_layer/python
pip install -t . PyJWT==2.8.0
cd ../..
zip -r lambda_layer.zip python/
aws lambda publish-layer-version --layer-name hyperplexity-dependencies --zip-file fileb://lambda_layer.zip
```

### "CORS policy: No 'Access-Control-Allow-Origin' header" Error

**Cause:** Frontend domain not in S3 CORS allowed origins

**Fix:**
1. Add your domain to `deployment/create_unified_s3_bucket.py` line 273
2. Redeploy CORS: `python3 deployment/create_unified_s3_bucket.py --update-cors-only`

### Rate Limit False Positives

**Cause:** Rate limit too aggressive for legitimate users

**Fix:**
```python
# In viewer_data.py, increase limits:
check_rate_limit(email, 'getViewerData', max_requests=20, window_minutes=1)
```

---

## Performance Monitoring

After deployment, monitor these metrics:

### Week 1 Metrics
```bash
# Check average Lambda duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=perplexity-validator-interface \
  --statistics Average \
  --start-time $(date -u -d '1 week ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600

# Check error rate
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=perplexity-validator-interface \
  --statistics Sum \
  --start-time $(date -u -d '1 week ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600
```

**Expected Results:**
- Average duration: <100ms (acceptable increase)
- Error rate: <1% (minimal impact)
- Security violations logged: Various (indicates working)

---

## Support

**Issues:** Create GitHub issue with logs
**Security Concerns:** Email security@yourdomain.com
**Documentation:** See SECURITY_FIXES_IMPLEMENTED.md

---

**Last Updated:** 2026-02-02
**Version:** 1.0
