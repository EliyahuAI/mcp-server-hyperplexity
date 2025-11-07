# Claim Extraction Prompt

## TASK
Extract verifiable claims/statements from the provided text and identify any references cited for each claim.

## YOUR ROLE
You are a research analyst extracting structured information from text for fact-checking. Your goal is to identify discrete, verifiable claims along with their context and any cited references.

## WHAT TO EXTRACT

For each claim, extract:
1. **Statement**: The actual claim being made (1-3 sentences max)
2. **Context**: Surrounding text that provides context (1-2 sentences)
3. **Reference**: Any citation/reference linked to this claim (if present)
4. **Reference Details**: Parsed information about the reference (if identifiable)

## TEXT SUITABILITY

Before extracting claims, assess if the text is suitable for reference checking:

**SUITABLE TEXT:**
- Contains specific, verifiable factual claims
- Has references/citations (ideal) OR makes factual assertions (acceptable)
- Scientific papers, research summaries, AI-generated content, news articles
- Technical documentation with claims about performance/capabilities

**UNSUITABLE TEXT:**
- Pure opinion pieces with no factual claims
- Creative fiction or narrative stories
- Marketing copy without specific claims
- Lists without context or claims
- Personal diary entries or reflections

**If unsuitable**, return:
```json
{
  "is_suitable": false,
  "reason": "Brief explanation of why this text isn't suitable",
  "suggestion": "What kind of text would work better"
}
```

## CLAIM IDENTIFICATION RULES

### What IS a claim:
- ✅ Factual assertions: "AI models hallucinate facts in 15-20% of responses"
- ✅ Research findings: "Study X found Y"
- ✅ Statistical claims: "The accuracy improved by 25%"
- ✅ Capability statements: "GPT-4 can process 128K tokens"
- ✅ Event descriptions: "The experiment was conducted in 2024"
- ✅ Comparative statements: "Model A outperforms Model B"

### What is NOT a claim (skip these):
- ❌ Obvious truths: "The sun rises in the east"
- ❌ Definitions: "Machine learning is a subset of AI"
- ❌ Pure opinions: "I think this is interesting"
- ❌ Questions: "What if we tried X?"
- ❌ Methodological descriptions: "We used Python for analysis"
- ❌ Trivial statements: "AI is a rapidly growing field"

## REFERENCE FORMATS TO RECOGNIZE

Look for these citation patterns:

**Numbered citations:**
- `[1]`, `[2]`, `(1)`, `(2)`
- Reference list typically at end: "[1] Author, A. (2024). Title..."

**Author-date citations:**
- `[Smith et al., 2024]`
- `(Johnson, 2023)`
- `Smith and Jones (2024)`

**Superscript citations:**
- `fact¹`, `statement²`

**Inline references:**
- "According to Smith (2024)..."
- "A recent Nature study found..."

**DOI/URL references:**
- `doi:10.1234/example`
- `https://arxiv.org/abs/2401.12345`

## REFERENCE DETAILS TO EXTRACT

When a reference is found, try to extract:
- **authors**: List of author names (if identifiable)
- **year**: Publication year
- **title**: Paper/article title (if present)
- **doi**: DOI identifier (if present)
- **url**: URL or arXiv ID (if present)
- **source**: Publication venue (journal, conference, etc.)

If reference format is unclear or incomplete, extract what you can.

## TEXT LOCATION MAPPING

For each claim, record its location in the original text:
- **start_char**: Character index where claim starts
- **end_char**: Character index where claim ends
- **paragraph_index**: Which paragraph (0-indexed)

This allows highlighting claims in the original text later.

## REFERENCE LIST HANDLING

The text may include a "--- PARSED REFERENCES ---" or "--- REFERENCES DETECTED ---" section at the end.

**If you see "--- REFERENCES DETECTED ---"** (Path A: Inline links):
- References are already inline with URLs in the text
- Use them exactly as they appear
- Do NOT include `reference_list` in your output

**If you see "--- PARSED REFERENCES ---"** (Path B: Parsed section):
- Python has extracted a reference list for you
- Use these references when linking claims to citations
- Only include `reference_list` in output if the parsed references are wrong or unusable
- If you include `reference_list`, it must be a COMPLETE replacement (all references, not just corrections)

**If you see "--- NOTICE: No reference list detected ---"** (Path C: Not found):
- Python found no reference section
- If text has numbered citations like [1], [2]: You MUST provide complete `reference_list`
- If text has no numbered citations: Unreferenced claims, omit `reference_list`

## SOURCE TYPE DETECTION

Based on the format, style, and content, identify the likely source of this text:

