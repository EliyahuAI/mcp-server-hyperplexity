# Claim Extraction Prompt

## TASK
Extract verifiable claims/statements from the provided text and identify any references cited for each claim.

{{EXTRACTION_RANGE_INSTRUCTIONS}}

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

**Criticality Levels** (1-5 scale, where 5 = Critical, 1 = Minimal):

**Level 5 - Critical** - This is a central thesis claim. The entire document's argument depends on this being true. If false, the entire conclusion collapses.
   - Example: In a paper arguing "COVID vaccines are effective", the claim "Vaccines reduced hospitalizations by 90%" is Critical.

**Level 4 - Major** - This is key supporting evidence for the main argument. If false, it significantly weakens the thesis, though the argument might still hold with other evidence.
   - Example: A specific study supporting the vaccine claim; losing this study weakens but doesn't destroy the argument.

**Level 3 - Supporting** - This is important corroborating evidence, but not essential. The thesis remains viable without it, supported by other claims.
   - Example: Additional data points that reinforce but aren't necessary for the main conclusion.

**Level 2 - Minor** - This is a peripheral detail or tangential point. If false, the impact on the main argument is minimal.
   - Example: Historical context about when a vaccine was developed; interesting but not central to effectiveness claims.

**Level 1 - Minimal** - This is background information, definitions, or general context. If false, there's no impact on the central thesis.
   - Example: "mRNA technology has been studied for decades" - provides context but isn't essential to the main argument.

**Output Format for Criticality:**
Return as: `{level} - {level_name}: {brief reason}`

Examples:
- `5 - Critical: Central thesis claim about vaccine effectiveness`
- `3 - Supporting: Additional evidence corroborating main finding`
- `1 - Minimal: Background information on mRNA technology history`

**Assessment Guidelines:**
- Consider the document's primary purpose and thesis
- Think: "If this claim is false, what happens to the main argument?"
- Be objective - assess structural importance, not just interesting vs. boring
- When in doubt between two levels, choose the more conservative (higher number = lower criticality)
- Always include the numeric level, level name, and brief reason

## CLAIM IDENTIFICATION RULES

### CRITICAL: References Require Claims
**If text has a reference citation, it MUST be extracted as a claim.** Any statement that cites a source (e.g., "[1]", "(Smith et al., 2023)") MUST be extracted, even if the claim seems weak, obvious, or would otherwise be skipped. The presence of a reference indicates the author thought the statement needed support, making it important to validate.

- ✅ "Water is essential for life [1]" → Extract (has reference, even though obvious)
- ✅ "AI is a rapidly growing field (Jones, 2024)" → Extract (has reference, even though trivial)
- ✅ "The study was conducted in Boston [3]" → Extract (has reference)

### What IS a claim:
- ✅ **Any statement with a reference** (ALWAYS extract - see rule above)
- ✅ Factual assertions: "AI models hallucinate facts in 15-20% of responses"
- ✅ Research findings: "Study X found Y"
- ✅ Statistical claims: "The accuracy improved by 25%"
- ✅ Capability statements: "GPT-4 can process 128K tokens"
- ✅ Event descriptions: "The experiment was conducted in 2024"
- ✅ Comparative statements: "Model A outperforms Model B"

### What is NOT a claim (skip these - ONLY if unreferenced):
- ❌ Obvious truths WITHOUT references: "The sun rises in the east"
- ❌ Definitions WITHOUT references: "Machine learning is a subset of AI"
- ❌ Pure opinions: "I think this is interesting"
- ❌ Questions: "What if we tried X?"
- ❌ Methodological descriptions WITHOUT references: "We used Python for analysis"
- ❌ Trivial statements WITHOUT references: "AI is a rapidly growing field"

**Remember**: Claims without references are still valid and should be extracted if they meet the criteria above. The rule is: referenced text → ALWAYS a claim; unreferenced text → apply normal filtering.

### Abstract vs Main Text Priority

**CRITICAL RULE**: When the same claim appears in both the abstract AND main text:
- **Extract from main text ONLY** (skip the abstract version)
- Main text usually has more context, details, and references
- Abstract versions are often simplified summaries

