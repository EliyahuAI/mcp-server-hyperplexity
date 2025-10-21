#!/usr/bin/env python3
"""
Row Consolidator for table generation system.

Takes candidates from multiple parallel streams, deduplicates them using fuzzy matching,
and returns a prioritized list of the best rows.
"""

import logging
import time
from typing import Dict, Any, List, Optional
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class RowConsolidator:
    """
    Consolidate row candidates from multiple parallel discovery streams.

    Features:
    - Fuzzy matching on ID columns to detect similar entities
    - Deduplication with configurable similarity threshold
    - Merge source URLs and metadata from duplicates
    - Filter by minimum match score
    - Sort by match score descending
    - Limit to top N candidates

    Example:
        >>> consolidator = RowConsolidator()
        >>> stream_results = [
        ...     {
        ...         "subdomain": "AI Research Companies",
        ...         "candidates": [
        ...             {
        ...                 "id_values": {"Company Name": "Anthropic"},
        ...                 "match_score": 0.95,
        ...                 "match_rationale": "Leading AI safety research...",
        ...                 "source_urls": ["https://anthropic.com/careers"]
        ...             }
        ...         ]
        ...     },
        ...     {
        ...         "subdomain": "Healthcare AI",
        ...         "candidates": [
        ...             {
        ...                 "id_values": {"Company Name": "Anthropic Inc"},
        ...                 "match_score": 0.88,
        ...                 "match_rationale": "AI research company...",
        ...                 "source_urls": ["https://anthropic.com/about"]
        ...             }
        ...         ]
        ...     }
        ... ]
        >>> result = consolidator.consolidate(stream_results, target_row_count=20)
        >>> print(f"Final count: {result['stats']['final_count']}")
    """

    def __init__(self, fuzzy_similarity_threshold: float = 0.85):
        """
        Initialize row consolidator.

        Args:
            fuzzy_similarity_threshold: Threshold for fuzzy matching (0-1).
                Default 0.85 catches most variations while avoiding false positives.
                Examples:
                - "Anthropic" vs "Anthropic Inc" → 0.89 (match)
                - "Anthropic" vs "Anthropic PBC" → 0.89 (match)
                - "OpenAI" vs "Open AI" → 0.93 (match)
                - "Google" vs "Microsoft" → 0.0 (no match)
        """
        if not 0 <= fuzzy_similarity_threshold <= 1:
            raise ValueError("fuzzy_similarity_threshold must be between 0 and 1")

        self.fuzzy_similarity_threshold = fuzzy_similarity_threshold
        logger.info(
            f"RowConsolidator initialized with fuzzy threshold: {fuzzy_similarity_threshold}"
        )

    def consolidate(
        self,
        stream_results: List[Dict[str, Any]],
        target_row_count: int = 20,
        min_match_score: float = 0.6,
        id_columns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Consolidate candidates from multiple streams into a prioritized final list.

        Process:
        1. Collect all candidates from all streams
        2. Fuzzy match on ID columns to find duplicates
        3. Merge duplicates (keep highest score, combine sources)
        4. Filter by min_match_score
        5. Sort by match_score descending
        6. Take top N (target_row_count)

        Args:
            stream_results: List of results from parallel discovery streams. Each contains:
                - subdomain: str (name of subdomain)
                - candidates: List[Dict] with id_values, match_score, match_rationale, source_urls
            target_row_count: Maximum number of rows to return (default: 20)
            min_match_score: Minimum match score to include (default: 0.6)
            id_columns: List of ID column names to use for fuzzy matching.
                If None, automatically detected from first candidate.

        Returns:
            Dictionary with:
            {
                "final_rows": List[Dict] - Top N deduplicated and filtered candidates
                "stats": {
                    "total_candidates": int - Total from all streams
                    "duplicates_removed": int - Number of duplicates merged
                    "below_threshold": int - Candidates filtered by min_match_score
                    "final_count": int - Number in final_rows
                },
                "processing_time": float - Time in seconds
            }

        Raises:
            ValueError: If stream_results is invalid or empty
            Exception: If consolidation process fails
        """
        start_time = time.time()

        result = {
            "final_rows": [],
            "stats": {
                "total_candidates": 0,
                "duplicates_removed": 0,
                "below_threshold": 0,
                "final_count": 0
            },
            "processing_time": 0.0
        }

        try:
            # Validate inputs
            self._validate_inputs(stream_results, target_row_count, min_match_score)

            # Step 1: Collect all candidates
            all_candidates = self._collect_candidates(stream_results)
            total_count = len(all_candidates)
            result["stats"]["total_candidates"] = total_count

            if total_count == 0:
                logger.warning("No candidates to consolidate")
                result["processing_time"] = round(time.time() - start_time, 3)
                return result

            logger.info(f"Consolidating {total_count} candidates from {len(stream_results)} stream(s)")

            # Step 1.5: Recalculate scores from breakdown (fix sonar-pro incorrect calculations)
            self._recalculate_scores(all_candidates)

            # Auto-detect ID columns if not provided
            if id_columns is None:
                id_columns = self._detect_id_columns(all_candidates)
                logger.debug(f"Auto-detected ID columns: {id_columns}")

            # Step 2: Deduplicate using fuzzy matching
            deduplicated = self._deduplicate_candidates(all_candidates, id_columns)
            duplicates_removed = total_count - len(deduplicated)
            result["stats"]["duplicates_removed"] = duplicates_removed

            logger.info(
                f"Deduplication complete: {len(deduplicated)} unique candidates "
                f"({duplicates_removed} duplicates merged)"
            )

            # Step 3: Filter by minimum match score
            filtered = self._filter_by_score(deduplicated, min_match_score)
            below_threshold = len(deduplicated) - len(filtered)
            result["stats"]["below_threshold"] = below_threshold

            if below_threshold > 0:
                logger.info(
                    f"Filtered out {below_threshold} candidate(s) below threshold {min_match_score}"
                )

            # Step 4: Sort by match score descending
            sorted_candidates = self._sort_by_score(filtered)

            # Step 5: Limit to top N
            final_rows = sorted_candidates[:target_row_count]
            result["stats"]["final_count"] = len(final_rows)
            result["final_rows"] = final_rows

            # Calculate processing time
            processing_time = time.time() - start_time
            result["processing_time"] = round(processing_time, 3)

            logger.info(
                f"Consolidation complete: {len(final_rows)} final row(s) "
                f"in {result['processing_time']}s"
            )

            # Log final statistics
            self._log_statistics(result["stats"])

            return result

        except Exception as e:
            logger.error(f"Error during consolidation: {e}")
            result["processing_time"] = round(time.time() - start_time, 3)
            raise

    def _validate_inputs(
        self,
        stream_results: List[Dict[str, Any]],
        target_row_count: int,
        min_match_score: float
    ) -> None:
        """
        Validate consolidation inputs.

        Args:
            stream_results: Stream results to validate
            target_row_count: Target row count to validate
            min_match_score: Minimum match score to validate

        Raises:
            ValueError: If inputs are invalid
        """
        if not isinstance(stream_results, list):
            raise ValueError(
                f"stream_results must be a list, got {type(stream_results).__name__}"
            )

        if target_row_count < 1:
            raise ValueError(f"target_row_count must be >= 1, got {target_row_count}")

        if not 0 <= min_match_score <= 1:
            raise ValueError(
                f"min_match_score must be between 0 and 1, got {min_match_score}"
            )

        logger.debug("Input validation passed")

    def _collect_candidates(self, stream_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Collect all candidates from all streams and tag with source subdomain.

        Args:
            stream_results: List of stream result dictionaries

        Returns:
            List of all candidates with source_subdomain added
        """
        all_candidates = []

        for stream_result in stream_results:
            subdomain_name = stream_result.get('subdomain', 'Unknown')
            candidates = stream_result.get('candidates', [])

            # Tag each candidate with its source subdomain
            for candidate in candidates:
                # Make a copy to avoid mutating original
                candidate_copy = candidate.copy()
                candidate_copy['source_subdomain'] = subdomain_name
                all_candidates.append(candidate_copy)

        return all_candidates

    def _recalculate_scores(self, candidates: List[Dict[str, Any]]) -> None:
        """
        Recalculate match scores from score_breakdown using correct formula.

        sonar-pro sometimes returns incorrect final scores. This method recalculates
        the match_score using the formula: (Relevancy × 0.4) + (Reliability × 0.3) + (Recency × 0.3)

        Modifies candidates in-place.

        Args:
            candidates: List of candidates with score_breakdown
        """
        recalculated_count = 0

        for candidate in candidates:
            score_breakdown = candidate.get('score_breakdown', {})

            if score_breakdown:
                relevancy = score_breakdown.get('relevancy', 0)
                reliability = score_breakdown.get('reliability', 0)
                recency = score_breakdown.get('recency', 0)

                # Calculate correct score
                calculated_score = (relevancy * 0.4) + (reliability * 0.3) + (recency * 0.3)

                # Update if different from reported score
                reported_score = candidate.get('match_score', 0)
                if abs(calculated_score - reported_score) > 0.01:
                    logger.debug(
                        f"Score correction: {reported_score:.2f} → {calculated_score:.2f} "
                        f"(R={relevancy:.2f}, Rl={reliability:.2f}, Rc={recency:.2f})"
                    )
                    candidate['match_score'] = calculated_score
                    recalculated_count += 1

        if recalculated_count > 0:
            logger.info(f"Recalculated {recalculated_count} incorrect score(s)")

    def _detect_id_columns(self, candidates: List[Dict[str, Any]]) -> List[str]:
        """
        Auto-detect ID column names from first candidate.

        Args:
            candidates: List of candidate dictionaries

        Returns:
            List of ID column names
        """
        if not candidates:
            return []

        first_candidate = candidates[0]
        id_values = first_candidate.get('id_values', {})

        return list(id_values.keys())

    def _deduplicate_candidates(
        self,
        candidates: List[Dict[str, Any]],
        id_columns: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate candidates using fuzzy matching on ID columns.

        When duplicates are found:
        - Keep the candidate with the highest match_score
        - Merge source_urls from all duplicates
        - Track which subdomains contributed (merged_from_streams)

        Args:
            candidates: List of candidate dictionaries
            id_columns: List of ID column names to match on

        Returns:
            List of deduplicated candidates
        """
        if not candidates or not id_columns:
            return candidates

        # Group candidates by fuzzy matching
        groups: List[List[Dict[str, Any]]] = []

        for candidate in candidates:
            # Try to find an existing group this candidate matches
            matched_group = None

            for group in groups:
                # Compare with first member of group (representative)
                if self._are_duplicates(candidate, group[0], id_columns):
                    matched_group = group
                    break

            if matched_group is not None:
                # Add to existing group
                matched_group.append(candidate)
            else:
                # Create new group
                groups.append([candidate])

        logger.debug(f"Fuzzy matching created {len(groups)} unique group(s) from {len(candidates)} candidates")

        # Merge each group into a single candidate
        deduplicated = []
        for group in groups:
            merged = self._merge_group(group)
            deduplicated.append(merged)

        return deduplicated

    def _are_duplicates(
        self,
        candidate1: Dict[str, Any],
        candidate2: Dict[str, Any],
        id_columns: List[str]
    ) -> bool:
        """
        Check if two candidates are duplicates using fuzzy matching.

        Two candidates are considered duplicates if ALL ID columns match
        with similarity >= fuzzy_similarity_threshold.

        Args:
            candidate1: First candidate
            candidate2: Second candidate
            id_columns: List of ID column names to compare

        Returns:
            True if candidates are duplicates, False otherwise
        """
        id_values1 = candidate1.get('id_values', {})
        id_values2 = candidate2.get('id_values', {})

        # All ID columns must match
        for col_name in id_columns:
            value1 = str(id_values1.get(col_name, '')).strip()
            value2 = str(id_values2.get(col_name, '')).strip()

            # Check fuzzy similarity
            similarity = self._calculate_similarity(value1, value2)

            if similarity < self.fuzzy_similarity_threshold:
                # At least one ID column doesn't match - not duplicates
                return False

        # All ID columns matched
        return True

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity between two strings using enhanced fuzzy matching.

        This is case-insensitive and handles common variations like:
        - "Anthropic" vs "Anthropic Inc" → 0.91+ (after suffix removal)
        - "OpenAI" vs "Open AI" → 0.93
        - "Google LLC" vs "Google" → 0.91+ (after suffix removal)

        Strategy:
        1. Normalize strings (lowercase, strip)
        2. Remove common business suffixes (Inc, LLC, Corp, etc.)
        3. Calculate similarity using SequenceMatcher
        4. Boost score if one is a prefix of the other

        Args:
            str1: First string
            str2: Second string

        Returns:
            Similarity ratio between 0 and 1
        """
        # Normalize: lowercase and strip whitespace
        s1 = str1.lower().strip()
        s2 = str2.lower().strip()

        # Handle empty strings
        if not s1 or not s2:
            return 1.0 if s1 == s2 else 0.0

        # Remove common business suffixes to improve matching
        # This helps "Anthropic" match "Anthropic Inc"
        suffixes = [
            ' inc.', ' inc', ' incorporated',
            ' llc', ' l.l.c.', ' l.l.c',
            ' ltd', ' ltd.', ' limited',
            ' corp', ' corp.', ' corporation',
            ' co', ' co.', ' company',
            ' pbc', ' p.b.c.', ' public benefit corporation',
            ' plc', ' p.l.c.',
            ',', '.'
        ]

        # Clean both strings
        s1_clean = s1
        s2_clean = s2
        for suffix in suffixes:
            if s1_clean.endswith(suffix):
                s1_clean = s1_clean[:-len(suffix)].strip()
            if s2_clean.endswith(suffix):
                s2_clean = s2_clean[:-len(suffix)].strip()

        # Calculate base similarity on cleaned strings
        base_similarity = SequenceMatcher(None, s1_clean, s2_clean).ratio()

        # Boost similarity if one is a prefix of the other (handles "OpenAI" vs "Open AI")
        # Check if cleaned strings are very similar in length-normalized form
        if s1_clean and s2_clean:
            # Check prefix match
            shorter = min(s1_clean, s2_clean, key=len)
            longer = max(s1_clean, s2_clean, key=len)

            if longer.startswith(shorter) or shorter.startswith(longer):
                # One is a prefix - likely the same entity
                prefix_similarity = len(shorter) / len(longer)
                base_similarity = max(base_similarity, prefix_similarity)

        return base_similarity

    def _merge_group(self, group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge a group of duplicate candidates into a single candidate.

        Strategy:
        - Keep candidate with highest match_score
        - Merge all source_urls (deduplicated)
        - Track which subdomains contributed

        Args:
            group: List of duplicate candidates to merge

        Returns:
            Single merged candidate
        """
        if len(group) == 1:
            # No merging needed - add metadata
            merged = group[0].copy()
            merged['merged_from_streams'] = [merged.get('source_subdomain', 'Unknown')]
            return merged

        # Sort by match_score descending
        sorted_group = sorted(group, key=lambda c: c.get('match_score', 0), reverse=True)

        # Start with highest-scored candidate
        best_candidate = sorted_group[0].copy()

        # Collect all source URLs
        all_urls = set()
        for candidate in group:
            urls = candidate.get('source_urls', [])
            all_urls.update(urls)

        # Collect all source subdomains
        all_subdomains = set()
        for candidate in group:
            subdomain = candidate.get('source_subdomain', 'Unknown')
            all_subdomains.add(subdomain)

        # Update merged candidate
        best_candidate['source_urls'] = sorted(list(all_urls))
        best_candidate['merged_from_streams'] = sorted(list(all_subdomains))

        logger.debug(
            f"Merged {len(group)} duplicate(s) for "
            f"'{best_candidate.get('id_values', {})}' "
            f"from streams: {best_candidate['merged_from_streams']}"
        )

        return best_candidate

    def _filter_by_score(
        self,
        candidates: List[Dict[str, Any]],
        min_match_score: float
    ) -> List[Dict[str, Any]]:
        """
        Filter candidates by minimum match score.

        Args:
            candidates: List of candidates
            min_match_score: Minimum score threshold

        Returns:
            Filtered list of candidates
        """
        return [
            c for c in candidates
            if c.get('match_score', 0) >= min_match_score
        ]

    def _sort_by_score(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort candidates by match_score descending.

        Args:
            candidates: List of candidates

        Returns:
            Sorted list (highest scores first)
        """
        return sorted(
            candidates,
            key=lambda c: c.get('match_score', 0),
            reverse=True
        )

    def _log_statistics(self, stats: Dict[str, Any]) -> None:
        """
        Log consolidation statistics.

        Args:
            stats: Statistics dictionary
        """
        logger.info(
            f"Consolidation stats - Total: {stats['total_candidates']}, "
            f"Duplicates: {stats['duplicates_removed']}, "
            f"Below threshold: {stats['below_threshold']}, "
            f"Final: {stats['final_count']}"
        )

    def get_consolidation_summary(self, result: Dict[str, Any]) -> str:
        """
        Generate a human-readable summary of consolidation results.

        Args:
            result: Result from consolidate() method

        Returns:
            Formatted summary string
        """
        stats = result.get('stats', {})
        final_rows = result.get('final_rows', [])

        lines = []
        lines.append("=== Row Consolidation Summary ===")
        lines.append("")
        lines.append(f"Total candidates collected: {stats.get('total_candidates', 0)}")
        lines.append(f"Duplicates merged: {stats.get('duplicates_removed', 0)}")
        lines.append(f"Below score threshold: {stats.get('below_threshold', 0)}")
        lines.append(f"Final row count: {stats.get('final_count', 0)}")
        lines.append(f"Processing time: {result.get('processing_time', 0):.3f}s")
        lines.append("")

        if final_rows:
            lines.append("Top 5 candidates:")
            for idx, row in enumerate(final_rows[:5], 1):
                id_values = row.get('id_values', {})
                score = row.get('match_score', 0)
                streams = row.get('merged_from_streams', [])

                # Format ID values
                id_str = ', '.join(f"{k}={v}" for k, v in id_values.items())
                lines.append(f"  {idx}. {id_str}")
                lines.append(f"     Score: {score:.2f}")
                if len(streams) > 1:
                    lines.append(f"     Merged from: {', '.join(streams)}")
                lines.append("")

        return '\n'.join(lines)
