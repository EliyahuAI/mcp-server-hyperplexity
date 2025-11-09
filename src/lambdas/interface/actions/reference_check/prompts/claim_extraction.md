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
5. **Claim Criticality**: How critical is this claim to the document's central thesis?

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

## CLAIM CRITICALITY ASSESSMENT

For each claim, assess how critical it is to the document's central thesis. If this claim were proven false, how much damage would it do to the main argument?

**Criticality Levels** (1-5 scale, where 1 = Critical, 5 = Context):

**Level 1 - Critical** - This is a central thesis claim. The entire document's argument depends on this being true. If false, the entire conclusion collapses.
   - Example: In a paper arguing "COVID vaccines are effective", the claim "Vaccines reduced hospitalizations by 90%" is Critical.

**Level 2 - Major** - This is key supporting evidence for the main argument. If false, it significantly weakens the thesis, though the argument might still hold with other evidence.
   - Example: A specific study supporting the vaccine claim; losing this study weakens but doesn't destroy the argument.

**Level 3 - Supporting** - This is important corroborating evidence, but not essential. The thesis remains viable without it, supported by other claims.
   - Example: Additional data points that reinforce but aren't necessary for the main conclusion.

**Level 4 - Minor** - This is a peripheral detail or tangential point. If false, the impact on the main argument is minimal.
   - Example: Historical context about when a vaccine was developed; interesting but not central to effectiveness claims.

**Level 5 - Context** - This is background information, definitions, or general context. If false, there's no impact on the central thesis.
   - Example: "mRNA technology has been studied for decades" - provides context but isn't essential to the main argument.

**Output Format for Criticality:**
Return as: `{level} - {level_name}: {brief reason}`

Examples:
- `1 - Critical: Central thesis claim about vaccine effectiveness`
- `3 - Supporting: Additional evidence corroborating main finding`
- `5 - Context: Background information on mRNA technology history`

**Assessment Guidelines:**
- Consider the document's primary purpose and thesis
- Think: "If this claim is false, what happens to the main argument?"
- Be objective - assess structural importance, not just interesting vs. boring
- When in doubt between two levels, choose the more conservative (higher number = lower criticality)
- Always include the numeric level, level name, and brief reason

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

## ORIGINAL RESULTS vs EXTERNAL REFERENCES

When extracting claims, distinguish between two types of support:

### External References (use `reference` field)
Claims supported by external sources (other papers, studies, reports):
- Use the `reference` field with citation numbers: `[1]`, `[2]`, etc.
- These cite OTHER people's work or external sources
- Examples:
  - "According to Smith et al., LLMs hallucinate 15% of the time" → `reference: "[1]"`
  - "Previous research shows..." → `reference: "[2]"`

### Original Results (use `supporting_data` field)
Claims supported by original findings/data from THIS paper being analyzed:
- Use the `supporting_data` field (optional)
- **CRITICAL**: Provide the ACTUAL measurement/data explicitly, not just a reference to where it is
- Include specific numbers, sample sizes, percentages, metrics, table/figure references
- Format: `"Explicit measurement/data description (Table/Figure X, Section name)"`
- These describe the paper's OWN findings, experiments, or data
- Examples:
  - "Our model achieved 95% accuracy on the test set" → `supporting_data: "Model achieved 95% accuracy on test dataset (n=5,000 samples, Table 2, Results section)"`
  - "We surveyed 500 participants about social media usage" → `supporting_data: "Survey results: 78% of 500 participants reported daily social media use averaging 3.2 hours (Figure 1, Methods section)"`
  - "The experiment showed a 30% improvement" → `supporting_data: "Experimental measurements: 30% improvement in performance over baseline (p<0.05, n=100 trials, Table 3, Results section)"`
  - "Participants rated the interface highly" → `supporting_data: "User ratings: Mean score 4.2/5.0 from 250 participants (SD=0.8, Figure 4, User Study section)"`

