# Troubleshooting Perplexity Validator Interface

## Common Issues

### 1. "Network error" when submitting email

This is typically caused by one of these issues:

#### A. Running from file:// protocol
**Problem**: Opening the HTML file directly in your browser (file://) triggers CORS restrictions.

**Solutions**:
1. **Use a local web server** (recommended for testing):
   ```bash
   # Python 3
   python -m http.server 8000
   # Then visit: http://localhost:8000/perplexity_validator_interface.html
   
   # Python 2
   python -m SimpleHTTPServer 8000
   
   # Node.js (if you have http-server installed)
   npx http-server -p 8000
   ```

2. **Upload to your web server**:
   - Upload the HTML file to your Squarespace site or any web server
   - Access it via http:// or https://

#### B. Incorrect API endpoint URL
**Problem**: The API_BASE URL in the code doesn't match your deployed API.

**Solution**:
1. Find your actual API endpoint:
   ```bash
   cd deployment
   python create_interface_package.py --deploy
   ```
   
2. Look for output like:
   ```
   === API Gateway Endpoints ===
   Main endpoint: https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/prod/validate
   ```

3. Update the API_BASE in `perplexity_validator_interface.html`:
   ```javascript
   const API_BASE = 'https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/prod';
   ```

#### C. API Gateway not deployed
**Problem**: The API Gateway hasn't been deployed yet.

**Solution**:
```bash
cd deployment
python create_interface_package.py --deploy --setup-db
```

This will:
- Deploy the Lambda function
- Set up API Gateway with all endpoints
- Create DynamoDB tables for email validation
- Output your API endpoints

### 2. CORS errors in browser console

**Problem**: Cross-Origin Resource Sharing (CORS) is blocking requests.

**Solutions**:
1. Ensure you're not running from file://
2. **IMPORTANT**: The interface now uses the `/validate` endpoint with action parameters instead of dedicated endpoints like `/check-or-send`. This fixes CORS issues with non-proxy integrations.
3. If you have an older version, update to the latest `perplexity_validator_interface.html`
4. The working endpoint format is:
   ```javascript
   POST https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/prod/validate
   {
     "action": "checkOrSendValidation",
     "email": "user@example.com"
   }
   ```

### 3. "Email already validated" but can't proceed

**Problem**: Email is cached but validation state is out of sync.

**Solution**:
Clear your browser's localStorage:
```javascript
// In browser console (F12)
localStorage.removeItem('validatedEmail');
// Then refresh the page
```

### 4. Finding your API details in AWS Console

1. **API Gateway endpoint**:
   - AWS Console > API Gateway
   - Click on "perplexity-validator-api"
   - Click "Stages" > "prod"
   - Copy the "Invoke URL"

2. **Lambda function logs**:
   - AWS Console > Lambda
   - Click on "perplexity-validator-interface"
   - Click "Monitor" tab > "View logs in CloudWatch"

3. **DynamoDB tables**:
   - AWS Console > DynamoDB
   - Look for tables:
     - perplexity-validator-user-validation
     - perplexity-validator-user-tracking

### 5. Debug mode

The interface now includes enhanced debugging. When you get a network error:
1. Check the browser console (F12) for detailed error information
2. Look at the debug information box that appears below the error
3. Note the "Current Protocol" and "API Endpoint" values

### Quick Checklist

- [ ] Not running from file:// protocol
- [ ] API_BASE URL matches your deployed API
- [ ] API Gateway is deployed (`--deploy` flag used)
- [ ] DynamoDB tables exist (`--setup-db` flag used)
- [ ] Using a modern browser (Chrome, Firefox, Safari, Edge)
- [ ] No browser extensions blocking requests

### Getting Help

If you're still having issues:
1. Check CloudWatch logs for your Lambda function
2. Test the API directly with curl:
   ```bash
   curl -X POST https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/prod/check-or-send \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com"}'
   ```
3. Verify all AWS resources are in the same region (default: us-east-1) 