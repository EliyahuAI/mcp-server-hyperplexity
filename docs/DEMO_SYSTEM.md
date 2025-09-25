# Demo System Documentation

## Overview

The demo system provides new users with pre-configured example tables to learn how the validator works without needing their own data. New users (those who have never completed a validation) are automatically detected and offered demo options alongside the regular file upload.

## User Experience Flow

1. **Email Validation** → System detects new user status
2. **Welcome Screen** → New users see "Try a Demo Table" vs "Upload Your Own Table"
3. **Demo Selection** → Vertical buttons display available demos with descriptions
4. **Auto-Load** → Selected demo data and configuration load into user session
5. **Preview** → System proceeds directly to validation preview with demo data

## Technical Architecture

### New User Detection
- **Function**: `is_new_user(email)` in `dynamodb_schemas.py`
- **Logic**: Scans `perplexity-validator-runs` table for completed runs by email
- **Response**: Added `is_new_user` flag to email validation API

### Demo Storage Structure
```
s3://hyperplexity-storage/demos/
├── demo_name_1/
│   ├── data_file.xlsx          # Sample data
│   ├── config_file.json        # Validation configuration
│   └── description.md          # Display name & description
└── demo_name_2/
    ├── data_file.csv
    ├── config_file.json
    └── description.md
```

### API Endpoints
- **`listDemos`** → Returns available demos with metadata
- **`selectDemo`** → Copies demo files to user session folder

### Frontend Components
- **`createUploadOrDemoCard()`** → Welcome screen for new users
- **`createSelectDemoCard()`** → Demo selection interface
- **`selectDemo()`** → Demo loading and session setup

## Demo File Requirements

### Data File
- **Formats**: `.xlsx`, `.xls`, `.csv`
- **Content**: Sample data representative of use case
- **Size**: Keep reasonable for quick loading

### Configuration File
- **Format**: Valid JSON with validation configuration
- **Required**: Must contain `validation_targets` array
- **Content**: Pre-configured validation rules matching data

### Description File
- **Format**: Markdown with specific structure:
```markdown
# Display Name for Demo

Brief description explaining what this demo validates and what users learn.

Can include:
- Data type overview
- Validation rules applied
- Expected insights
```

## Demo Management

### Upload Script Usage
```bash
# Validate local demos (dry run)
python deployment/upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --dry-run

# Upload to production
python deployment/upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --upload

# Upload to development
python deployment/upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage-dev --upload
```

### Script Features
- **Validation**: Checks file types, JSON validity, data readability
- **Metadata Parsing**: Extracts display names from markdown
- **Error Reporting**: Detailed validation errors and warnings
- **Environment Support**: Different buckets per environment

## Testing the Demo System

### Option 1: Use Fresh Email
- Use an email that has never completed a validation
- Go through normal email validation flow
- Should see demo vs upload choice

### Option 2: URL Parameters (Quick Testing)
Add testing parameters to the URL:

**Force New User**: `?force_new_user=true`
**Force Returning User**: `?force_returning_user=true`

Example:
```
https://your-validator-url.com/?force_new_user=true
```

### Option 3: Browser Console Commands
Open browser console and use testing utilities:

```javascript
// Check current new user status
testingUtils.checkNewUserStatus();

// Force new user mode
testingUtils.forceNewUser();

// Force returning user mode
testingUtils.forceReturningUser();

// Show demo selection card directly
testingUtils.showDemoCard();

// Show upload or demo choice card
testingUtils.showUploadOrDemoCard();

// Run quick test sequence
testingUtils.testNewUserFlow();

// Clear user's validation history (development only)
await testingUtils.clearUserHistory('user@example.com');
```

### Option 4: API Testing Endpoint (Development Only)
For development environments, clear user history via API:

```javascript
// Clear current user's history
fetch('https://api-url/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        action: 'clearUserHistoryForTesting',
        email: 'user@example.com'
    })
});
```

**Note**: Testing endpoint is disabled in production environments.

## Environment Configuration

### Production
- **Bucket**: `hyperplexity-storage`
- **API**: `https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod`

### Development
- **Bucket**: `hyperplexity-storage-dev`
- **API**: Development endpoint

### Testing Override
Add to frontend for testing:
```javascript
// Force demo mode for testing
globalState.isNewUser = true; // In browser console
```

## Demo Creation Workflow

1. **Design Demo**
   - Choose representative data set
   - Define validation rules that showcase features
   - Write clear description

2. **Prepare Files**
   - Create data file (Excel/CSV)
   - Generate matching config JSON
   - Write description.md with proper format

3. **Validate Locally**
   ```bash
   python deployment/upload_demos.py --demos-folder ./local_demos --bucket test --dry-run
   ```

4. **Upload to Environment**
   ```bash
   python deployment/upload_demos.py --demos-folder ./local_demos --bucket hyperplexity-storage-dev --upload
   ```

5. **Test Demo**
   - Use fresh email or testing override
   - Verify demo appears in list
   - Test demo loading and validation flow

## Troubleshooting

### Demo Not Appearing
- ✅ Check S3 bucket has `demos/folder_name/` structure
- ✅ Verify all three files present (data, config, description)
- ✅ Confirm API endpoint `listDemos` returns demo
- ✅ Check browser console for API errors

### Demo Loading Fails
- ✅ Verify S3 copy permissions within bucket
- ✅ Check session ID initialization
- ✅ Validate JSON config file format
- ✅ Confirm file sizes are reasonable

### Always Shows Upload Option
- ✅ Check new user detection logic
- ✅ Verify user actually has no completion history
- ✅ Test with fresh email address
- ✅ Use testing override methods above

### Upload Script Errors
- ✅ Check file permissions and paths
- ✅ Verify AWS credentials configured
- ✅ Confirm bucket exists and accessible
- ✅ Validate demo folder structure locally

## Security & Performance

### Security
- Demo files are public within S3 bucket structure
- No sensitive data should be included in demos
- User session isolation maintained during demo copy

### Performance
- Demo list cached by browser
- Demo files copied, not linked (isolation)
- Reasonable file sizes recommended (< 1MB each)

### Monitoring
- Track demo usage via existing validation metrics
- Monitor S3 costs for demo storage/transfer
- Log demo selection events for analytics

This system provides a seamless onboarding experience for new users while maintaining full functionality for existing users.