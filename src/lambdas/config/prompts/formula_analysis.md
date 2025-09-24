# Excel Formula Analysis

## FORMULA ANALYSIS - CRITICAL FOR CONFIG GENERATION
**⚠️ IMPORTANT: This Excel file contains {{FORMULA_COUNT}} formulas that create dependencies between columns.**

**Formula Dependencies Found:**

{{FORMULA_DEPENDENCIES_DETAIL}}

**FORMULA-AWARE CONFIG REQUIREMENTS:**

1. **Calculated Columns** ({{CALCULATED_COLUMNS_LIST}}):
   - Use these columns in the search groups with their source info, making it clear that these are derivative
   - Use Claude AI validation (no web search) in a separate calculation search group when the computation is complex
   - Include formula information in field notes

2. **Source Columns** ({{SOURCE_COLUMNS_LIST}}):
   - Require strict format validation to prevent formula breakage
   - Add notes about being used in calculations to the source columns, with explicit examples.
   - Ensure data types are preserved (numbers as numbers, dates as dates)

**Column-Specific Formula Context:**
{{COLUMN_FORMULA_CONTEXT}}