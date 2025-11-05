# Table Extraction Task

═══════════════════════════════════════════════════════════════
## 🔍 YOUR EXTRACTION TASK
═══════════════════════════════════════════════════════════════

**BUILD a structured table from information at:** {{TABLE_URL}}

**Table Name:** {{TABLE_NAME}}

**Target Structure:**
- Estimated entities: {{ESTIMATED_ROWS}}
- Columns to populate: {{EXPECTED_COLUMNS}}

{{TARGET_ROWS_INSTRUCTION}}

**Your Job: BUILD the table from whatever information is available**

**FOCUS ON THIS SPECIFIC PAGE:** {{TABLE_URL}}

Search is configured with low context to focus on this exact page. Do not pull from other pages.

The page may have:
- ✅ Article text mentioning entities → Extract and structure into rows
- ✅ Paragraphs describing entities → Parse into table format
- ✅ Bullet lists → Convert to structured rows
- ✅ HTML table → Extract directly
- ✅ Mixed content → Compile all entity information

**CRITICAL:**
- You are BUILDING a table, not just copying one
- Extract information from prose, articles, lists, any format on THIS PAGE
- Structure the extracted information into rows with expected columns
- Return empty ONLY if: URL inaccessible OR page contains no relevant entities
- "No table found" is NOT acceptable - if page has entity information, build rows from it!
- Search focuses on the specific URL provided, not the whole domain

═══════════════════════════════════════════════════════════════
## 📋 EXTRACTION REQUIREMENTS
═══════════════════════════════════════════════════════════════

**YOUR PRIMARY TASK: Build structured rows from prose/article content**

Most sources won't have HTML tables - you'll build the table from article text, paragraphs, and prose descriptions.

**How to Build Rows:**

1. **Read the page content** - Article text, paragraphs, lists
2. **Find entity mentions** - Look for the entities (candidates, companies, people, etc.)
3. **Extract attributes** - For each entity, find the data points (name, position, details)
4. **Structure into rows** - Build row objects with expected column names as keys
5. **Fill all columns possible** - Include all data you find, leave unknown columns empty

**Example - Election Article:**
```
Article text: "Marc McGovern was the top vote-getter with 2,372 votes. The incumbent
focused his campaign on affordable housing and bike safety, appealing to progressive
voters. Ayah Al-Zubi, a newcomer and democratic socialist, also won a seat..."

Build rows:
[
  {
    "Winner Name": "Marc McGovern",
    "Incumbent Status": "Incumbent",
    "Campaign Platform": "Affordable housing, bike safety",
    "Vote Count": "2,372",
    "Demographic Appeal": "Progressive voters"
  },
  {
    "Winner Name": "Ayah Al-Zubi",
    "Incumbent Status": "Newcomer",
    "Campaign Platform": "Democratic socialist platform",
    "Vote Count": "",  // Not mentioned
    "Demographic Appeal": ""  // Details not in this excerpt
  }
]
```

**Quality Standards:**
- Only use information actually present in the source (never fabricate)
- If some columns have no data, leave those fields empty ("")
- Build as many complete rows as you can find entities for
- "No table found" means "URL inaccessible", NOT "no HTML table visible"

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
