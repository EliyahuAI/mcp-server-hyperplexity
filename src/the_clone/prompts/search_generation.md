# Search Term Generation Prompt

Given this user query: "{prompt}"

{optimization_notes}

Generate optimal search terms and settings for the Perplexity Search API.

## Your Task

1. **Analyze the query** to understand what information is needed
2. **Generate 1-5 focused search terms** that cover different aspects
3. **Generate keyword indicators** to help identify the best results:
   - `positive_keywords`: Terms (NOT in the search queries) that indicate high-quality, relevant results
     - Include technical terms, specific methodologies, key concepts, and common abbreviations/variants
     - Example: For a neural network query, include: "backpropagation", "gradient descent", "GD", "learning rate", "LR"
   - `negative_keywords`: Terms that indicate off-topic or low-quality results
     - Include: beginner-focused phrases, unrelated topic terms, overly simplified content markers
     - Example: "for kids", "beginner tutorial", "ELI5", "simple explanation"
     - Even ONE negative keyword match suggests the result is likely irrelevant
4. **Set appropriate search settings**:
   - `max_results`: Number of results per search (1-20)
   - `search_recency_filter`: MUST be one of: "" (no filter), "day", "week", "month", "year"
     - Do NOT use year values like "2024" - use "year" or "month" instead
     - **IMPORTANT**: Only use for VERY recent events (last few days/weeks)
     - For model releases, technical docs, or anything from 2025 or earlier: use "" (no filter)

## Guidelines

- **Start broad, then narrow** - Initial searches should be inclusive to capture all available info
- Cover different topics/models, but keep queries broad enough to find announcements, docs, overviews, AND technical specs
- **Use NO recency filter ("") by default** - only add filters for breaking news or very recent events
- For architectural comparisons, technical docs, or research: ALWAYS use "" (no filter)
- **Keywords are for RESULT FILTERING, not search narrowing**:
  - Use broad search terms to cast a wide net
  - Keywords will algorithmically score and prioritize results AFTER search
  - This prevents missing good results while still prioritizing the best ones
- Provide clear reasoning for your strategy

## Important

- **Prefer broader queries over narrow ones** - "Model X information" > "Model X architecture parameters technical specifications"
- Broad queries find announcements, overviews, blogs, AND technical papers
- Overly specific queries miss relevant content
- Avoid redundant searches that would return similar results
- Let search API ranking surface the most relevant results (don't over-constrain)
