# Merged Synthesis with Code-Based Citations

Your goal is to synthesize a comprehensive answer to the query using labeled source text. You will cite specific parts using codes and provide quality scores for each citation.

Query: {query}

**Today's Date:** {current_date}

## Synthesis Instructions

{synthesis_guidance}

---

## Labeled Sources

Sources are organized by search term. Text is labeled with codes you'll use for citations.

**Code Format - CRITICAL:**
- All codes have Source ID prefix: `S1:1.1, `S2:3.5
- Sentences: `S1:1.1, `S1:1.2 (source 1, section 1, sentence 1/2)
- Headings: `S1:1.0, `S2:3.0 (section header)
- Ranges: `S1:1.1-1.3 or `S1:1.1-3 (consecutive sentences)
- Word ranges: `S1:1.1.w5-7 (words 5-7, 1-indexed)
- Tables: MUST include header `S1:1.0 with data rows

**Context annotations** (use when needed):
- Heading context: [`S1:2.0] `S1:2.1 → adds section context
- Attribution: [`S2:1.w1-4] `S2:3.5 → pulls attribution from elsewhere
- Clarification: `S1:1.1 [of Gemini] or [re: Topic] `S2:2.1

**CRITICAL RULES:**
- ONLY use codes that exist in the labeled sources below
- DO NOT invent codes or cite beyond available sentences
- Each source has its own code namespace (S1:, S2:, etc.)
- Check that the code exists before citing it

{formatted_sources}

---

## Citation Format

**CRITICAL:** Your citations must include code, p-score, and reason using this EXACT format:

- Single citation: {{`S1:1.1, 0.95, P}}
- Multiple facts: {{`S1:1.1, 0.95, P}} ... {{`S2:2.3-2.5, 0.85, A}}
- Source prefix is REQUIRED: `S1:, `S2:, `S3:, etc.
- Use CURLY BRACES for citations, square brackets [] for context only

**P-Scores** (use exact values): 0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95

**Source Authority** - Assess BEFORE betting:
- **AU** (Authoritative): High general authority + known expertise on query topic
- **UK** (Unknown): Unclear authority or medium general authority
- **LA** (Low Authority): Low general authority or lacks topic expertise

**Validation: Bet on pass rate.** Imagine a judge extracts all atomic factual claims and tests each. Pass = precisely accurate. p = expected pass-rate. Consider source authority (AU/UK/LA) when betting - higher authority → higher confidence in same claim.

**Positive indicators** (higher p):
- **P=PRIMARY**: Official self-report / primary document style
- **D=DOCUMENTED**: Methods/data shown, peer reviewed
- **A=ATTRIBUTED**: Believable named source + role
- **O=OK**: No red flags, aligns with knowledge

**Negative indicators** (lower p):
- **C=CONTRADICTED**: Known to be false / internally inconsistent
- **U=UNSOURCED**: Just statements, no evidence
- **PR=PROMOTIONAL**: Clear bias
- **S=STALE**: Out of date dynamic information
- **SL=SLOP**: AI-generated SEO content

**Citation examples:**
```
"Claude Opus 4.5 was released in November 2024 {{`S1:1.1, 0.95, P}} and uses a transformer architecture {{`S1:1.2-1.3, 0.85, D}}."

"Performance improved by 40% {{`S2:2.5, 0.65, O}} according to unnamed sources {{`S3:3.1, 0.30, U}}."

"The report states {{`S1:1.5 [of the system], 0.85, A}} with attribution {{[`S2:2.1.w1-3] `S1:3.2, 0.95, P}}."
```

**Note**: Square brackets [] are ONLY for context annotations inside codes. Curly braces {{}} are for citations with p-scores.

---

## Output Format

{output_format_guidance}

**Example structure:**
```json
{{
  "comparison": {{
    "claude_opus_4": {{
      "release_date": "November 2024 {{`S1:1.1, 0.95, P}}",
      "architecture": "Transformer-based {{`S1:1.2-1.3, 0.85, D}} with MoE {{`S1:1.4, 0.85, D}}",
      "performance": {{
        "mmlu": "92.3% {{`S2:2.1, 0.95, P}}",
        "humaneval": "89.5% {{`S2:2.2, 0.95, P}}"
      }}
    }},
    "gpt_4_5": {{
      "release_date": "December 2024 {{`S3:3.1, 0.65, O}}",
      "architecture": "Undisclosed {{`S3:3.2, 0.30, U}}"
    }}
  }}{assessment_field}
}}
```

## Your Task

1. **Synthesize** a structured answer organizing information logically
2. **Cite every factual claim** using: {{`S#:code, p_score, reason}}
3. **Validate each citation** with appropriate p-score and reason
4. **Use ONLY codes that exist** in the labeled sources above
5. **Add context** to codes when needed: {{`S1:1.5 [of the system], 0.85, A}}

**Remember:**
- Every claim needs a citation: {{`S#:code, p, reason}}
- Use exact p-score values: 0.05, 0.15, 0.30, 0.50, 0.65, 0.85, 0.95
- Codes MUST exist in the labeled sources above - DO NOT invent codes
- Source prefix REQUIRED: `S1:, `S2:, etc.
- Curly braces for citations, square brackets [] for context annotations only
- Citation format: {{`S1:1.1, 0.95, P}} with NO extra quotes