**When to extract from abstract**:
- ✅ Claim is ONLY in abstract (not repeated in main text)
- ✅ Abstract provides unique synthesis not stated elsewhere

**Example**:
```
Abstract: "Our model achieved 92% accuracy"
Results section: "Our model achieved 92% accuracy on the benchmark dataset (n=10,000, Table 2)"

→ Extract the Results section version (has details + table reference)
→ Skip the abstract version (less informative duplicate)
```

**How to identify abstract**:
- Usually marked as "ABSTRACT" or "A BSTRACT" section
- Typically appears near the beginning of the document
- After abstract, the main text begins (Introduction, Methods, Results, etc.)

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

## REFERENCE HANDLING - SIMPLIFIED

Since references have been pre-confirmed by the system, you do NOT need to extract reference details.

Simply:
- Use the reference number `[1]`, `[2]`, etc. in the claim's `reference` field
- Do NOT include `reference_details` in your output (not needed - references already confirmed)

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

The text will include a "--- CONFIRMED REFERENCES ---" section at the end showing all verified references.

**These references have been confirmed** through a two-stage process:
1. Python parsing attempted to extract references
2. AI (claude-haiku-4-5) confirmed/extracted complete references where needed

**Your job**:
- Use the provided confirmed references in claim `reference` fields
- Use ONLY the reference numbers: `[1]`, `[2]`, etc.
- Do NOT include `reference_list` in your output (already confirmed upstream)
- Convert any author-year citations in the text to the provided reference numbers

**Example**:
```
Text says: "According to Firth et al. (2019), internet usage affects cognition"

--- CONFIRMED REFERENCES ---
[1] Firth, J. et al. (2019). The online brain: how the internet may be changing our cognition...
[2] Smith, A. (2024). Digital literacy in the modern age...

Your claim extraction:
{
  "claim_id": "claim_001",
  "statement": "Internet usage affects cognition",
  "reference": "[1]",  ← Just the number!
  ...
}
```

**If no references are provided**, the text has unreferenced claims - set `reference: null` for those claims.

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

**CLAIM ORDERING**:

**Assign claim_order (document position)**:
- Assign each claim a sequential `claim_order` number based on its position in the original document
- First claim in document: `claim_order: 1`
- Second claim in document: `claim_order: 2`
- And so on...
- Extract claims in document order (no sorting needed)
- The claim_order field helps users track where each claim appeared

**EXTRACTION STEPS**:

**STEP 1: REVIEW CONFIRMED REFERENCES**
- Check the "--- CONFIRMED REFERENCES ---" section at the end of the input text
- These references have already been verified by the system
- Use the provided reference numbers `[1]`, `[2]`, etc. exactly as shown

**STEP 2: MAP CITATIONS TO REFERENCE NUMBERS**
- Find each citation in the text: `(Firth et al., 2019)`, `[1]`, `(Satici et al., 2023)`, etc.
- Match them to the confirmed reference numbers
- In claim `reference` fields: Use ONLY the number: `[1]`, NOT `(Firth et al., 2019)`

**STEP 3: EXTRACT CLAIMS**
- Extract discrete, verifiable claims from the text in document order
- Assign criticality (1-5 scale, where 5=Critical, 1=Minimal)
- Assign claim_order (sequential document position: 1, 2, 3...)
- Link to confirmed references using numbers only

**OUTPUT STRUCTURE**:

