#!/usr/bin/env python3
"""
Row Discovery Orchestrator for table generation system.

Coordinates the entire row discovery pipeline:
1. Subdomain Analysis - Split search into parallel streams
2. Parallel Stream Execution - Discover rows in each subdomain concurrently
3. Consolidation - Deduplicate and prioritize final rows

This is the main entry point for independent row discovery that replaces
the old inline row generation approach.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class RowDiscovery:
    """
    Orchestrate row discovery across subdomains with integrated scoring.

    This class coordinates two sub-components:
    - RowDiscoveryStream: Discovers and scores candidates in each subdomain (integrated scoring)
    - RowConsolidator: Deduplicates and prioritizes final row list

    Subdomains are now defined in the column definition (search_strategy.subdomains),
    not via separate analysis.

    Example:
        >>> from row_discovery import RowDiscovery
        >>> discovery = RowDiscovery(ai_client, prompt_loader, schema_validator)
        >>> result = await discovery.discover_rows(
        ...     search_strategy={
        ...         "description": "Find AI companies...",
        ...         "subdomains": [
        ...             {
        ...                 "name": "AI Research",
        ...                 "focus": "Academic AI research companies",
        ...                 "search_queries": ["AI research labs", "ML institutes"],
        ...                 "target_rows": 10
        ...             }
        ...         ]
        ...     },
        ...     columns=[
        ...         {"name": "Company Name", "is_identification": True},
        ...         {"name": "Website", "is_identification": True}
        ...     ],
        ...     target_row_count=20,
        ...     max_parallel_streams=1  # Sequential for testing
        ... )
        >>> print(f"Found {len(result['final_rows'])} rows")
    """

    def __init__(
        self,
        ai_client,
        prompt_loader,
        schema_validator,
        row_discovery_stream=None,
        row_consolidator=None
    ):
        """
        Initialize row discovery orchestrator.

        Args:
            ai_client: AI API client instance
            prompt_loader: PromptLoader instance
            schema_validator: SchemaValidator instance
            row_discovery_stream: Optional pre-configured RowDiscoveryStream (for testing)
            row_consolidator: Optional pre-configured RowConsolidator (for testing)
        """
        self.ai_client = ai_client
        self.prompt_loader = prompt_loader
        self.schema_validator = schema_validator

        # Import and initialize components (lazy import to avoid circular dependencies)
        if row_discovery_stream is None:
            from .row_discovery_stream import RowDiscoveryStream
            self.row_discovery_stream_class = RowDiscoveryStream
        else:
            self.row_discovery_stream_class = row_discovery_stream

        if row_consolidator is None:
            from .row_consolidator import RowConsolidator
            self.row_consolidator = RowConsolidator()
        else:
            self.row_consolidator = row_consolidator

        logger.info("RowDiscovery orchestrator initialized")

    async def discover_rows(
        self,
        search_strategy: Dict[str, Any],
        columns: List[Dict[str, Any]],
        target_row_count: int = 20,
        discovery_multiplier: float = 1.5,
        min_match_score: float = 0.6,
        max_parallel_streams: int = 1,
        scoring_model: str = 'sonar-pro'
    ) -> Dict[str, Any]:
        """
        Discover rows using subdomains from search_strategy.

        This method orchestrates the row discovery pipeline:
        1. Extract subdomains from search_strategy (already defined in column definition)
        2. Launch discovery streams (sequential or parallel based on max_parallel_streams)
        3. Consolidate results: deduplicate, filter, sort, limit to top N

        Args:
            search_strategy: Must contain 'subdomains' array from column definition:
                - description: str - What to search for
                - subdomains: List[Dict] - Pre-defined subdomains with search queries
            columns: List of column definitions (ID + research columns)
            target_row_count: Final number of rows to return (default: 20)
            discovery_multiplier: Overshooting factor for discovery (default: 1.5)
                                  Note: Overshooting is achieved by sum of subdomain target_rows
            min_match_score: Minimum match score threshold (default: 0.6)
            max_parallel_streams: Max concurrent streams (default: 1 for sequential testing)
            scoring_model: Model for integrated scoring (default: sonar-pro)

        Returns:
            Dictionary with:
            {
                "success": bool,
                "final_rows": List[Dict] - Top N deduplicated candidates with:
                    - id_values: Dict[str, str]
                    - match_score: float (0-1)
                    - score_breakdown: {relevancy, reliability, recency}
                    - match_rationale: str
                    - source_urls: List[str]
                    - merged_from_streams: List[str]
                "stats": {
                    "subdomains_analyzed": int,
                    "parallel_streams": int,
                    "total_candidates_found": int,
                    "duplicates_removed": int,
                    "below_threshold": int,
                    "final_row_count": int
                },
                "processing_time": float (seconds),
                "error": Optional[str]
            }

        Raises:
            ValueError: If inputs are invalid
        """
        start_time = time.time()

        result = {
            "success": False,
            "final_rows": [],
            "stats": {
                "subdomains_analyzed": 0,
                "parallel_streams": 0,
                "total_candidates_found": 0,
                "duplicates_removed": 0,
                "below_threshold": 0,
                "final_row_count": 0
            },
            "processing_time": 0.0,
            "error": None
        }

        try:
            # Validate inputs
            self._validate_inputs(search_strategy, columns, target_row_count, min_match_score)

            logger.info(
                f"Starting row discovery: target={target_row_count}, "
                f"min_score={min_match_score}, max_streams={max_parallel_streams}, "
                f"scoring_model={scoring_model}"
            )

            # ================================================================
            # STEP 1: GET SUBDOMAINS FROM SEARCH_STRATEGY
            # ================================================================
            logger.info("Step 1/3: Loading subdomains from search_strategy")

            # Get subdomains from search_strategy (not separate analysis)
            subdomains = search_strategy.get('subdomains', [])

            if not subdomains:
                error_msg = "No subdomains found in search_strategy"
                logger.error(error_msg)
                result['error'] = error_msg
                result['processing_time'] = round(time.time() - start_time, 2)
                return result

            result['stats']['subdomains_analyzed'] = len(subdomains)

            logger.info(
                f"Using {len(subdomains)} subdomain(s) from column definition: "
                f"{[s.get('name', 'Unknown') for s in subdomains]}"
            )

            # Log overshooting strategy
            total_target_rows = sum(s.get('target_rows', 0) for s in subdomains)
            logger.info(
                f"Overshooting: Finding up to {total_target_rows} candidates "
                f"to select best {target_row_count}"
            )

            # ================================================================
            # STEP 2: EXECUTE STREAMS (SEQUENTIAL OR PARALLEL)
            # ================================================================
            if max_parallel_streams == 1:
                # SEQUENTIAL MODE (for initial testing)
                logger.info("Step 2/3: Processing subdomains SEQUENTIALLY (testing mode)")
                stream_results = []
                for i, subdomain in enumerate(subdomains, 1):
                    logger.info(
                        f"Processing subdomain {i}/{len(subdomains)}: {subdomain['name']} "
                        f"(target: {subdomain.get('target_rows', 7)} rows)"
                    )
                    result_item = await self._execute_single_stream(
                        subdomain,
                        columns,
                        search_strategy,
                        subdomain.get('target_rows', 7),
                        scoring_model
                    )
                    stream_results.append(result_item)
            else:
                # PARALLEL MODE (for production)
                logger.info(
                    f"Step 2/3: Processing subdomains in PARALLEL "
                    f"(max {max_parallel_streams} concurrent)"
                )

                # Limit to max_parallel_streams
                subdomains_to_process = subdomains[:max_parallel_streams]
                result['stats']['parallel_streams'] = len(subdomains_to_process)

                if len(subdomains) > max_parallel_streams:
                    logger.warning(
                        f"Limiting to {max_parallel_streams} streams "
                        f"(defined {len(subdomains)} subdomains)"
                    )

                # Execute streams in parallel
                stream_results = await self._execute_parallel_streams(
                    subdomains_to_process,
                    columns,
                    search_strategy,
                    scoring_model
                )

            result['stats']['parallel_streams'] = len(stream_results)

            # Check if ALL streams failed
            successful_streams = [s for s in stream_results if not s.get('error')]
            if len(successful_streams) == 0:
                error_msg = "All discovery streams failed - no candidates found"
                logger.error(error_msg)
                result['error'] = error_msg
                result['processing_time'] = round(time.time() - start_time, 2)
                return result

            # Log warnings for failed streams (but continue with successful ones)
            failed_streams = [s for s in stream_results if s.get('error')]
            if len(failed_streams) > 0:
                logger.warning(
                    f"{len(failed_streams)} stream(s) failed, "
                    f"continuing with {len(successful_streams)} successful stream(s)"
                )
                for failed_stream in failed_streams:
                    logger.warning(
                        f"  - {failed_stream.get('subdomain', 'Unknown')}: "
                        f"{failed_stream.get('error')}"
                    )

            # Count total candidates
            total_candidates = sum(
                len(s.get('candidates', [])) for s in successful_streams
            )
            result['stats']['total_candidates_found'] = total_candidates

            logger.info(
                f"Stream execution complete: {total_candidates} candidate(s) found "
                f"across {len(successful_streams)} stream(s)"
            )

            # ================================================================
            # STEP 3: CONSOLIDATION
            # ================================================================
            logger.info("Step 3/3: Consolidating results (deduplication + filtering + sorting)")

            consolidation_result = self.row_consolidator.consolidate(
                stream_results=successful_streams,
                target_row_count=target_row_count,
                min_match_score=min_match_score
            )

            # Extract consolidation stats
            result['stats']['duplicates_removed'] = consolidation_result['stats']['duplicates_removed']
            result['stats']['below_threshold'] = consolidation_result['stats']['below_threshold']
            result['stats']['final_row_count'] = consolidation_result['stats']['final_count']

            # Extract final rows
            result['final_rows'] = consolidation_result['final_rows']

            # Keep all candidates before filtering (for later use)
            all_candidates_before_filter = []
            for stream in successful_streams:
                all_candidates_before_filter.extend(stream.get('candidates', []))
            result['all_candidates'] = all_candidates_before_filter

            # Mark success
            result['success'] = True

            # Calculate total processing time
            result['processing_time'] = round(time.time() - start_time, 2)

            logger.info(
                f"Row discovery complete: {result['stats']['final_row_count']} final row(s) "
                f"in {result['processing_time']}s"
            )

            # Log summary statistics
            self._log_final_statistics(result['stats'])

            return result

        except ValueError as e:
            error_msg = f"Invalid input: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['processing_time'] = round(time.time() - start_time, 2)
            return result

        except Exception as e:
            error_msg = f"Row discovery failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result['error'] = error_msg
            result['processing_time'] = round(time.time() - start_time, 2)
            return result

    async def _execute_single_stream(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        target_rows: int,
        scoring_model: str
    ) -> Dict[str, Any]:
        """
        Execute a single row discovery stream.

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Overall search strategy
            target_rows: Number of rows to find for this subdomain
            scoring_model: Model for integrated scoring

        Returns:
            Stream result dictionary
        """
        # Create a new stream instance
        stream = self.row_discovery_stream_class(
            self.ai_client,
            self.prompt_loader,
            self.schema_validator
        )

        # Execute discovery with integrated scoring
        result = await stream.discover_rows(
            subdomain=subdomain,
            columns=columns,
            search_strategy=search_strategy,
            target_rows=target_rows,
            scoring_model=scoring_model
        )

        return result

    async def _execute_parallel_streams(
        self,
        subdomains: List[Dict[str, Any]],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        scoring_model: str
    ) -> List[Dict[str, Any]]:
        """
        Execute row discovery streams in parallel using asyncio.gather().

        This method launches multiple RowDiscoveryStream instances concurrently,
        one for each subdomain. If any stream fails, it continues with the others
        (graceful degradation).

        Args:
            subdomains: List of subdomain definitions
            columns: Column definitions
            search_strategy: Overall search strategy
            scoring_model: Model for integrated scoring

        Returns:
            List of stream results (may include errors for failed streams)
        """
        logger.info(f"Launching {len(subdomains)} parallel discovery stream(s)")

        # Create tasks for parallel execution
        tasks = []
        for subdomain in subdomains:
            # Create a new stream instance for each subdomain
            stream = self.row_discovery_stream_class(
                self.ai_client,
                self.prompt_loader,
                self.schema_validator
            )

            # Create async task with integrated scoring
            task = stream.discover_rows(
                subdomain=subdomain,
                columns=columns,
                search_strategy=search_strategy,
                target_rows=subdomain.get('target_rows', 7),
                scoring_model=scoring_model
            )
            tasks.append(task)

        # Execute all tasks in parallel
        # Note: asyncio.gather() returns results in order, even if some fail
        stream_results = await asyncio.gather(*tasks, return_exceptions=False)

        # Log completion
        successful = sum(1 for r in stream_results if not r.get('error'))
        logger.info(
            f"Parallel stream execution complete: {successful}/{len(stream_results)} "
            f"successful"
        )

        return stream_results

    def _validate_inputs(
        self,
        search_strategy: Dict[str, Any],
        columns: List[Dict[str, Any]],
        target_row_count: int,
        min_match_score: float
    ) -> None:
        """
        Validate input parameters.

        Args:
            search_strategy: Search strategy to validate
            columns: Column definitions to validate
            target_row_count: Target row count to validate
            min_match_score: Minimum match score to validate

        Raises:
            ValueError: If inputs are invalid
        """
        # Validate search_strategy
        if not isinstance(search_strategy, dict):
            raise ValueError(
                f"search_strategy must be a dictionary, got {type(search_strategy).__name__}"
            )

        if 'description' not in search_strategy:
            raise ValueError("search_strategy must contain 'description' field")

        # Validate columns
        if not isinstance(columns, list) or len(columns) == 0:
            raise ValueError("columns must be a non-empty list")

        # Check for at least one ID column
        id_columns = [col for col in columns if col.get('is_identification', False)]
        if len(id_columns) == 0:
            raise ValueError("At least one column must be marked as identification")

        # Validate target_row_count
        if not isinstance(target_row_count, int) or target_row_count < 1:
            raise ValueError(
                f"target_row_count must be a positive integer, got {target_row_count}"
            )

        # Validate min_match_score
        if not 0 <= min_match_score <= 1:
            raise ValueError(
                f"min_match_score must be between 0 and 1, got {min_match_score}"
            )

        logger.debug("Input validation passed")

    def _log_final_statistics(self, stats: Dict[str, Any]) -> None:
        """
        Log final statistics summary.

        Args:
            stats: Statistics dictionary
        """
        logger.info("=" * 60)
        logger.info("ROW DISCOVERY STATISTICS")
        logger.info("=" * 60)
        logger.info(f"  Subdomains analyzed:      {stats['subdomains_analyzed']}")
        logger.info(f"  Parallel streams:         {stats['parallel_streams']}")
        logger.info(f"  Total candidates found:   {stats['total_candidates_found']}")
        logger.info(f"  Duplicates removed:       {stats['duplicates_removed']}")
        logger.info(f"  Below threshold:          {stats['below_threshold']}")
        logger.info(f"  Final row count:          {stats['final_row_count']}")
        logger.info("=" * 60)

    def get_discovery_summary(self, result: Dict[str, Any]) -> str:
        """
        Generate a human-readable summary of discovery results.

        Args:
            result: Result from discover_rows() method

        Returns:
            Formatted summary string
        """
        if not result.get('success'):
            return f"Discovery failed: {result.get('error', 'Unknown error')}"

        stats = result.get('stats', {})
        final_rows = result.get('final_rows', [])

        lines = []
        lines.append("=== Row Discovery Summary ===")
        lines.append("")
        lines.append(f"Subdomains analyzed: {stats.get('subdomains_analyzed', 0)}")
        lines.append(f"Parallel streams: {stats.get('parallel_streams', 0)}")
        lines.append(f"Total candidates found: {stats.get('total_candidates_found', 0)}")
        lines.append(f"Duplicates removed: {stats.get('duplicates_removed', 0)}")
        lines.append(f"Below threshold: {stats.get('below_threshold', 0)}")
        lines.append(f"Final row count: {stats.get('final_row_count', 0)}")
        lines.append(f"Processing time: {result.get('processing_time', 0)}s")
        lines.append("")

        if final_rows:
            lines.append(f"Top 5 rows (by match score):")
            for idx, row in enumerate(final_rows[:5], 1):
                id_values = row.get('id_values', {})
                score = row.get('match_score', 0)

                # Format ID values
                id_str = ', '.join(f"{k}={v}" for k, v in id_values.items())
                lines.append(f"  {idx}. {id_str}")
                lines.append(f"     Match score: {score:.2f}")
                lines.append(f"     Rationale: {row.get('match_rationale', 'N/A')[:80]}...")

                # Show merged streams if applicable
                merged_streams = row.get('merged_from_streams', [])
                if len(merged_streams) > 1:
                    lines.append(f"     Merged from: {', '.join(merged_streams)}")
                lines.append("")

        return '\n'.join(lines)


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

async def discover_rows(
    ai_client,
    prompt_loader,
    schema_validator,
    search_strategy: Dict[str, Any],
    columns: List[Dict[str, Any]],
    target_row_count: int = 20,
    discovery_multiplier: float = 1.5,
    min_match_score: float = 0.6,
    max_parallel_streams: int = 1,
    scoring_model: str = 'sonar-pro'
) -> Dict[str, Any]:
    """
    Convenience function to discover rows without creating RowDiscovery instance.

    Args:
        ai_client: AI API client instance
        prompt_loader: PromptLoader instance
        schema_validator: SchemaValidator instance
        search_strategy: Search strategy dictionary with subdomains
        columns: Column definitions
        target_row_count: Number of final rows (default: 20)
        discovery_multiplier: Overshooting factor (default: 1.5)
        min_match_score: Minimum match score (default: 0.6)
        max_parallel_streams: Maximum concurrent streams (default: 1 for sequential)
        scoring_model: Model for integrated scoring (default: sonar-pro)

    Returns:
        Row discovery results dictionary
    """
    discovery = RowDiscovery(ai_client, prompt_loader, schema_validator)
    return await discovery.discover_rows(
        search_strategy=search_strategy,
        columns=columns,
        target_row_count=target_row_count,
        discovery_multiplier=discovery_multiplier,
        min_match_score=min_match_score,
        max_parallel_streams=max_parallel_streams,
        scoring_model=scoring_model
    )
