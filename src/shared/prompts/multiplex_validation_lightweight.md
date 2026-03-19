# Table Entry Validation (Lightweight)

You are quickly validating field values for a single row in a research table.

═══════════════════════════════════════════════════════════════
## 🎯 FOCUSED TASK
═══════════════════════════════════════════════════════════════

{search_instruction}

{research_questions}

═══════════════════════════════════════════════════════════════

---

═══════════════════════════════════════════════════════════════
## 📝 FIELD DETAILS
═══════════════════════════════════════════════════════════════

{fields_to_validate}

---

═══════════════════════════════════════════════════════════════
## 📤 RESPONSE FORMAT
═══════════════════════════════════════════════════════════════

Return a JSON array where each item is a cell array with 6 elements:

```
[column, answer, confidence, original_confidence, consistent, explanation]
```

- **column**: Exact field name from FIELD DETAILS
- **answer**: The validated value (string or null for blank)
- **confidence**: Always "M" (MEDIUM)
- **original_confidence**: Always "M" (MEDIUM)
- **consistent**: null
- **explanation**: Brief reason

**Example:**
```json
[
  ["Revenue", "$158.9B", "M", "M", null, "Confirmed via search"],
  ["CEO", "Andy Jassy", "M", "M", null, "Confirmed via search"],
  ["Founded", null, "M", "M", null, "No data found"]
]
```

- **Use exact column names** from FIELD DETAILS
- **Valid JSON required**: The response MUST be valid JSON array format

---
