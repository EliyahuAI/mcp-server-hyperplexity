# QC Layer Example Output

This document shows an example of how the QC (Quality Control) layer reviews discovered rows and makes keep/reject decisions.

---

## Input to QC Layer

After row discovery and consolidation, we have 12 candidate rows:

```json
[
  {
    "id_values": {"Company Name": "Anthropic", "Website": "https://anthropic.com"},
    "match_score": 0.95,
    "match_rationale": "Leading AI safety research company with active job postings",
    "source_subdomain": "AI Research Companies",
    "found_by_models": ["sonar-pro(high)"]
  },
  {
    "id_values": {"Company Name": "OpenAI", "Website": "https://openai.com"},
    "match_score": 0.92,
    "match_rationale": "Major AI company developing GPT models, multiple job openings",
    "source_subdomain": "AI Research Companies",
    "found_by_models": ["sonar(high)", "sonar-pro(high)"]
  },
  {
    "id_values": {"Company Name": "DeepMind", "Website": "https://deepmind.com"},
    "match_score": 0.88,
    "match_rationale": "Google AI research lab with ongoing hiring",
    "source_subdomain": "AI Research Companies",
    "found_by_models": ["sonar(high)"]
  },
  {
    "id_values": {"Company Name": "Hugging Face", "Website": "https://huggingface.co"},
    "match_score": 0.85,
    "match_rationale": "AI model platform company expanding team",
    "source_subdomain": "AI Tools & Platforms",
    "found_by_models": ["sonar(low)"]
  },
  {
    "id_values": {"Company Name": "Cohere", "Website": "https://cohere.ai"},
    "match_score": 0.82,
    "match_rationale": "Enterprise AI platform with active recruitment",
    "source_subdomain": "AI Tools & Platforms",
    "found_by_models": ["sonar(high)"]
  },
  {
    "id_values": {"Company Name": "Stability AI", "Website": "https://stability.ai"},
    "match_score": 0.78,
    "match_rationale": "Generative AI company, known for Stable Diffusion",
    "source_subdomain": "AI Research Companies",
    "found_by_models": ["sonar(low)"]
  },
  {
    "id_values": {"Company Name": "Scale AI", "Website": "https://scale.com"},
    "match_score": 0.75,
    "match_rationale": "AI data labeling platform, hiring data scientists",
    "source_subdomain": "AI Tools & Platforms",
    "found_by_models": ["sonar(high)"]
  },
  {
    "id_values": {"Company Name": "Adept", "Website": "https://adept.ai"},
    "match_score": 0.72,
    "match_rationale": "AI agent research company, recent funding",
    "source_subdomain": "AI Research Companies",
    "found_by_models": ["sonar(low)"]
  },
  {
    "id_values": {"Company Name": "Inflection AI", "Website": "https://inflection.ai"},
    "match_score": 0.68,
    "match_rationale": "AI assistant company, limited job listings visible",
    "source_subdomain": "AI Research Companies",
    "found_by_models": ["sonar(low)"]
  },
  {
    "id_values": {"Company Name": "Generic Consulting", "Website": "https://generic-consulting.com"},
    "match_score": 0.62,
    "match_rationale": "General consulting firm that mentions AI in blog posts",
    "source_subdomain": "General Business",
    "found_by_models": ["sonar(low)"]
  },
  {
    "id_values": {"Company Name": "AI Solutions Inc", "Website": "https://aisolutions.com"},
    "match_score": 0.58,
    "match_rationale": "Aerospace company, not AI-focused despite name",
    "source_subdomain": "General Business",
    "found_by_models": ["sonar(low)"]
  },
  {
    "id_values": {"Company Name": "TechCorp", "Website": "https://techcorp.com"},
    "match_score": 0.54,
    "match_rationale": "General tech company, minimal AI involvement",
    "source_subdomain": "General Business",
    "found_by_models": ["sonar(low)"]
  }
]
```

---

## QC Review Process

The QC layer (Claude Sonnet 4.5) reviews each row considering:
- Relevance to user requirements ("Find AI companies that are actively hiring")
- Uniqueness (not duplicate)
- Actionability (can we validate this?)
- Strategic value (good example for table)

---

## QC Output