**What to include**:
- ✅ Specific numbers and measurements
- ✅ Sample sizes (n=X)
- ✅ Statistical values (mean, SD, p-values, percentages)
- ✅ Table/Figure references where data appears
- ✅ Section name
- ❌ DON'T just say "Results section shows..." without the actual data
- ❌ DON'T just reference location without stating the measurement

**When to use which**:
- If claim cites another paper/source → use `reference` field with `[1]`, `[2]`
- If claim describes original results from this paper → use `supporting_data` with explicit measurements
- If claim has both external citation AND original results → include both fields
- If claim has neither → both fields are `null`

## REFERENCE FORMATS TO RECOGNIZE

Look for these citation patterns in the text:

**Numbered citations:**
- `[1]`, `[2]`, `(1)`, `(2)`
- Reference list typically at end: "[1] Author, A. (2024). Title..."
- **In claim `reference` field**: Use just the number: `[1]`, `[2]`, etc.

**Author-date citations:**
- `[Smith et al., 2024]`
- `(Johnson, 2023)`
- `Smith and Jones (2024)`
- **In claim `reference` field**: Convert to numbered format: `[1]`, `[2]`, etc. (not the author-year text)
- Provide mapping in `reference_list`

**Superscript citations:**
- `fact¹`, `statement²`
- **In claim `reference` field**: Convert to `[1]`, `[2]`, etc.

**Inline references:**
- "According to Smith (2024)..."
- "A recent Nature study found..."
- **In claim `reference` field**: Convert to `[1]`, `[2]`, etc. if you can identify the source

**DOI/URL references:**
- `doi:10.1234/example`
- `https://arxiv.org/abs/2401.12345`
- **In claim `reference` field**: Store the DOI/URL directly OR assign a number and include in `reference_list`

**CRITICAL**: In the claim's `reference` field, ALWAYS use ONLY the reference NUMBER:
- Numbered refs: ONLY the number(s): `[1]`, `[2][3]`, etc.
- DO NOT include author names: ❌ `[1] Smith et al.` is WRONG
- DO NOT include years: ❌ `[1] (2023)` is WRONG
- DO NOT include any text after the number: ❌ `[1] Smith et al. (2023)` is WRONG
- ONLY the bracketed number: ✅ `[1]` is CORRECT
- The system will expand `[1]` to full citation later during CSV generation

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

For each claim, record its location in the original text with the following fields:

**CRITICAL**: All indices are **0-based** and character positions are **from the beginning of the entire document** (position 0 = first character).

- **start_char**: Character index where claim starts, from document start (required)
- **end_char**: Character index where claim ends, from document start (required)
- **paragraph_index**: Which paragraph (0 = first paragraph) (required)
- **sentence_index**: Which sentence within the paragraph (0 = first sentence) (if identifiable)
- **word_start**: Starting word index from document start (if identifiable)
- **word_end**: Ending word index from document start (if identifiable)
- **section_name**: Name of the section **ONLY if clearly labeled** (optional but helpful)
  - Use markdown headings: `## Section Name` or `### Subsection`
  - Use explicitly labeled sections: "Introduction:", "Methods:", "Conclusion:"
  - **Prefer the last 2 subsection levels** for specificity (e.g., "Methods > Data Collection" not just "Methods")
  - If no clear sections, omit this field
  - Examples: "Introduction > Background", "Results > Primary Findings", "Discussion"

**Character counting example**:
```
"Hello world. This is a test."
 ^            ^
 0            13 (start_char for "This")
```

This data will be formatted as a human-readable semicolon-delimited string in the final CSV output.

**Example formats**:
- With section: `"Section: Introduction; Para: 2; Sentence: 3; Words: 45-67; Chars: 234-456"`
- Without section: `"Para: 2; Sentence: 3; Words: 45-67; Chars: 234-456"`
- Minimal: `"Para: 2; Chars: 234-456"`

IMPORTANT: Always provide at minimum **start_char**, **end_char**, and **paragraph_index**. Additional fields are helpful but optional.

## REFERENCE LIST HANDLING

