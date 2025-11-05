# Table Extraction Task

═══════════════════════════════════════════════════════════════
## 🔍 YOUR EXTRACTION TASK
═══════════════════════════════════════════════════════════════

Extract rows from the table at: **{{TABLE_URL}}**

**Table Name:** {{TABLE_NAME}}

**Expected Structure:**
- Estimated rows: {{ESTIMATED_ROWS}}
- Expected columns: {{EXPECTED_COLUMNS}}

{{TARGET_ROWS_INSTRUCTION}}

**Search Configuration:** Your search is configured to prioritize the domain of this URL. Access the page and extract the table.

═══════════════════════════════════════════════════════════════
## 📋 EXTRACTION REQUIREMENTS
═══════════════════════════════════════════════════════════════

**CRITICAL:**
- Preserve exact values as they appear in the source
- If the table has pagination/multiple pages, note this in extraction_notes
- If column names differ from expected, use the actual column names from the source
- Return empty array if table is not accessible or doesn't exist
- Follow the row extraction guidance above (extract all or up to target)

**Quality Standards:**
- Maintain data accuracy - copy values exactly as shown
- Preserve all columns present in the table (not just expected ones)
- Note any issues (missing data, formatting problems, access restrictions)

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
