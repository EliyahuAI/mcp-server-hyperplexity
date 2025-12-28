#!/usr/bin/env python3
"""
Confidence Mapper: Maps the_clone p-scores to validator confidence levels.

P-Score Ranges:
- p >= 0.85 → HIGH confidence
- 0.65 <= p < 0.85 → MEDIUM confidence
- p < 0.65 → LOW confidence
"""

from typing import List, Dict


def map_p_score_to_confidence(p_score: float) -> str:
    """
    Map the_clone p-score to validator confidence level.

    Args:
        p_score: Quality score from the_clone (0.0-1.0)

    Returns:
        "HIGH", "MEDIUM", or "LOW"
    """
    if p_score >= 0.85:
        return "HIGH"
    elif p_score >= 0.65:
        return "MEDIUM"
    else:
        return "LOW"


def get_highest_confidence_from_snippets(snippets: List[Dict]) -> str:
    """
    Get the highest confidence level from a list of snippets.

    For a cell value supported by multiple snippets,
    use the highest confidence level among them.

    Args:
        snippets: List of snippet dictionaries with 'p' scores

    Returns:
        "HIGH", "MEDIUM", or "LOW"
    """
    if not snippets:
        return "LOW"

    max_p = max(s.get('p', 0.0) for s in snippets)
    return map_p_score_to_confidence(max_p)


def get_average_confidence_from_snippets(snippets: List[Dict]) -> str:
    """
    Get average confidence level from snippets (alternative to highest).

    Args:
        snippets: List of snippet dictionaries with 'p' scores

    Returns:
        "HIGH", "MEDIUM", or "LOW"
    """
    if not snippets:
        return "LOW"

    avg_p = sum(s.get('p', 0.0) for s in snippets) / len(snippets)
    return map_p_score_to_confidence(avg_p)
