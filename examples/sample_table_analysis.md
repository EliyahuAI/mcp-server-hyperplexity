# Example: Efficient Column Config Generation

## Sample Table: Pharmaceutical Products

| Product_Name | Company | Target | Status | Launch_Date | Revenue_M |
|--------------|---------|--------|--------|-------------|-----------|
| Drug-ABC     | Pfizer  | Cancer | Phase3 | 2025-06-01  | 150.5     |
| Compound-XYZ | Novartis| Heart  | Phase2 | 2026-12-15  | 89.2      |

## Efficient AI Analysis Process

**ANALYST**: I've analyzed your pharmaceutical products table. Here's my assessment:

### MY ANALYSIS:

**Table Purpose**: Tracking pharmaceutical products in development pipeline
**Domain**: Pharmaceutical/biotech industry  
**Preferred Sources**: Company press releases, clinicaltrials.gov, FDA databases, SEC filings

**Unique Identifiers**: Product_Name + Company (composite key for uniqueness)

**Search Groups**:
- Group 0: Product_Name, Company (ID fields, not validated)
- Group 1: Target (medical condition info, often found with product announcements)
- Group 2: Status, Launch_Date (development timeline info found together)
- Ungrouped: Revenue_M (financial data from separate sources)

**Column Classifications**:
| Column | Importance | Format | Notes | Examples (from data) |
|--------|------------|--------|-------|---------------------|
| Product_Name | ID | String | Official drug codes/names | "Drug-ABC", "Compound-XYZ" |
| Company | ID | String | Full company names | "Pfizer", "Novartis" |
| Target | CRITICAL | String | Medical condition targets | "Cancer", "Heart" |
| Status | CRITICAL | String | Clinical development phases | "Phase3", "Phase2" |
| Launch_Date | HIGH | Date | YYYY-MM-DD format | "2025-06-01", "2026-12-15" |
| Revenue_M | MEDIUM | Number | Millions USD | "150.5", "89.2" |

### CLARIFYING QUESTIONS:
1. Is my understanding correct that this is for investment portfolio tracking?
2. For the Status column, should this be: A) Standard clinical phases only or B) Include regulatory milestones like "FDA Review"?
3. For preferred sources, should I prioritize: A) Company press releases for announcements or B) Regulatory databases for official status?

**USER RESPONSES**:
1. Yes, investment tracking for portfolio decisions
2. A) Standard clinical phases only
3. B) Regulatory databases for official status

## Generated Simplified Config

```json
{
  "general_notes": "This table tracks pharmaceutical products in our investment portfolio for decision-making. Focus on accurate development status and timeline information. Prioritize regulatory databases (FDA, clinicaltrials.gov) for official status, with company press releases for announcements. Use standard clinical phases only for status tracking.",
  "default_model": "sonar-pro",
  "validation_targets": [
    {
      "column": "Product_Name",
      "description": "Official drug name or compound identifier",
      "importance": "ID",
      "format": "String",
      "notes": "Use official nomenclature from company press releases",
      "examples": ["Drug-ABC", "Compound-XYZ"],
      "search_group": 0
    },
    {
      "column": "Company",
      "description": "Pharmaceutical company developing the product",
      "importance": "ID",
      "format": "String",
      "notes": "Use full company name, include parent company if acquired",
      "examples": ["Pfizer", "Novartis"],
      "search_group": 0
    },
    {
      "column": "Target",
      "description": "Medical condition or disease target",
      "importance": "CRITICAL",
      "format": "String",
      "notes": "Use specific medical terminology",
      "examples": ["Cancer", "Heart"],
      "search_group": 1
    },
    {
      "column": "Status",
      "description": "Current development phase",
      "importance": "CRITICAL",
      "format": "String",
      "notes": "Use standard clinical trial phases only (Phase1, Phase2, Phase3, Approved, Discontinued)",
      "examples": ["Phase3", "Phase2"],
      "search_group": 2
    },
    {
      "column": "Launch_Date",
      "description": "Expected or actual market launch date",
      "importance": "HIGH",
      "format": "Date",
      "notes": "Use YYYY-MM-DD format, estimate if not announced",
      "examples": ["2025-06-01", "2026-12-15"],
      "search_group": 2
    },
    {
      "column": "Revenue_M",
      "description": "Annual revenue in millions USD",
      "importance": "MEDIUM",
      "format": "Number",
      "notes": "Current or projected annual revenue",
      "examples": ["150.5", "89.2"]
    }
  ]
}
```

## Efficiency Demonstrated

✅ **Intelligent analysis**: Inferred purpose, domain, and groupings from data
✅ **Real examples**: Used actual values from the table
✅ **Logical assumptions**: Made smart guesses about formats and importance
✅ **A/B clarifications**: Clear choice format for ambiguous decisions
✅ **Fast turnaround**: From table to config in one interaction
✅ **Clear reasoning**: Showed analysis before asking questions

## Key Efficiency Features

- **Auto-detected formats**: Date format from sample values
- **Inferred groupings**: Logical relationships between columns
- **Smart importance**: ID fields auto-identified, criticality inferred
- **Domain knowledge**: Pharmaceutical-specific sources suggested
- **Real examples**: Extracted from actual table data
- **A/B questions**: Clear choices instead of open-ended questions
- **Default model**: Always sonar-pro, no model selection needed 