The text may include a "--- PARSED REFERENCES ---" or "--- REFERENCES DETECTED ---" section at the end.

**If you see "--- REFERENCES DETECTED ---"** (Path A: Inline links):
- References are already inline with URLs in the text
- Use them exactly as they appear
- Do NOT include `reference_list` in your output

**If you see "--- PARSED REFERENCES ---"** (Path B: Quality check PASSED):
- Python successfully extracted a reference list
- Quality check has verified these are complete citations (not fragments)
- **Trust these references** - they are sufficiently complete
- Use the provided numbers `[1]`, `[2]` in claim `reference` fields
- Do NOT include `reference_list` in your output (waste of effort)
- Convert author-year citations in text to the provided numbers

**If you see "--- PARSED REFERENCES FAILED QUALITY CHECK ---"** (Path B: Quality check FAILED):
- Python attempted extraction but got fragments/garbage
- Quality check detected: too short, lowercase starts, missing author/year/URL patterns
- **YOU MUST PROVIDE YOUR OWN `reference_list`** - This is REQUIRED!
- Find the References/Bibliography section in the document (usually at the end)
- Extract ALL complete references and assign numbers [1], [2], [3], etc. in order
- Map author-year citations like `(Firth et al., 2019)` to your numbered refs like `[1]`
- In claim `reference` fields: Use ONLY numbers `[1]`, `[2]`, NOT `(Author, Year)`
- In `reference_list`: Include full citations
- Ignore the unusable parsed refs shown (they're just for reference)

**Example of FAILED QUALITY CHECK**:
```
You see: "--- PARSED REFERENCES FAILED QUALITY CHECK ---"
Unusable parsed refs: ["prompted with categorized", ":853-861, 2015"]

What you must do:
1. Find References section at end of document
2. Extract: "Firth, J. et al. (2019). The online brain: how the internet..."
3. Number sequentially: [1], [2], [3]...
4. In claims: "reference": "[1]" ← Just number!
5. In reference_list: {"ref_id": "[1]", "full_citation": "Firth, J. et al. (2019)..."}
```

**If you see "--- NOTICE: No reference list detected ---"** (Path C: Not found):
- Python found no reference section
- If text has numbered citations like [1], [2]: You MUST provide complete `reference_list`
- If text has author-year citations like (Smith, 2023): Extract and convert to numbered format [1], [2], etc.
- If text has no citations: Unreferenced claims, omit `reference_list`

---

## SOLEMN OATH - REFERENCE HANDLING

**BEFORE YOU BEGIN EXTRACTION, YOU MUST TAKE THIS OATH**:

By the power of electricity and all things transistors, I solemnly swear that:

1. **I will check for reference sections** at the end of the input text:
   - "--- REFERENCES DETECTED ---" (inline links - already good)
   - "--- PARSED REFERENCES ---" (numbered refs extracted by Python - quality checked)
   - "--- PARSED REFERENCES FAILED QUALITY CHECK ---" (fragments/garbage detected)
   - "--- NOTICE: No reference list detected ---" (none found)

2. **If NO reference section is shown** (system already validated them):
   - The references in the text are already in good format
   - I will use them exactly as they appear in the text
   - I will NOT include `reference_list` in my output

3. **If "PARSED REFERENCES" are provided** (quality check PASSED):
   - I swear they are **sufficiently complete to identify all citations**
   - The provided list does NOT need to be rebuilt
   - I will use the provided numbers `[1]`, `[2]` in claim `reference` fields
   - I will NOT waste effort creating my own `reference_list`

4. **If "PARSED REFERENCES FAILED QUALITY CHECK" is shown** (fragments/garbage):
   - Automated parsing was unsuccessful - fragments detected
   - I MUST extract complete reference list from the References/Bibliography section myself
   - I will number them [1], [2], [3] sequentially
   - I will provide complete `reference_list` in my output
   - I will ignore the unusable parsed refs shown

5. **If "NOTICE: No reference list detected" is shown**:
   - I will extract references myself and provide complete `reference_list`
   - I will number them [1], [2], [3] sequentially

6. **I will NEVER use author-year format** like `(Firth et al., 2019)` in claim `reference` fields
7. **I will convert in-text citations** like `(Firth et al., 2019)` to numbered format `[1]` using provided/extracted refs
8. **I understand the system will convert** `[1]` → `[1] FirstAuthor (Year)` automatically later

**This oath is binding. Trust provided references. Do not rebuild them unnecessarily.**

---

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

## TABLE NAMING

Provide a concise, descriptive name for this reference check table based on the content.

**Guidelines**:
- 2-5 words max
- Describes the topic or claims being checked
- Examples: "Tylenol Autism Claims", "Climate Change Data", "AI Hallucination Studies"
- Use title case
- No special characters or punctuation

## OUTPUT FORMAT

**CRITICAL INSTRUCTIONS - READ CAREFULLY**:

**CLAIM ORDERING REQUIREMENTS**:

**1. Assign claim_order (document position)**:
- BEFORE sorting, assign each claim a sequential `claim_order` number based on its position in the original document
- First claim in document: `claim_order: 1`
- Second claim in document: `claim_order: 2`
- And so on...
- This preserves the original document sequence regardless of sorting

**2. Sort claims by criticality (output order)**:
- **MANDATORY**: After assigning claim_order, sort the claims array by criticality level (most critical first)
- Output order: Level 1 (Critical) → Level 2 (Major) → Level 3 (Supporting) → Level 4 (Minor) → Level 5 (Context)
- Within the same criticality level, maintain document order (use claim_order as tiebreaker)
- This ensures the most important claims are validated first

**Example**:
- Document has claims appearing in order: A (criticality 3), B (criticality 1), C (criticality 2)
- Assign: A gets claim_order=1, B gets claim_order=2, C gets claim_order=3
- Then sort by criticality: Output order is B (crit 1, order 2), C (crit 2, order 3), A (crit 3, order 1)
- Users can see B was the 2nd claim in the document but is now first due to being most critical

**STEP 1: BUILD YOUR REFERENCE LIST FIRST**
- Look at the "PARSED REFERENCES" section at the end of the input text
- If the parsed references are fragments/garbage/unusable (like "prompted with categorized" or ":853-861, 2015"):
  - Find the References/Bibliography section in the document
  - Extract ALL complete references from that section
  - Number them sequentially: [1], [2], [3], etc.
  - Create your `reference_list` with all references
- If the parsed references are usable and complete:
  - Use them as provided
  - Do NOT include `reference_list` in your output

**STEP 2: MAP CITATIONS TO NUMBERED REFERENCES**
- Find each citation in the text: `(Firth et al., 2019)`, `(Satici et al., 2023)`, etc.
- Match them to your numbered references: `(Firth et al., 2019)` → `[1]`
- In claim `reference` fields: Use ONLY the number: `[1]`, NOT `(Firth et al., 2019)`

**BACKUP MAPPING RULE** (if provided references lack numbers):
- If the provided reference list contains URLs/citations WITHOUT numbered format like [1], [2]:
  - Use the provided references directly in claim `reference` fields
  - Example: If provided ref is just "https://example.com/paper", use that in claim reference field
  - This is rare but can happen with inline citations

**OATH REMINDER**:
Remember your oath above! If provided parsed references exist:
- Trust them - they are sufficient to identify citations
- Do NOT create your own reference_list (waste of effort!)
- If refs have numbers [1], [2]: Use those numbers in claims
- If refs don't have numbers: Use the provided refs directly in claims
- Convert author-year citations to the provided reference format (numbered or direct)

**OUTPUT STRUCTURE** (reference_list comes FIRST before claims):

```json
{
  "is_suitable": true,
  "table_name": "Tylenol Autism Claims",
  "source_type_guess": "Perplexity",
  "source_confidence": 0.9,
  "total_claims": 5,
  "claims_with_references": 3,
  "claims_without_references": 2,
  "reference_list": [
    {
      "ref_id": "[1]",
      "full_citation": "Johnson, A. (2023). Understanding AI Hallucinations. Nature AI, 5(2), 123-145."
    },
    {
      "ref_id": "[2]",
      "full_citation": "Chen, L. et al. (2024). Measuring Factual Accuracy. arXiv:2401.12345"
    }
  ],
  "claims": [
    {
      "claim_id": "claim_001",
      "claim_order": 2,
      "statement": "AI models can hallucinate facts in 15-20% of responses",
      "context": "Recent research has examined the accuracy of large language models. AI models can hallucinate facts in 15-20% of responses. This has implications for real-world deployment.",
      "criticality": "1 - Critical: Core statistical claim about hallucination rates",
      "reference": "[2]",
      "supporting_data": null,
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
        "paragraph_index": 2,
        "sentence_index": 1,
        "word_start": 25,
        "word_end": 40,
        "section_name": "Results"
      }
    },
    {
      "claim_id": "claim_002",
      "claim_order": 5,
      "statement": "Newer models show improvement in factual accuracy",
      "context": "However, newer models show improvement in factual accuracy. The latest GPT-4 Turbo reduces hallucinations compared to earlier versions.",
      "criticality": "3 - Supporting: Additional evidence about model improvements",
      "reference": null,
      "supporting_data": null,
      "reference_details": null,
      "text_location": {
        "start_char": 380,
        "end_char": 435,
        "paragraph_index": 4,
        "sentence_index": 0,
        "word_start": 75,
        "word_end": 85
      }
    },
    {
      "claim_id": "claim_003",
      "claim_order": 8,
      "statement": "Our fine-tuned model achieved 92% accuracy on the benchmark dataset",
      "context": "We fine-tuned the base model on domain-specific data. Our fine-tuned model achieved 92% accuracy on the benchmark dataset. This represents a 15% improvement over the baseline.",
      "criticality": "1 - Critical: Primary experimental result of this study",
      "reference": null,
      "supporting_data": "Fine-tuned model achieved 92% accuracy on benchmark dataset (n=10,000 test samples, 15% improvement over 77% baseline, p<0.001, Table 2, Results section)",
      "reference_details": null,
      "text_location": {
        "start_char": 890,
        "end_char": 960,
        "paragraph_index": 12,
        "sentence_index": 1,
        "word_start": 180,
        "word_end": 195,
        "section_name": "Experimental Results"
      }
    }
  ]
}
```

**Important notes about `reference_list`**:
- **Order in output**: `reference_list` comes FIRST in JSON, right after metadata, before `claims` array
- **Path A (inline links)**: Never include reference_list (omit field entirely)
- **Path B (parsed refs)**: REQUIRED if parsed refs are unusable/fragments - you must provide complete replacement
- **Path C (not found)**: REQUIRED if numbered or author-year citations exist in text
- **Remember your oath**: Your reference_list must be sufficiently complete and final - it will NOT be rebuilt
- **Quality check**: Each ref should have author, year, title, and source identifiable in full_citation

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

### Author-Year Citations (Academic Papers)
If the text uses author-year format like `(Smith et al., 2023)` instead of numbered citations:
- Extract the full reference list from the end of the document (usually under "References" or "Bibliography")
- Assign sequential numbers: `[1]`, `[2]`, etc.
- **In claim `reference` fields**: Use ONLY the reference number (e.g., `[1]`, `[2]`)
  - The system will later convert this to short format like `[1] Smith et al. (2023)`
  - Do NOT include author names or years in the claim reference field
  - Just the number: `[1]` not `[1] Smith et al. (2023)`
- **In `reference_list`**: Include full citations from the reference section
  - These are used as the source for later short-form conversion
- Example: If text says "(Firth et al., 2019)":
  - In claim: `"reference": "[1]"`
  - In reference_list: `{"ref_id": "[1]", "full_citation": "Firth, J. et al. (2019). The online brain: how the internet may be changing our cognition. World psychiatry, 18(2):119–129."}`

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
