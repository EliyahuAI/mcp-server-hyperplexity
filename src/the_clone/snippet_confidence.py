#!/usr/bin/env python3
"""
Snippet-based confidence assessment.

Assesses whether extracted snippets are sufficient to answer each search term.
More accurate than preview-based verification (judges actual quotes, not summaries).
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


async def assess_snippet_confidence(
    snippets: List[Dict[str, Any]],
    search_terms: List[str],
    breadth: str = "narrow",
    depth: str = "shallow",
    ai_client = None
) -> Dict[str, Any]:
    """
    Assess confidence based on extracted snippets (not previews).

    More accurate than preview-based verification because it judges
    actual extracted quotes rather than predicting from summaries.

    Args:
        snippets: Extracted snippets from memory sources
        search_terms: List of search terms to assess
        breadth: Query breadth (narrow/broad)
        depth: Query depth (shallow/deep)
        ai_client: AIAPIClient instance

    Returns:
        {
            'confidence_vector': [float, ...],  # Per-term confidence
            'overall_confidence': float,        # Mean of vector
            'snippet_counts': [int, ...],       # Snippets per term
            'recommended_searches': [str, ...]  # Terms needing search
        }
    """
    num_terms = len(search_terms)

    # Fast path: 0 snippets = 0 confidence
    if len(snippets) == 0:
        return {
            'confidence_vector': [0.0] * num_terms,
            'overall_confidence': 0.0,
            'snippet_counts': [0] * num_terms,
            'recommended_searches': search_terms[:]
        }

    # Heuristic assessment (fast, no AI call)
    # Count snippets per search term
    snippet_counts = []
    for i, term in enumerate(search_terms):
        # Search term index is 1-indexed in snippet metadata
        count = sum(1 for s in snippets if s.get('search_ref') == i + 1)
        snippet_counts.append(count)

    # Calculate quality score
    high_quality = sum(1 for s in snippets if s.get('p', 0) >= 0.85)
    avg_quality = sum(s.get('p', 0.5) for s in snippets) / len(snippets)

    # Heuristic confidence per term
    confidence_vector = []
    for count in snippet_counts:
        if count >= 5 and avg_quality >= 0.8:
            conf = 0.90  # Excellent coverage
        elif count >= 3 and avg_quality >= 0.7:
            conf = 0.80  # Good coverage
        elif count >= 1 and avg_quality >= 0.6:
            conf = 0.60  # Partial coverage
        elif count >= 1:
            conf = 0.40  # Weak coverage
        else:
            conf = 0.0   # No coverage
        confidence_vector.append(conf)

    overall_confidence = sum(confidence_vector) / len(confidence_vector) if confidence_vector else 0.0

    # Determine which terms need search (confidence < 0.85)
    recommended_searches = [
        term for i, term in enumerate(search_terms)
        if confidence_vector[i] < 0.85
    ]

    logger.debug(
        f"[SNIPPET_CONFIDENCE] Assessed {len(snippets)} snippets: "
        f"counts={snippet_counts}, conf={confidence_vector}, "
        f"overall={overall_confidence:.2f}, quality={avg_quality:.2f}"
    )

    # Optional: If AI client provided and confidence is borderline (0.5-0.8),
    # do a quick Gemini check for refinement
    if ai_client and 0.5 <= overall_confidence <= 0.8:
        logger.debug("[SNIPPET_CONFIDENCE] Borderline confidence, using Gemini for refinement")
        try:
            refined = await _gemini_refine_assessment(
                snippets=snippets,
                search_terms=search_terms,
                heuristic_confidence=confidence_vector,
                breadth=breadth,
                depth=depth,
                ai_client=ai_client
            )
            if refined:
                return refined
        except Exception as e:
            logger.warning(f"[SNIPPET_CONFIDENCE] Gemini refinement failed, using heuristic: {e}")

    return {
        'confidence_vector': confidence_vector,
        'overall_confidence': overall_confidence,
        'snippet_counts': snippet_counts,
        'recommended_searches': recommended_searches
    }


async def _gemini_refine_assessment(
    snippets: List[Dict[str, Any]],
    search_terms: List[str],
    heuristic_confidence: List[float],
    breadth: str,
    depth: str,
    ai_client
) -> Optional[Dict[str, Any]]:
    """
    Use Gemini to refine borderline confidence assessments.

    Only called when heuristic confidence is borderline (0.5-0.8).
    Provides quick check on actual extracted quotes.
    """
    # Format snippets for Gemini
    snippet_text = []
    for i, snippet in enumerate(snippets[:20], 1):  # Max 20 snippets
        text = snippet.get('text', '')[:300]
        p = snippet.get('p', 0.5)
        snippet_text.append(f"[{i}] (p={p:.2f}) {text}...")

    # Format search terms with heuristic confidence
    term_list = []
    for i, term in enumerate(search_terms):
        h_conf = heuristic_confidence[i]
        count = sum(1 for s in snippets if s.get('search_ref') == i + 1)
        term_list.append(f'{i}. "{term}" (heuristic: {h_conf:.2f}, {count} snippets)')

    prompt = f"""# Snippet Sufficiency Assessment

**Query breadth:** {breadth}
**Query depth:** {depth}

**Search Terms ({len(search_terms)} total):**
{chr(10).join(term_list)}

**Extracted Snippets ({len(snippets)} total):**
{chr(10).join(snippet_text)}

**Task:** For each search term, assess: "Can I write a {'comprehensive' if breadth == 'broad' else 'focused'} {'detailed' if depth == 'deep' else 'concise'} answer using ONLY these snippets?"

Return JSON with confidence_vector (length={len(search_terms)}):
- 0.9+: Yes, sufficient snippets
- 0.7-0.9: Mostly sufficient
- 0.5-0.7: Partially sufficient
- <0.5: Insufficient

```json
{{
  "confidence_vector": [0.85, 0.60, 0.90],
  "reasoning": "Brief explanation"
}}
```
"""

    schema = {
        "type": "object",
        "properties": {
            "confidence_vector": {
                "type": "array",
                "items": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "description": f"Confidence per term, length={len(search_terms)}"
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of assessment"
            }
        },
        "required": ["confidence_vector"]
    }

    try:
        response = await ai_client.call_structured_api(
            prompt=prompt,
            schema=schema,
            model="gemini-2.5-flash-lite",
            use_cache=False,
            context="snippet_confidence_assessment",
            soft_schema=True
        )

        from shared.ai_client.utils import extract_structured_response
        data = extract_structured_response(response.get('response', response))

        conf_vector = data.get('confidence_vector', heuristic_confidence)
        # Pad if needed
        while len(conf_vector) < len(search_terms):
            conf_vector.append(0.0)

        overall = sum(conf_vector) / len(conf_vector) if conf_vector else 0.0
        recommended = [term for i, term in enumerate(search_terms) if conf_vector[i] < 0.85]

        logger.debug(f"[SNIPPET_CONFIDENCE] Gemini refined: {heuristic_confidence} → {conf_vector}")

        return {
            'confidence_vector': conf_vector,
            'overall_confidence': overall,
            'snippet_counts': [sum(1 for s in snippets if s.get('search_ref') == i + 1) for i in range(len(search_terms))],
            'recommended_searches': recommended
        }

    except Exception as e:
        logger.error(f"[SNIPPET_CONFIDENCE] Gemini refinement error: {e}")
        return None
