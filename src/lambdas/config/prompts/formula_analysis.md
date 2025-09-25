# Excel Formula Analysis

## FORMULA ANALYSIS - CRITICAL FOR CONFIG GENERATION
**⚠️ IMPORTANT: This Excel file contains {{FORMULA_COUNT}} formulas that create dependencies between columns.**

**Formula Dependencies Found:**

{{FORMULA_DEPENDENCIES_DETAIL}}

**FORMULA-AWARE CONFIG REQUIREMENTS:**

1. **Calculated Columns** ({{CALCULATED_COLUMNS_LIST}}):
   - Mark as **CRITICAL** importance - these should be validated by AI using the underlying formula logic
   - Use Claude AI validation (anthropic_max_web_searches: 0) since this is pure calculation, not web research
   - Include detailed formula information in field notes explaining the calculation logic
   - Provide clear examples showing the expected calculation pattern
   - **DO NOT use calculated columns as ID fields** - they are derived data, not unique identifiers

2. **Source Columns** ({{SOURCE_COLUMNS_LIST}}):
   - Mark as **CRITICAL** importance with strict format validation to prevent formula breakage
   - These provide the input data for calculations and must be accurate
   - Add notes explaining their role in calculations with explicit examples
   - Ensure data types are preserved (numbers as numbers, dates as dates)
   - **Source columns can be ID fields** if they uniquely identify rows

3. **ID Field Selection**:
   - **NEVER use calculated/formula columns as ID fields**
   - Choose source columns or other non-calculated columns that uniquely identify each row
   - Prefer meaningful identifiers over sequential numbers when available

**Column-Specific Formula Context:**
{{COLUMN_FORMULA_CONTEXT}}