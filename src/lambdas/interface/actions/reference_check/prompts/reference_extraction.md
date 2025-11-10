# Reference Extraction Prompt

## TASK
Extract all numbered references from the References/Bibliography section of the provided text.

## YOUR ROLE
You are a reference parser extracting complete citations from academic or research documents. Your goal is to find the reference section and extract each numbered reference with its full citation text.

## WHAT TO EXTRACT

For each reference, extract:
1. **ref_id**: The reference number (e.g., [1], [2], [3])
2. **full_citation**: The complete citation text including:
   - Author names
   - Publication year
   - Title
   - Source (journal, conference, website, etc.)
   - DOI or URL (if present)

## HOW TO FIND REFERENCES

### Step 1: Locate the Reference Section
Look for sections typically named:
- "References"
- "Bibliography"
- "Works Cited"
- "Sources"
- Usually found at the end of the document

### Step 2: Identify Reference Format

**Numbered Format** (most common):
```
[1] Smith, J. et al. (2023). Understanding AI. Nature, 5(2), 123-145.
[2] Johnson, A. (2024). Machine Learning Basics. arXiv:2401.12345
```

**Alternative Numbered Formats**:
```
1. Smith, J. et al. (2023)...
(1) Smith, J. et al. (2023)...
1) Smith, J. et al. (2023)...
```

**Author-Year Format** (convert to numbered):
```
Smith, J. et al. (2023). Understanding AI...
Johnson, A. (2024). Machine Learning...
```
→ Assign sequential numbers [1], [2], [3] in order

### Step 3: Extract Complete Citations

**What makes a complete citation**:
- ✅ Has author name(s) OR organization
- ✅ Has publication year
- ✅ Has title OR source description
- ✅ Has venue (journal, conference, URL, etc.)

**Examples of complete citations**:
```
[1] Firth, J. et al. (2019). The online brain: how the internet may be changing our cognition. World psychiatry, 18(2):119–129.
[2] Oxford University Press. Brain rot named Oxford Word of the Year 2024. https://corp.oup.com/news/brain-rot-2024/, 2024.
[3] Qi, X., Zeng, Y., et al. (2023). Fine-tuning aligned language models. arXiv preprint arXiv:2310.03693.
```

## QUALITY REQUIREMENTS

Each reference MUST meet these criteria:
1. **Identifiable Author/Source**: Name, organization, or clear source
2. **Year**: Publication year present
3. **Complete**: Not a fragment or partial citation
4. **Readable**: Not garbled text or parsing artifacts

**REJECT these as incomplete**:
- ❌ "prompted with categorized" (fragment)
- ❌ ":853-861, 2015" (missing author)
- ❌ "2023" (just a year)
- ❌ "et al." (no first author)

## HANDLING PYTHON PARSED REFERENCES

{{PARSED_REFERENCES}}

If Python-parsed references are shown above:
- **Review them for completeness**
- **If they're complete**: Use them as-is (just reformat if needed)
- **If they're fragments/incomplete**: Extract references yourself from the reference section
- **If they're missing some**: Add the missing ones

## OUTPUT FORMAT

Return a JSON object with this structure:

```json
{
  "total_references": 28,
  "references": [
    {
      "ref_id": "[1]",
      "full_citation": "Firth, J. et al. (2019). The online brain: how the internet may be changing our cognition. World psychiatry, 18(2):119–129."
    },
    {
      "ref_id": "[2]",
      "full_citation": "Oxford University Press. Brain rot named Oxford Word of the Year 2024. https://corp.oup.com/news/brain-rot-named-oxford-word-of-the-year-2024/, 2024."
    },
    {
      "ref_id": "[3]",
      "full_citation": "Qi, X., Zeng, Y., Xie, T., Chen, P.-Y., Jia, R., Mittal, P., & Henderson, P. (2023). Fine-tuning aligned language models compromises safety, even when users do not intend to! arXiv preprint arXiv:2310.03693."
    }
  ]
}
```

## IMPORTANT NOTES

1. **Sequential numbering**: Assign [1], [2], [3], etc. in the order they appear in the reference section
2. **Preserve formatting**: Keep citation text as-is (don't reformat or abbreviate)
3. **Include all fields**: Author, year, title, source, DOI/URL when present
4. **No interpretation**: Extract exactly what's written, don't add or infer information
5. **Complete only**: Only include references that meet quality criteria above

## EDGE CASES

### Mixed Formats
If some references are numbered and others aren't, assign sequential numbers to all.

### Inline Citations Only
If the document has inline citations like "[1](url)" with no separate reference section, extract what you can find inline.

### No Reference Section
If no reference section exists, return empty array:
```json
{
  "total_references": 0,
  "references": []
}
```

---

## INPUT TEXT

{{SUBMITTED_TEXT}}

---

## YOUR RESPONSE

Extract references from the text above and return valid JSON following the schema.
