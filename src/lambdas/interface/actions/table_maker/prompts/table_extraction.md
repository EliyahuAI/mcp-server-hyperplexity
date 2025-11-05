# Table Extraction Task

═══════════════════════════════════════════════════════════════
## 🔍 YOUR EXTRACTION TASK
═══════════════════════════════════════════════════════════════

Extract data from: **{{TABLE_URL}}**

**Table Name:** {{TABLE_NAME}}

**Expected Structure:**
- Estimated rows: {{ESTIMATED_ROWS}}
- Expected columns: {{EXPECTED_COLUMNS}}

{{TARGET_ROWS_INSTRUCTION}}

**Search Configuration:** Your search is configured to prioritize the domain of this URL.

**CRITICAL - Extract from ANY format:**
- HTML table → Extract rows directly
- Article text → Build structured rows from prose
- List format → Parse into structured rows
- Multiple paragraphs → Extract entities and their attributes
- Don't require pre-existing table structure - BUILD the table from available information
- Never fabricate - only use information present at the URL

═══════════════════════════════════════════════════════════════
## 📋 EXTRACTION REQUIREMENTS
═══════════════════════════════════════════════════════════════

**CRITICAL:**
- Extract information from whatever format is available (table, article, list, paragraphs)
- Build structured rows from the source content
- Use expected column names (or actual column names if structured table exists)
- Only include information actually present at the URL (never fabricate)
- If pagination detected, note this in extraction_notes
- Return empty array ONLY if URL is inaccessible or contains no relevant information

**Quality Standards:**
- Maintain data accuracy - only use information from the source
- Build complete rows with all available columns
- If some columns have no data for certain rows, leave those fields empty
- Note any issues (missing data, incomplete information, access restrictions)

**Example - Extracting from Article Text:**
If article says "Marc McGovern won with 2,372 votes. He's an incumbent focused on housing..."
→ Build row: {"Winner Name": "Marc McGovern", "Incumbent Status": "Yes", "Campaign Platform": "Housing policy", "Vote Count": "2,372"}

═══════════════════════════════════════════════════════════════
## 📤 OUTPUT FORMAT
═══════════════════════════════════════════════════════════════

Return JSON matching this structure:

```json
{
  "table_name": "{{TABLE_NAME}}",
  "source_url": "{{TABLE_URL}}",
  "extraction_complete": true,
  "rows_extracted": 50,
  "pagination_detected": false,
  "extraction_notes": "Successfully extracted complete table with all columns",
  "rows": [
    {
      "Column Name 1": "value for row 1",
      "Column Name 2": "value for row 1",
      "Column Name 3": "value for row 1"
    },
    {
      "Column Name 1": "value for row 2",
      "Column Name 2": "value for row 2",
      "Column Name 3": "value for row 2"
    }
  ]
}
```

**Field Descriptions:**
- `table_name`: Name of the table (use provided name)
- `source_url`: URL of the source (use provided URL)
- `extraction_complete`: true if all rows extracted, false if partial/paginated
- `rows_extracted`: Exact count of rows in the array
- `pagination_detected`: true if table has pagination and more rows might exist
- `extraction_notes`: Notes about extraction quality, issues, or special circumstances
- `rows`: Array of objects, each object represents one row with column names as keys

**Requirements:**
- ✅ Use actual column names from the source table
- ✅ Include ALL rows accessible at the URL
- ✅ Set `extraction_complete: false` if you detect pagination or can't access all rows
- ✅ If table not found or inaccessible, return `rows: []` and explain in `extraction_notes`
- ✅ Return valid JSON matching the schema above

**Return your extraction as valid JSON.**
