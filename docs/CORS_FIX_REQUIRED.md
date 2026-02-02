# CORS Configuration Fix Required for Table Maker API

**Issue Discovered:** 2026-02-02
**Severity:** HIGH (Breaks table maker in local development)
**Status:** Requires Action

---

## Problem

**CORS Error When Using Table Maker:**
```
Access to fetch at 'https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev/validate'
from origin 'http://localhost:8000' has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present on the requested resource.
```

**Error Details:**
- **Endpoint:** `https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev/validate`
- **Origin:** `http://localhost:8000`
- **Issue:** API Gateway not configured for CORS
- **HTTP Status:** 502 Bad Gateway (after CORS preflight failure)

---

## Root Cause

The project has **TWO different API Gateway instances:**

1. **Main API (validator-interface):**
   - URL: `https://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod`
   - Used for: Email validation, viewer data, account balance
   - CORS Status: ✅ Configured (from deployment scripts)

2. **Table Maker API (dev environment):**
   - URL: `https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev`
   - Used for: Table maker, config generation, validation
   - CORS Status: ❌ **NOT CONFIGURED**

**Why Two APIs:**
- Configured in `frontend/src/js/00-config.js` line 15
- Dev environment uses separate API Gateway
- Likely for testing/isolation purposes

---

## Fix: Configure CORS on Table Maker API Gateway

### Option 1: Via AWS Console (Quick Fix)

1. **Navigate to API Gateway:**
   ```
   https://console.aws.amazon.com/apigateway/home?region=us-east-1#/apis/wqamcddvub
   ```

2. **Enable CORS:**
   - Select the `/validate` resource
   - Click "Actions" → "Enable CORS"
   - Configure:
     ```
     Access-Control-Allow-Origin: http://localhost:8000, http://localhost:3000, https://eliyahu.ai
     Access-Control-Allow-Headers: Content-Type, X-Session-Token, Authorization
     Access-Control-Allow-Methods: GET, POST, OPTIONS
     ```

3. **Deploy API:**
   - Click "Actions" → "Deploy API"
   - Stage: `dev`
   - Deployment description: "Add CORS headers for local development"

4. **Test:**
   ```bash
   curl -X OPTIONS https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev/validate \
     -H "Origin: http://localhost:8000" \
     -H "Access-Control-Request-Method: POST" \
     -v

   # Should return:
   # Access-Control-Allow-Origin: http://localhost:8000
   ```

### Option 2: Via Deployment Script (Recommended)

**Check if deployment script exists:**
```bash
# Look for API Gateway deployment script
ls deployment/create_*_api_gateway.py
ls deployment/setup_api_gateway.py
```

**If script exists, add CORS configuration:**
```python
# In the deployment script
api_gateway = boto3.client('apigateway', region_name='us-east-1')

# Configure CORS for /validate resource
api_gateway.update_integration_response(
    restApiId='wqamcddvub',
    resourceId='resource_id',  # Get from API Gateway
    httpMethod='POST',
    statusCode='200',
    responseParameters={
        'method.response.header.Access-Control-Allow-Origin': "'http://localhost:8000,http://localhost:3000,https://eliyahu.ai'",
        'method.response.header.Access-Control-Allow-Headers': "'Content-Type,X-Session-Token,Authorization'",
        'method.response.header.Access-Control-Allow-Methods': "'GET,POST,OPTIONS'"
    }
)

# Add OPTIONS method for preflight
api_gateway.put_method(
    restApiId='wqamcddvub',
    resourceId='resource_id',
    httpMethod='OPTIONS',
    authorizationType='NONE'
)

# Add OPTIONS integration
api_gateway.put_integration(
    restApiId='wqamcddvub',
    resourceId='resource_id',
    httpMethod='OPTIONS',
    type='MOCK',
    requestTemplates={
        'application/json': '{"statusCode": 200}'
    }
)
```

### Option 3: Terraform/CloudFormation (If Using IaC)

