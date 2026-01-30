# Demo System Setup Guide

This guide explains how to set up demo systems for the Hyperplexity Validator.

## Overview

There are two types of demos:

1. **Onboarding Demos** - Allow new users to try pre-configured example tables through the full validation flow
2. **Interactive Table Demos** - Pre-built tables displayed in the public viewer (no validation needed)

---

## 1. Onboarding Demos

These demos allow new users to try pre-configured example tables without needing to upload their own data. When a user with no prior validation history logs in, they'll see an option to "Try a Demo Table" alongside the regular upload option.

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

---

## 2. Interactive Table Demos

Interactive table demos are pre-built tables that can be displayed in the public viewer without going through the validation pipeline. These are useful for showcasing example tables or competitive analysis data.

### Interactive Tables Folder Structure

Interactive tables are stored at `s3://{bucket}/demos/interactive_tables/` with the following structure:

```
s3://hyperplexity-storage/demos/interactive_tables/
├── ai_research_tools/
│   ├── table_metadata.json    (required)
│   └── info.json              (optional)
├── competitive_analysis/
│   └── table_metadata.json
└── market_comparison/
    ├── table_metadata.json
    └── info.json
```

### Required Files per Interactive Table

Each interactive table folder must contain:

1. **table_metadata.json** (required): The table data in the InteractiveTable format with:
   - `rows`: Array of row data
   - `columns`: Array of column definitions
   - `table_name`: Display name (optional)
   - `general_notes`: Notes shown above the table (optional)

2. **info.json** (optional): Additional metadata:
   ```json
   {
     "display_name": "AI Research Tools Comparison"
   }
   ```

### Setting Up Interactive Tables

#### 1. Prepare Table Files Locally

Create a local `demos/interactive_tables/` folder:

```
demos/interactive_tables/
├── ai_research_tools/
│   ├── table_metadata.json
│   └── info.json
└── competitive_analysis/
    └── table_metadata.json
```

#### 2. Validate and Upload

Use the upload script with the `--interactive-tables` flag:

```bash
# Validate interactive tables (dry run)
python deployment/upload_demos.py --interactive-tables ./demos/interactive_tables --bucket hyperplexity-storage --dry-run

# Upload interactive tables to production
python deployment/upload_demos.py --interactive-tables ./demos/interactive_tables --bucket hyperplexity-storage --upload

# Upload to development environment
python deployment/upload_demos.py --interactive-tables ./demos/interactive_tables --bucket hyperplexity-storage-dev --upload

# Upload both onboarding demos and interactive tables at once
python deployment/upload_demos.py --demos-folder ./demos --interactive-tables ./demos/interactive_tables --bucket hyperplexity-storage --upload
```

### Accessing Interactive Tables

Interactive tables are accessed via the `getDemoData` API action:

```javascript
// Frontend call
const response = await apiCall('getDemoData', { table_name: 'ai_research_tools' });
// Returns: { table_metadata, clean_table_name, is_demo: true }
```

Or via URL: `https://hyperplexity.ai?mode=viewer&demo=ai_research_tools`

### Interactive Table Troubleshooting

#### Table Not Found
- Verify the folder exists at `demos/interactive_tables/{table_name}/`
- Check that `table_metadata.json` exists in the folder
- Ensure table name uses only letters, numbers, hyphens, and underscores

#### Table Renders Empty
- Verify `table_metadata.json` has valid `rows` and `columns` arrays
- Check browser console for JavaScript errors
- Validate JSON syntax with `python -m json.tool table_metadata.json`

#### Display Name Not Showing
- Add `info.json` with a `display_name` field
- Or set `table_name` in the `table_metadata.json` file