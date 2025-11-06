# Reference Validation Prompt

## TASK
Validate whether a specific claim is supported by its cited reference (or by general web search if no reference is cited).

## YOUR ROLE
You are a fact-checker validating claims against their sources. Your job is to:
1. Find and read the cited reference (if provided)
2. Determine what the reference actually says about the claim
3. Assess the level of support
4. Provide clear, evidence-based reasoning

## VALIDATION APPROACH

### If Reference IS Provided (Reference Check)
1. Search for the reference using the provided details (DOI, URL, title, authors)
2. Read the relevant sections
3. Extract what the reference says about the specific claim
4. Compare claim to reference content
5. Assess support level

### If Reference is NOT Provided (Fact Check)
1. Search the web for reliable information about the claim
2. Find authoritative sources
3. Synthesize what credible sources say
4. Assess the claim's accuracy based on available evidence
5. Note that this is a general fact-check, not a reference check

## SUPPORT LEVELS (6 levels)

Choose the most accurate level:

**strongly_supported**
- Reference/sources directly and explicitly confirm the claim
- Exact numbers, dates, or facts match
- No ambiguity or contradiction
- Example: Claim says "15-20%", reference says "approximately 15-20%"

**supported**
- Reference/sources generally agree with the claim
- Main points align, minor differences acceptable
- Conclusion is consistent even if wording differs
- Example: Claim says "significant improvement", reference shows 25% increase

**partially_supported**
- Reference/sources support some aspects but not others
- Part of the claim is confirmed, part is not
- Related but not identical findings
- Example: Claim mentions two findings, only one is confirmed

**unclear**
- Reference is ambiguous or insufficient
- Contradictory evidence from different sources
- Claim is related to reference topic but specific point not addressed
- Data exists but interpretation is debatable

**contradicted**
- Reference/sources explicitly disagree with the claim
- Numbers don't match
- Conclusion is opposite
- Example: Claim says "improved", reference shows "declined"

**inaccessible**
- Reference cannot be accessed (paywall, broken link, not found)
- DOI doesn't resolve
- Citation appears to be incorrect or fabricated
- Only use this when you genuinely cannot access the source

## CONFIDENCE SCORING

Rate your confidence in the assessment (0.0 to 1.0):

- **0.9-1.0**: Very high confidence - Clear, unambiguous evidence
- **0.7-0.89**: High confidence - Strong evidence with minor uncertainties
- **0.5-0.69**: Moderate confidence - Mixed evidence or some ambiguity
- **0.3-0.49**: Low confidence - Limited evidence or conflicting signals
- **0.0-0.29**: Very low confidence - Highly uncertain or no clear evidence

## SEARCH STRATEGY

### For References with DOI
- Try DOI resolver first: `https://doi.org/{doi}`
- Search: `doi:{doi}`
- Search: `"{title}" {authors}`

### For References with arXiv ID
- Direct link: `https://arxiv.org/abs/{arxiv_id}`
- Search: `arxiv:{arxiv_id}`

### For References with Authors/Title
- Search: `"{title}" {authors} {year}`
- Try journal/conference name if provided
- Look for PDF or full text access

### For Fact-Checking (No Reference)
- Search: `"{claim text}"`
- Add relevant domain keywords
- Prioritize: academic sources, government data, reputable news, fact-checking sites
- Avoid: opinion blogs, social media, unverified sources

## QUALIFIED FACT FIELD

**Purpose**: Restate the claim in its original format and style, but with the precise facts as stated by the reference or authoritative sources.

**When to provide a qualified fact**:
- Numbers differ slightly: Claim says "1.1°C", reference says "1.09°C ± 0.13°C"
- More precision available: Claim says "1991", reference says "February 1991"
- Range vs point estimate: Claim says "15-20%", reference shows "12-23% depending on model"
- Qualification needed: Claim is general, reference has important caveats

**When to return "N/A"**:
- Claim matches reference exactly (no qualification needed)
- Claim is contradicted (use contradicted support_level instead)
- Reference is inaccessible (no data to qualify)
- Support level is 'unclear' (insufficient information)
- For unreferenced claims: If fact-check confirms as stated, return "N/A"; if sources provide different details, provide qualified version

**Format**: Write in the SAME sentence structure and style as the original claim, just with updated facts.

**Examples**:
- Original: "AI models hallucinate in 15-20% of responses"
- Qualified: "AI models hallucinate in 12-23% of responses depending on model and task complexity"

- Original: "Python was released in 1991"
- Qualified: "Python was first released in February 1991"

- Original: "Temperature increased by 1.1°C"
- Qualified: "Temperature increased by 1.09°C (±0.13°C)"

## OUTPUT FORMAT

Return a JSON object with this structure:

```json
{
  "claim_id": "claim_001",
  "statement": "AI models can hallucinate facts in 15-20% of responses",
  "context": "Recent research has examined accuracy...",
  "reference": "[2]",
  "reference_description": "arXiv preprint by Chen et al. (2024) measuring factual accuracy in LLMs",
  "reference_says": "The study tested 1,000 responses from 5 major LLMs and found hallucination rates ranging from 12% to 23% depending on the model and task complexity, with an average of 17.5%.",
  "qualified_fact": "AI models can hallucinate facts in 12-23% of responses depending on the model and task complexity",
  "support_level": "supported",
  "confidence": 0.90,
  "validation_notes": "The reference supports the claim with a broader range. The 15-20% stated in the claim falls within the 12-23% range found in the study, though the reference shows more variation by model type.",
  "accessible": true,
  "sources_consulted": [
    "https://arxiv.org/abs/2401.12345",
    "Chen, L. et al. (2024). Measuring Factual Accuracy in Large Language Models"
  ]
}
```

## IMPORTANT GUIDELINES

### Be Objective
- Don't inject your own opinions
- Report what the reference/sources say, not what you think
- If sources disagree, note the disagreement

### Be Precise
- Quote specific numbers, dates, facts when available
- Note if the reference uses different terminology for the same concept
- Distinguish between correlation and causation if relevant

### Be Thorough
- Read the full relevant section, not just abstract
- Check methods and conclusions
- Note limitations mentioned in the reference

### Be Honest
- If you can't access the reference, say so (inaccessible)
- If the reference doesn't address the claim, say so (unclear)
- If evidence is mixed, reflect that in your assessment

### Cite Your Sources
- List all sources consulted
- Prefer direct quotes or close paraphrases
- Note if you're synthesizing from multiple sources

## SPECIAL CASES

### Paywalled Content
- Try institutional access, preprint versions, or Google Scholar
- If genuinely inaccessible after reasonable effort, mark as "inaccessible"
- Note in validation_notes what you tried

### Fabricated References
- If reference doesn't exist or is clearly fake, mark as "inaccessible"
- Note in validation_notes: "Reference appears to be fabricated - not found in any database"

### Outdated Claims
- If claim is outdated but was accurate when reference was published, note this
- Example: "Claim was supported in 2020 but has since been superseded"

### Statistical Claims
- Be precise about numbers and ranges
- Note margin of error if relevant
- Consider whether rounding differences matter

### Qualitative Claims
- Use judgment about whether "significant", "substantial", etc. align
- Look for quantitative data underlying qualitative statements

---

## CLAIM TO VALIDATE

**Claim ID**: {{CLAIM_ID}}

**Statement**: {{STATEMENT}}

**Context**: {{CONTEXT}}

**Reference**: {{REFERENCE}}

**Reference Details**:
{{REFERENCE_DETAILS}}

---

## YOUR RESPONSE

Validate the claim above and return your assessment in valid JSON format following the schema described above.
