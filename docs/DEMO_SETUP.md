# Demo System Setup Guide

This guide explains how to set up the demo system for new users in the Hyperplexity Validator.

## Overview

The demo system allows new users to try pre-configured example tables without needing to upload their own data. When a user with no prior validation history logs in, they'll see an option to "Try a Demo Table" alongside the regular upload option.

## Demo Folder Structure

Demos are stored in the S3 bucket at `s3://hyperplexity-storage/demos/` with the following structure:

```
s3://hyperplexity-storage/demos/
├── financial_portfolio/
│   ├── portfolio_data.xlsx
│   ├── portfolio_config.json
│   └── description.md
├── sales_leads/
│   ├── leads_data.csv
│   ├── leads_config.json
│   └── description.md
└── marketing_campaigns/
    ├── campaigns.xlsx
    ├── campaigns_config.json
    └── description.md
```

### Required Files per Demo

Each demo folder must contain exactly these three files:

1. **Data File**: Excel (.xlsx, .xls) or CSV (.csv) file containing the sample data
2. **Config File**: JSON file with the validation configuration
3. **Description File**: Markdown (.md) file with the demo name and description

### Description File Format

The `description.md` file should follow this format:

```markdown
# Demo Display Name

Brief description of what this demo validates and what users can learn from it.

This second paragraph will be ignored.
Only the first paragraph after the heading is used.
```

**Important**:
- The first heading (`# ...`) becomes the display name in the UI
- Only the **first paragraph** after the heading is used as the description
- Any subsequent paragraphs (after a blank line) are ignored

## Setting Up Demos

### 1. Prepare Demo Files Locally

Create a local `demos/` folder with your demo subfolders:

```
demos/
├── financial_portfolio/
│   ├── portfolio_data.xlsx
│   ├── portfolio_config.json
│   └── description.md
└── sales_leads/
    ├── leads_data.csv
    ├── leads_config.json
    └── description.md
```

### 2. Validate and Upload

Use the provided upload script to validate and upload your demos:

```bash
# Validate demos (dry run)
python deployment/upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --dry-run

# Upload demos to production
python deployment/upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --upload

# Upload to development environment
python deployment/upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage-dev --upload
```

### 3. Verify Upload

The script will:
- Validate that each demo has all required files
- Check that data files can be read
- Validate that config files are valid JSON
- Parse description files for display names
- Upload all files to the correct S3 locations

## Demo Selection Flow

1. **New User Detection**: When a user validates their email, the system checks if they have any completed validation runs
2. **Choice Screen**: New users see a choice between "Try a Demo Table" and "Upload Your Own Table"
3. **Demo List**: If they choose demos, available demos are loaded from S3 and displayed as vertical buttons
4. **Demo Loading**: When selected, the demo files are copied to the user's session folder
5. **Preview**: The system proceeds directly to the preview step with the demo data and configuration

## Files Modified

### Backend Changes
- `src/shared/dynamodb_schemas.py`: Added `is_new_user()` function
- `src/lambdas/interface/actions/email_validation.py`: Added new user detection
- `src/lambdas/interface/actions/demo_management.py`: New demo management API
- `src/lambdas/interface/handlers/http_handler.py`: Added demo action routing

### Frontend Changes
- `frontend/perplexity_validator_interface2.html`:
  - Added demo selection UI
  - Modified email validation flow for new users
  - Added demo loading and selection functions

### Deployment
- `deployment/upload_demos.py`: New script for demo management

## Testing

To test the demo system:

1. Use an email address that has never completed a validation
2. Go through email validation
3. You should see the choice between demo and upload
4. Select "Try a Demo Table" to see available demos
5. Select a demo to load it and proceed to preview

## Troubleshooting

### No Demos Appear
- Check that demos exist in S3 at `demos/` prefix
- Verify each demo folder has all three required files
- Check browser console for API errors

### Demo Loading Fails
- Verify S3 permissions allow copying within the bucket
- Check that session ID is properly initialized
- Confirm config JSON is valid

### Always Shows Upload (No Demo Option)
- Verify new user detection is working
- Check if user actually has validation history
- Ensure `is_new_user` flag is being returned from email validation

## Environment-Specific Buckets

- **Production**: `hyperplexity-storage`
- **Development**: `hyperplexity-storage-dev`
- **Staging**: `hyperplexity-storage-staging`
- **Testing**: `hyperplexity-storage-test`

Make sure to upload demos to the appropriate bucket for each environment.