#!/usr/bin/env python3
"""
Relevance Scoring Module for Search Results.
Scores search results based on ranking position and keyword matches.
"""

import logging
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RelevanceScorer:
    """
    Scores search results based on:
    1. Base rank score (position in search results)
    2. Keyword adjustments (positive and negative keywords)
    """

    def __init__(
        self,
        positive_weight: float = 1.0,
        negative_weight: float = 5.0
    ):
        """
        Initialize the relevance scorer.

        Args:
            positive_weight: Points added per positive keyword match (default: 1.0)
            negative_weight: Points subtracted per negative keyword match (default: 5.0)
        """
        self.positive_weight = positive_weight
        self.negative_weight = negative_weight

    def score_search_results(
        self,
        results: List[Dict[str, Any]],
        positive_keywords: List[str],
        negative_keywords: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Score all search results based on rank and keywords.

        Args:
            results: List of search result dicts with 'title', 'snippet', etc.
            positive_keywords: Keywords that indicate relevant, high-quality results
            negative_keywords: Keywords that indicate irrelevant, low-quality results

        Returns:
            Same list of results with added 'relevance_score' and 'keyword_matches' fields
        """
        if not results:
            return results

        max_results = len(results)

        # Score each result
        scored_results = []
        for rank, result in enumerate(results):
            # Base score from rank (inverse - lower rank number = higher score)
            # Rank 0 gets score max_results, rank 1 gets max_results-1, etc.
            base_score = max_results - rank

            # Count keyword matches in title + snippet
            text = self._get_searchable_text(result)
            pos_matches, neg_matches = self._count_keyword_matches(
                text, positive_keywords, negative_keywords
            )

            # Calculate keyword adjustment
            keyword_adjustment = (
                (pos_matches * self.positive_weight) -
                (neg_matches * self.negative_weight)
            )

            # Final relevance score
            relevance_score = base_score + keyword_adjustment

            # Add score and metadata to result
            result_copy = result.copy()
            result_copy['relevance_score'] = relevance_score
            result_copy['base_rank_score'] = base_score
            result_copy['keyword_adjustment'] = keyword_adjustment
            result_copy['keyword_matches'] = {
                'positive': pos_matches,
                'negative': neg_matches,
                'positive_keywords_found': self._find_matching_keywords(text, positive_keywords),
                'negative_keywords_found': self._find_matching_keywords(text, negative_keywords)
            }
            result_copy['original_rank'] = rank

            scored_results.append(result_copy)

        return scored_results

    def _get_searchable_text(self, result: Dict[str, Any]) -> str:
        """
        Extract searchable text from result (title + snippet).

        Args:
            result: Search result dict

        Returns:
            Lowercase combined text for keyword matching
        """
        title = result.get('title', '')
        snippet = result.get('snippet', '')
        return f"{title} {snippet}".lower()

    def _count_keyword_matches(
        self,
        text: str,
        positive_keywords: List[str],
        negative_keywords: List[str]
    ) -> tuple:
        """
        Count positive and negative keyword matches in text.

        Args:
            text: Lowercase text to search
            positive_keywords: List of positive keywords
            negative_keywords: List of negative keywords

        Returns:
            Tuple of (positive_count, negative_count)
        """
        text_lower = text.lower()

        pos_count = sum(
            1 for keyword in positive_keywords
            if keyword.lower() in text_lower
        )

        neg_count = sum(
            1 for keyword in negative_keywords
            if keyword.lower() in text_lower
        )

        return pos_count, neg_count

    def _find_matching_keywords(
        self,
        text: str,
        keywords: List[str]
    ) -> List[str]:
        """
        Find which keywords matched in the text.

        Args:
            text: Lowercase text to search
            keywords: List of keywords to look for

        Returns:
            List of matched keywords
        """
        text_lower = text.lower()
        return [
            keyword for keyword in keywords
            if keyword.lower() in text_lower
        ]

    def get_reranked_indices(
        self,
        scored_results: List[Dict[str, Any]]
    ) -> List[int]:
        """
        Get original indices of results sorted by relevance score.

        Args:
            scored_results: Results with relevance_score field

        Returns:
            List of original indices sorted by score (highest first)
        """
        # Sort by relevance score (descending)
        sorted_results = sorted(
            scored_results,
            key=lambda x: x['relevance_score'],
            reverse=True
        )

        # Return original indices
        return [r['original_rank'] for r in sorted_results]

    def format_scores_for_triage(
        self,
        scored_results: List[Dict[str, Any]]
    ) -> str:
        """
        Format scoring information for triage prompt.

        Args:
            scored_results: Results with relevance scores

        Returns:
            Formatted string with score breakdown
        """
        lines = []
        lines.append("Relevance Scores (Rank + Keyword Analysis):")
        lines.append("=" * 60)

        for result in scored_results:
            rank = result['original_rank']
            score = result['relevance_score']
            base = result['base_rank_score']
            adj = result['keyword_adjustment']
            km = result['keyword_matches']

            lines.append(f"[{rank}] Score: {score:.1f} (base: {base}, keywords: {adj:+.1f})")

            if km['positive'] > 0:
                pos_kw = ', '.join(km['positive_keywords_found'][:3])
                if len(km['positive_keywords_found']) > 3:
                    pos_kw += f" (+{len(km['positive_keywords_found']) - 3} more)"
                lines.append(f"    [+] Positive matches ({km['positive']}): {pos_kw}")

            if km['negative'] > 0:
                neg_kw = ', '.join(km['negative_keywords_found'])
                lines.append(f"    [-] NEGATIVE matches ({km['negative']}): {neg_kw}")

        return '\n'.join(lines)