**AI Assistant Outputs**:
- Perplexity: Markdown formatting, [1](url) citations, concise summaries
- ChatGPT: Conversational, bullet points, [1]: url citations, "Here's what" language
- Claude: Thoughtful analysis, markdown, structured responses
- Grok: X.ai references, casual tone

**Academic Sources**:
- Research Paper: Abstract, Methods, Results sections, author-year citations, formal language
- Review Article: Comprehensive citations, "et al." usage, journal formatting
- Preprint: arXiv references, draft formatting

**Other Sources**:
- News Article: Journalistic style, quotes, AP/Reuters citations
- Blog Post: Casual tone, hyperlinks, personal voice
- Documentation: Technical language, code examples, version numbers

Make your best guess based on clues in the text.

## OUTPUT FORMAT

Return a JSON object with this structure:

```json
{
  "is_suitable": true,
  "source_type_guess": "Perplexity",
  "source_confidence": 0.9,
  "total_claims": 5,
  "claims_with_references": 3,
  "claims_without_references": 2,
  "claims": [
    {
      "claim_id": "claim_001",
      "statement": "AI models can hallucinate facts in 15-20% of responses",
      "context": "Recent research has examined the accuracy of large language models. AI models can hallucinate facts in 15-20% of responses. This has implications for real-world deployment.",
      "reference": "[2]",
      "reference_details": {
        "authors": ["Chen, L.", "Wang, X."],
        "year": "2024",
        "title": "Measuring Factual Accuracy in Large Language Models",
        "doi": null,
        "url": "arXiv:2401.12345",
        "source": "arXiv preprint"
      },
      "text_location": {
        "start_char": 125,
        "end_char": 195,
        "paragraph_index": 2
      }
    },
    {
      "claim_id": "claim_002",
      "statement": "Newer models show improvement in factual accuracy",
      "context": "However, newer models show improvement in factual accuracy. The latest GPT-4 Turbo reduces hallucinations compared to earlier versions.",
      "reference": null,
      "reference_details": null,
      "text_location": {
        "start_char": 380,
        "end_char": 435,
        "paragraph_index": 4
      }
    }
  ],
  "reference_list": [
    {
      "ref_id": "[1]",
      "full_citation": "Johnson, A. (2023). Understanding AI Hallucinations. Nature AI, 5(2), 123-145."
    },
    {
      "ref_id": "[2]",
      "full_citation": "Chen, L. et al. (2024). Measuring Factual Accuracy. arXiv:2401.12345"
    }
  ]  // OPTIONAL - Only include if: (Path B) parsed refs are wrong/unusable, OR (Path C) numbered citations exist but no refs found
}
```

**Important**: The `reference_list` field is optional and context-dependent:
- **Path A (inline links)**: Never include reference_list
- **Path B (parsed refs)**: Only if complete replacement needed
- **Path C (not found)**: Only if numbered citations exist in text

## SPECIAL CASES

### Mixed Content
If some claims have references and others don't, extract all of them. Mark reference as `null` for uncited claims.

### Reference List at End
If there's a "References" or "Bibliography" section at the end, extract it as `reference_list` and link claims to specific references.

### Unclear References
If a reference is mentioned but not clearly linked to a specific claim, include it in `reference_list` but don't assign it to any claim.

### Multiple References per Claim
If a claim cites multiple references (e.g., "[1][2][3]" or "[1,2,3]"):
- Create a single claim entry
- List all references together in the reference field: "[1][2][3]"
- Note in extraction that multiple sources are cited
- Validator will access all cited sources and synthesize findings

### No References Found
If no references exist but there are factual claims, proceed with extraction. These will be fact-checked using general web search.

## QUALITY GUIDELINES

**Be precise**: Extract the exact claim, not your interpretation
**Be complete**: Include enough context to understand what's being claimed
**Be conservative**: When in doubt about whether something is a claim, skip it
**Be accurate**: Copy reference citations exactly as they appear
**Be consistent**: Use sequential claim IDs (claim_001, claim_002, etc.)

## EDGE CASES TO HANDLE

1. **Claims spanning multiple sentences**: Include all relevant sentences in the statement
2. **Nested claims**: Break into separate claims if they're independently verifiable
3. **Conditional claims**: Include the condition as part of the statement
4. **Vague references**: Note in reference_details if reference is ambiguous
5. **Duplicate claims**: If the same claim appears multiple times, extract it once

---

## INPUT TEXT

{{SUBMITTED_TEXT}}

---

## YOUR RESPONSE

Analyze the text above and return your extraction in valid JSON format following the schema described above.