```json
{
  "reviewed_rows": [
    {
      "id_values": {"Company Name": "Anthropic", "Website": "https://anthropic.com"},
      "row_score": 0.95,
      "qc_score": 0.98,
      "qc_rationale": "Perfect match - leading AI company with well-documented hiring activity",
      "keep": true,
      "priority_adjustment": "promote"
    },
    {
      "id_values": {"Company Name": "OpenAI", "Website": "https://openai.com"},
      "row_score": 0.92,
      "qc_score": 0.96,
      "qc_rationale": "Excellent match - major AI research org with active job postings",
      "keep": true,
      "priority_adjustment": "promote"
    },
    {
      "id_values": {"Company Name": "DeepMind", "Website": "https://deepmind.com"},
      "row_score": 0.88,
      "qc_score": 0.92,
      "qc_rationale": "Strong match - prominent AI lab with regular hiring",
      "keep": true,
      "priority_adjustment": "none"
    },
    {
      "id_values": {"Company Name": "Hugging Face", "Website": "https://huggingface.co"},
      "row_score": 0.85,
      "qc_score": 0.88,
      "qc_rationale": "Good match - rapidly growing AI platform company",
      "keep": true,
      "priority_adjustment": "promote"
    },
    {
      "id_values": {"Company Name": "Cohere", "Website": "https://cohere.ai"},
      "row_score": 0.82,
      "qc_score": 0.85,
      "qc_rationale": "Solid match - enterprise AI company with active recruitment",
      "keep": true,
      "priority_adjustment": "none"
    },
    {
      "id_values": {"Company Name": "Stability AI", "Website": "https://stability.ai"},
      "row_score": 0.78,
      "qc_score": 0.78,
      "qc_rationale": "Good match - well-known generative AI company",
      "keep": true,
      "priority_adjustment": "none"
    },
    {
      "id_values": {"Company Name": "Scale AI", "Website": "https://scale.com"},
      "row_score": 0.75,
      "qc_score": 0.74,
      "qc_rationale": "Adequate match - AI data company, verifiable hiring",
      "keep": true,
      "priority_adjustment": "none"
    },
    {
      "id_values": {"Company Name": "Adept", "Website": "https://adept.ai"},
      "row_score": 0.72,
      "qc_score": 0.72,
      "qc_rationale": "Adequate match - AI agent research startup",
      "keep": true,
      "priority_adjustment": "none"
    },
    {
      "id_values": {"Company Name": "Inflection AI", "Website": "https://inflection.ai"},
      "row_score": 0.68,
      "qc_score": 0.58,
      "qc_rationale": "Marginal match - limited hiring visibility",
      "keep": true,
      "priority_adjustment": "demote"
    },
    {
      "id_values": {"Company Name": "Generic Consulting", "Website": "https://generic-consulting.com"},
      "row_score": 0.62,
      "qc_score": 0.25,
      "qc_rationale": "Not an AI company, only tangentially mentions AI",
      "keep": false,
      "priority_adjustment": "none"
    },
    {
      "id_values": {"Company Name": "AI Solutions Inc", "Website": "https://aisolutions.com"},
      "row_score": 0.58,
      "qc_score": 0.15,
      "qc_rationale": "Misleading name - aerospace company, not AI-focused",
      "keep": false,
      "priority_adjustment": "none"
    },
    {
      "id_values": {"Company Name": "TechCorp", "Website": "https://techcorp.com"},
      "row_score": 0.54,
      "qc_score": 0.20,
      "qc_rationale": "General tech company, minimal AI involvement",
      "keep": false,
      "priority_adjustment": "none"
    }
  ],
  "rejected_rows": [
    {
      "id_values": {"Company Name": "Generic Consulting", "Website": "https://generic-consulting.com"},
      "rejection_reason": "Not an AI company, only tangentially mentions AI"
    },
    {
      "id_values": {"Company Name": "AI Solutions Inc", "Website": "https://aisolutions.com"},
      "rejection_reason": "Misleading name - aerospace company, not AI-focused"
    },
    {
      "id_values": {"Company Name": "TechCorp", "Website": "https://techcorp.com"},
      "rejection_reason": "General tech company, minimal AI involvement"
    }
  ],
  "qc_summary": {
    "total_reviewed": 12,
    "kept": 9,
    "rejected": 3,
    "promoted": 3,
    "demoted": 1,
    "reasoning": "Rejected 3 off-topic entries that aren't genuinely AI companies. Promoted 3 exceptional fits (Anthropic, OpenAI, Hugging Face) and demoted 1 marginal entry (Inflection AI) due to limited hiring visibility."
  }
}
```

---

## Final Approved Rows (after filtering)

After applying `min_qc_score: 0.5` threshold and sorting by QC score:

**9 approved rows** (sorted by qc_score descending):

1. **Anthropic** - QC: 0.98 (PROMOTED)
2. **OpenAI** - QC: 0.96 (PROMOTED)
3. **DeepMind** - QC: 0.92
4. **Hugging Face** - QC: 0.88 (PROMOTED)
5. **Cohere** - QC: 0.85
6. **Stability AI** - QC: 0.78
7. **Scale AI** - QC: 0.74
8. **Adept** - QC: 0.72
9. **Inflection AI** - QC: 0.58 (DEMOTED)

**3 rejected rows:**

- Generic Consulting (QC: 0.25) - Not an AI company
- AI Solutions Inc (QC: 0.15) - Aerospace company, misleading name
- TechCorp (QC: 0.20) - General tech company

---

## Key Benefits of QC Layer

1. **Quality-based filtering**: Removes off-topic entries that passed initial discovery
2. **Flexible row count**: Returns 9 rows (not forced to 10 or 20)
3. **Priority adjustment**: Promotes exceptional fits, demotes marginal ones
4. **Clear rationale**: Each decision has explanation for transparency
5. **No web search needed**: Uses Claude Sonnet 4.5 reasoning only

---

## Cost Tracking

Each QC review includes `enhanced_data` for cost tracking:

```json
{
  "call_description": "QC Review - Filtering and Prioritizing Rows",
  "model_used": "claude-sonnet-4-5",
  "cost": 0.0145,
  "enhanced_data": {
    "costs": {
      "actual": {
        "total_cost": 0.0145,
        "input_cost": 0.0023,
        "output_cost": 0.0122
      }
    },
    "token_usage": {
      "input_tokens": 765,
      "output_tokens": 812
    }
  }
}
```

This integrates seamlessly with the enhanced data collection system for comprehensive cost tracking across the entire pipeline.