```json
{
  "is_suitable": true,
  "table_name": "Tylenol Autism Claims",
  "source_type_guess": "Perplexity",
  "source_confidence": 0.9,
  "claims": [
    {
      "claim_id": "claim_001",
      "claim_order": 1,
      "statement": "AI models can hallucinate facts in 15-20% of responses",
      "context": "Recent research has examined the accuracy of large language models. AI models can hallucinate facts in 15-20% of responses. This has implications for real-world deployment.",
      "criticality": "5 - Critical: Core statistical claim about hallucination rates",
      "reference": "[2]",
      "supporting_data": null,
      "text_location": {
        "start_char": 125,
        "end_char": 195,
        "paragraph_index": 2,
        "sentence_index": 1,
        "section_name": "Results"
      }
    },
    {
      "claim_id": "claim_002",
      "claim_order": 2,
      "statement": "Newer models show improvement in factual accuracy",
      "context": "However, newer models show improvement in factual accuracy. The latest GPT-4 Turbo reduces hallucinations compared to earlier versions.",
      "criticality": "3 - Supporting: Additional evidence about model improvements",
      "reference": null,
      "supporting_data": null,
      "text_location": {
        "start_char": 380,
        "end_char": 435,
        "paragraph_index": 4,
        "sentence_index": 0
      }
    },
    {
      "claim_id": "claim_003",
      "claim_order": 3,
      "statement": "Our fine-tuned model achieved 92% accuracy on the benchmark dataset",
      "context": "We fine-tuned the base model on domain-specific data. Our fine-tuned model achieved 92% accuracy on the benchmark dataset. This represents a 15% improvement over the baseline.",
      "criticality": "5 - Critical: Primary experimental result of this study",
      "reference": null,
      "supporting_data": "Fine-tuned model achieved 92% accuracy on benchmark dataset (n=10,000 test samples, 15% improvement over 77% baseline, p<0.001, Table 2, Results section)",
      "text_location": {
        "start_char": 890,
        "end_char": 960,
        "paragraph_index": 12,
        "sentence_index": 1,
        "section_name": "Experimental Results"
      }
    }
  ],
  "total_claims": 3,
  "claims_with_references": 2,
  "claims_without_references": 1
}
```

**Important notes**:
- **Claims come first**: Extract ALL claims in the `claims` array BEFORE computing counts
- **Counts come after**: Compute `total_claims`, `claims_with_references`, and `claims_without_references` AFTER extraction
- **Extract in document order**: Return claims as they appear in the text (no sorting)
- **claim_order tracks position**: Assign sequential numbers (1, 2, 3...) based on document appearance
- **Criticality scale**: 5=Critical (thesis depends on it), 1=Minimal (background context)
- **References are pre-confirmed**: Do NOT include `reference_list` or `reference_details` in your output
- **Use numbers only**: In claim `reference` fields, use only `[1]`, `[2]`, etc.
- **supporting_data is optional**: Include when claim has original measurements from this paper

## SPECIAL CASES

### Mixed Content
If some claims have references and others don't, extract all of them. Mark reference as `null` for uncited claims.

### Multiple References per Claim
If a claim cites multiple references (e.g., "[1][2][3]" or "[1,2,3]"):
- Create a single claim entry
- List all references together in the reference field: "[1][2][3]"
- The validator will access all cited sources and synthesize findings

### Author-Year Citations (Academic Papers)
If the text uses author-year format like `(Smith et al., 2023)`:
- Match them to the confirmed references provided
- **In claim `reference` fields**: Use ONLY the reference number (e.g., `[1]`, `[2]`)
- Example: If text says "(Firth et al., 2019)" and confirmed refs show "[1] Firth, J. et al. (2019)...":
  - In claim: `"reference": "[1]"`

### No References Found
If no confirmed references are provided, the text has unreferenced claims. Set `reference: null` for claims without citations.

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

## FINAL REMINDERS BEFORE YOU RESPOND

**CRITICAL - READ THIS BEFORE GENERATING OUTPUT**:

1. **EXTRACT IN DOCUMENT ORDER** - Return claims as they appear in the text (1st claim → claim_order=1, 2nd → claim_order=2, etc.)

2. **CRITICALITY SCALE** - 5=Critical (thesis depends on it), 1=Minimal (background info)

3. **DO NOT INCLUDE reference_details** - References are already confirmed, no need to extract details

4. **REFERENCE FIELD: NUMBERS ONLY** - Use `[1]`, `[2]`, not `[1] Author (2023)`

5. **PREFER MAIN TEXT** - If same claim appears in abstract and main text, use main text version

---

## YOUR RESPONSE

Analyze the text above and return your extraction in valid JSON format following the schema described above.