**If using Terraform:**
```hcl
resource "aws_api_gateway_method" "options" {
  rest_api_id = "wqamcddvub"
  resource_id = aws_api_gateway_resource.validate.id
  http_method = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options" {
  rest_api_id = "wqamcddvub"
  resource_id = aws_api_gateway_resource.validate.id
  http_method = aws_api_gateway_method.options.http_method
  type = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options_200" {
  rest_api_id = "wqamcddvub"
  resource_id = aws_api_gateway_resource.validate.id
  http_method = aws_api_gateway_method.options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin" = true
  }
}

resource "aws_api_gateway_integration_response" "options_200" {
  rest_api_id = "wqamcddvub"
  resource_id = aws_api_gateway_resource.validate.id
  http_method = aws_api_gateway_method.options.http_method
  status_code = aws_api_gateway_method_response.options_200.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Session-Token,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin" = "'http://localhost:8000,http://localhost:3000,https://eliyahu.ai'"
  }
}
```

---

## Temporary Workaround: Use Production API

**While waiting for CORS fix, use production API:**

1. **Edit `frontend/src/js/00-config.js`:**
   ```javascript
   // Change line 15:
   // OLD:
   apiBase: 'https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev',

   // NEW (temporary):
   apiBase: 'https://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod',
   ```

2. **Rebuild frontend:**
   ```bash
   python3 frontend/build.py
   ```

3. **Test:**
   ```bash
   ./start-local.sh
   # Table maker should now work!
   ```

**WARNING:** This makes dev environment use production API. Not ideal, but works for testing.

---

## Why Demo Mode Worked But Table Maker Didn't

**Demo Mode:**
- Uses main API: `xt6790qk9f.../prod` ✅ CORS configured
- Action: `getDemoData`
- Works from localhost ✓

**Table Maker:**
- Uses dev API: `wqamcddvub.../dev` ❌ CORS not configured
- Action: `processExcel`, `generateConfig`, etc.
- Fails from localhost ✗
- **But works after demo** because...
  - Demo initializes the global state properly
  - Sets up API base correctly
  - Coincidence, not a fix

---

## Verification Steps

### After CORS Fix:

1. **Test CORS preflight:**
   ```bash
   curl -X OPTIONS https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev/validate \
     -H "Origin: http://localhost:8000" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type,X-Session-Token" \
     -v
   ```

   **Expected Response Headers:**
   ```
   HTTP/1.1 200 OK
   Access-Control-Allow-Origin: http://localhost:8000
   Access-Control-Allow-Headers: Content-Type,X-Session-Token,Authorization
   Access-Control-Allow-Methods: GET,POST,OPTIONS
   ```

2. **Test table maker:**
   ```bash
   ./start-local.sh
   # Navigate to table maker
   # Upload file
   # Should work without CORS error!
   ```

3. **Check browser console:**
   ```
   No CORS errors should appear ✓
   ```

---

## Production Deployment Checklist

Before production, ensure CORS is configured on **ALL** API Gateways:

- [ ] Main API (`xt6790qk9f.../prod`) - CORS configured ✅
- [ ] Dev API (`wqamcddvub.../dev`) - **CORS NEEDED** ⚠️
- [ ] Any other API Gateways - Check and configure

**Remove localhost from production:**
```javascript
// Production CORS (API Gateway)
Access-Control-Allow-Origin: https://eliyahu.ai, https://www.eliyahu.ai
// DO NOT include localhost in production!
```

---

## Related Issues

### Issue: Signed-In Badge Not Showing

**Status:** ✅ FIXED

**Fix:**
- Moved badge initialization from `DOMContentLoaded` event to `99-init.js`
- Badge now initializes properly when email + token are present
- Should display on next page load

---

## Summary

**Required Actions:**

1. **Immediate:** Configure CORS on table maker API Gateway (`wqamcddvub.../dev`)
2. **Temporary Workaround:** Use production API in dev config
3. **Already Fixed:** Signed-in badge initialization
4. **Testing:** Use `./start-local.sh` and verify table maker works

**Priority:** HIGH - Blocks local table maker testing

**Estimated Time:** 10 minutes (AWS Console) or 30 minutes (deployment script)

---

**Document Version:** 1.0
**Last Updated:** 2026-02-02
