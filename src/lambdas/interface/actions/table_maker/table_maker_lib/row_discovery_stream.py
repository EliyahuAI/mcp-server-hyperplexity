#!/usr/bin/env python3
"""
Row Discovery Stream for table maker.

Discovers and scores candidate rows for a SINGLE subdomain by:
1. Executing web searches for the subdomain
2. Extracting candidate entities from search results
3. Scoring each candidate against table criteria
4. Returning scored candidates with rationale
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _is_separator_line(line: str) -> bool:
    """
    Check if a markdown table line is a separator (e.g., |---|---|---|).
    Only returns True if the line contains ONLY pipes, dashes, colons, and whitespace.
    Prevents data rows containing '---' (e.g., 'Phase III---Approved') from
    being misidentified as separators.
    """
    import re
    cleaned = re.sub(r'[\|\-\:\s]', '', line)
    return len(cleaned) == 0 and '---' in line


def _filter_numeric_citations(citations: Dict[str, str]) -> Dict[str, str]:
    """
    Filter citations to only include numeric keys.

    Some models (e.g., the-clone) may return citations with non-standard keys like 'S1.1.2.0'.
    This function filters to only keep valid integer keys.

    Args:
        citations: Dictionary with citation keys and URL values

    Returns:
        Dictionary with only numeric keys
    """
    if not citations:
        return {}

    numeric_citations = {}
    non_numeric_keys = []

    for key, value in citations.items():
        if key.isdigit():
            numeric_citations[key] = value
        else:
            non_numeric_keys.append(key)

    if non_numeric_keys:
        logger.warning(f"[CITATION] Filtered out {len(non_numeric_keys)} non-numeric citation keys: {non_numeric_keys[:5]}{'...' if len(non_numeric_keys) > 5 else ''}")

    return numeric_citations


def _get_max_citation_number(citations: Dict[str, str]) -> int:
    """
    Get the maximum citation number from a citations dictionary.

    Args:
        citations: Dictionary with citation keys and URL values

    Returns:
        Maximum citation number, or 0 if no valid numeric citations
    """
    numeric_citations = _filter_numeric_citations(citations)
    if not numeric_citations:
        return 0
    return max(int(k) for k in numeric_citations.keys())


def parse_candidates_markdown(
    markdown_str: str,
    columns: List[Dict[str, Any]],
    citations: Dict[str, str] = None,
    scoring: List[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Parse a markdown table of candidates with ALL columns (ID + RESEARCH + SCORING) and inline citations.

    Expected markdown format (unified format with scoring columns):
    | Company Name | CEO Name | Rel | Src | Rec | Rationale |
    |---|---|---|---|---|---|
    | Anthropic[1] | Dario Amodei[2] | 0.95 | 1.0 | 0.9 | Leading AI safety co |

    Args:
        markdown_str: Markdown table string with inline citations [n]
        columns: Full column definitions (ID + RESEARCH columns)
        citations: Map of citation numbers to URLs (e.g., {"1": "https://..."})
        scoring: DEPRECATED - scoring now extracted from table columns (kept for backward compat)

    Returns:
        List of candidate dictionaries with id_values, research_values, cell_citations, etc.
    """
    import re

    if not markdown_str or not isinstance(markdown_str, str):
        return []

    citations = citations or {}

    # Scoring column names (case-insensitive matching)
    SCORING_COLUMNS = {'rel', 'src', 'rec', 'rationale', 'relevancy', 'reliability', 'recency'}

    candidates = []
    lines = markdown_str.strip().split('\n')

    # Find header line (first line with |)
    header_line = None
    header_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith('|') and '---' not in line:
            header_line = line
            header_idx = i
            break

    if not header_line:
        logger.warning("[PARSE_MD] No header line found in candidates markdown")
        return []

    # Parse header to get column names
    headers = [h.strip() for h in header_line.split('|') if h.strip()]
    logger.info(f"[PARSE_MD] Found headers: {headers}")

    # Identify ID vs RESEARCH columns (exclude scoring columns)
    id_column_names = set()
    research_column_names = set()
    for col in columns:
        col_name = col.get('name', '')
        if col.get('importance', '').upper() == 'ID' or col.get('is_identification'):
            id_column_names.add(col_name)
        else:
            research_column_names.add(col_name)

    # Identify scoring column indices in headers
    scoring_col_indices = {}
    for i, h in enumerate(headers):
        h_lower = h.lower().strip()
        if h_lower in SCORING_COLUMNS:
            scoring_col_indices[h_lower] = i

    logger.info(f"[PARSE_MD] Scoring columns found at indices: {scoring_col_indices}")

    # Parse data rows (skip header and separator)
    row_num = 0
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped or not stripped.startswith('|') or _is_separator_line(stripped):
            continue

        row_num += 1

        # Parse table row: split by | and skip first/last empty strings from |...|
        raw_parts = stripped.split('|')
        values = [v.strip() for v in raw_parts[1:-1]]  # Skip first/last empty from |...|

        # Tolerate rows with fewer values
        if len(values) < len(headers):
            logger.warning(f"[PARSE_MD] Row {row_num} has fewer values than headers: {len(values)} < {len(headers)}")

        # Extract values and citations for each cell
        id_values = {}
        research_values = {}
        cell_citations = {}  # column_name -> list of citation URLs
        all_source_urls = set()

        # Extract scoring values from table columns
        relevancy = 0.7  # default
        reliability = 0.7  # default
        recency = 0.7  # default
        rationale = ''

        for col_idx, header in enumerate(headers):
            if col_idx >= len(values):
                continue

            cell_value = values[col_idx]
            h_lower = header.lower().strip()

            # Check if this is a scoring column
            if h_lower in SCORING_COLUMNS:
                # Extract scoring value (no citations expected on scores)
                if h_lower in ('rel', 'relevancy'):
                    try:
                        relevancy = float(cell_value) if cell_value else 0.7
                    except ValueError:
                        relevancy = 0.7
                elif h_lower in ('src', 'reliability'):
                    try:
                        reliability = float(cell_value) if cell_value else 0.7
                    except ValueError:
                        reliability = 0.7
                elif h_lower in ('rec', 'recency'):
                    try:
                        recency = float(cell_value) if cell_value else 0.7
                    except ValueError:
                        recency = 0.7
                elif h_lower == 'rationale':
                    rationale = cell_value
                continue  # Don't add scoring columns to id_values or research_values

            # Extract citation numbers [n] from cell
            citation_pattern = r'\[(\d+)\]'
            citation_nums = re.findall(citation_pattern, cell_value)

            # Remove citations from value for clean display
            clean_value = re.sub(citation_pattern, '', cell_value).strip()

            # Collect citation URLs for this cell
            cell_urls = []
            for cite_num in citation_nums:
                if cite_num in citations:
                    url = citations[cite_num]
                    cell_urls.append(url)
                    all_source_urls.add(url)

            if cell_urls:
                cell_citations[header] = cell_urls

            # Determine if this is an ID or RESEARCH column
            # Try exact match first
            if header in id_column_names:
                id_values[header] = clean_value
            elif header in research_column_names:
                if clean_value:  # Only add non-empty research values
                    research_values[header] = clean_value
            else:
                # Try case-insensitive match
                matched = False
                for col_name in id_column_names:
                    if col_name.lower() == header.lower():
                        id_values[col_name] = clean_value
                        matched = True
                        break
                if not matched:
                    for col_name in research_column_names:
                        if col_name.lower() == header.lower():
                            if clean_value:
                                research_values[col_name] = clean_value
                            matched = True
                            break
                # If still not matched and not a scoring column, treat first columns as ID
                if not matched and col_idx < len(id_column_names):
                    id_col_name = list(id_column_names)[col_idx] if col_idx < len(list(id_column_names)) else header
                    id_values[id_col_name] = clean_value

        # Generate row_id from first ID column value
        first_id_value = list(id_values.values())[0] if id_values else f"Row{row_num}"

        # Build candidate dict with scoring from table columns
        candidate = {
            'id_values': id_values,
            'research_values': research_values,
            'cell_citations': cell_citations,
            'source_urls': sorted(list(all_source_urls)),
            'row_id': f"{row_num}-{first_id_value}",
            'score_breakdown': {
                'relevancy': relevancy,
                'reliability': reliability,
                'recency': recency
            },
            'match_rationale': rationale,
            'match_score': (relevancy * 0.5 + reliability * 0.3 + recency * 0.2)
        }

        candidates.append(candidate)

    logger.info(f"[PARSE_MD] Parsed {len(candidates)} candidates from markdown table with {len(citations)} citations")
    return candidates


def _renumber_citations(
    markdown: str,
    citations: Dict[str, str],
    start_number: int
) -> tuple:
    """
    Renumber citations starting from start_number to avoid collisions.

    Args:
        markdown: Markdown text with [1], [2], etc.
        citations: {"1": "url1", "2": "url2"}
        start_number: First citation number to use

    Returns:
        (renumbered_markdown, renumbered_citations)
    """
    import re

    if not citations:
        return markdown, {}

    # Filter to only numeric citation keys (some models return non-standard formats)
    numeric_citations = _filter_numeric_citations(citations)
    if not numeric_citations:
        logger.warning("[CITATION] No numeric citation keys found, returning original markdown")
        return markdown, {}

    # Sort by number descending to avoid replacement collisions
    # e.g., replace [10] before [1] so we don't turn [10] into [1]0
    sorted_nums = sorted(numeric_citations.keys(), key=lambda x: int(x), reverse=True)

    renumbered_citations = {}
    renumbered_md = markdown

    # First pass: replace with temporary placeholders
    for old_num in sorted_nums:
        new_num = str(int(old_num) - 1 + start_number)
        renumbered_citations[new_num] = numeric_citations[old_num]
        # Use a unique placeholder that won't conflict with real citations
        renumbered_md = renumbered_md.replace(f'[{old_num}]', f'[__CITE_{new_num}__]')

    # Second pass: convert placeholders to final format
    for new_num in renumbered_citations.keys():
        renumbered_md = renumbered_md.replace(f'[__CITE_{new_num}__]', f'[{new_num}]')

    return renumbered_md, renumbered_citations


# Legacy function for backward compatibility
def parse_candidates_markdown_legacy(markdown_str: str, id_column_names: List[str]) -> List[Dict[str, Any]]:
    """
    Legacy parser for old format with scoring columns in table.
    Kept for backward compatibility.
    """
    if not markdown_str or not isinstance(markdown_str, str):
        return []

    candidates = []
    lines = markdown_str.strip().split('\n')

    header_line = None
    header_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith('|') and '---' not in line:
            header_line = line
            header_idx = i
            break

    if not header_line:
        return []

    headers = [h.strip() for h in header_line.split('|') if h.strip()]

    # Find indices for known columns
    relevancy_idx = None
    reliability_idx = None
    recency_idx = None
    rationale_idx = None
    sources_idx = None

    for i, h in enumerate(headers):
        h_lower = h.lower()
        if 'relevancy' in h_lower or h_lower == 'rel':
            relevancy_idx = i
        elif 'reliability' in h_lower:
            reliability_idx = i
        elif 'recency' in h_lower:
            recency_idx = i
        elif 'rationale' in h_lower or 'reason' in h_lower:
            rationale_idx = i
        elif 'source' in h_lower or 'url' in h_lower:
            sources_idx = i

    header_lower_map = {h.lower().strip(): i for i, h in enumerate(headers)}

    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped or not stripped.startswith('|') or _is_separator_line(stripped):
            continue

        raw_parts = stripped.split('|')
        values = [v.strip() for v in raw_parts[1:-1]]

        id_values = {}
        for col_name in id_column_names:
            if col_name in headers:
                col_idx = headers.index(col_name)
                if col_idx < len(values):
                    id_values[col_name] = values[col_idx]
            elif col_name.lower() in header_lower_map:
                col_idx = header_lower_map[col_name.lower()]
                if col_idx < len(values):
                    id_values[col_name] = values[col_idx]

        try:
            relevancy = float(values[relevancy_idx]) if relevancy_idx is not None and relevancy_idx < len(values) else 0.7
        except (ValueError, TypeError):
            relevancy = 0.7
        try:
            reliability = float(values[reliability_idx]) if reliability_idx is not None and reliability_idx < len(values) else 0.7
        except (ValueError, TypeError):
            reliability = 0.7
        try:
            recency = float(values[recency_idx]) if recency_idx is not None and recency_idx < len(values) else 0.7
        except (ValueError, TypeError):
            recency = 0.7

        rationale = values[rationale_idx] if rationale_idx is not None and rationale_idx < len(values) else ""
        sources_str = values[sources_idx] if sources_idx is not None and sources_idx < len(values) else ""
        source_urls = [s.strip() for s in sources_str.split(',') if s.strip()]

        candidate = {
            'id_values': id_values,
            'score_breakdown': {
                'relevancy': relevancy,
                'reliability': reliability,
                'recency': recency
            },
            'match_rationale': rationale,
            'source_urls': source_urls,
            'match_score': (relevancy * 0.5 + reliability * 0.3 + recency * 0.2)
        }

        candidates.append(candidate)

    return candidates


class RowDiscoveryStream:
    """
    Discover and score candidate rows for a single subdomain.

    Example:
        >>> stream = RowDiscoveryStream(ai_client, prompt_loader, schema_validator)
        >>> subdomain = {
        ...     "name": "AI Research Companies",
        ...     "focus": "Academic/research-focused AI companies",
        ...     "search_queries": ["AI research labs hiring", "machine learning research companies"]
        ... }
        >>> columns = [
        ...     {"name": "Company Name", "is_identification": True, ...},
        ...     {"name": "Website", "is_identification": True, ...}
        ... ]
        >>> search_strategy = {"description": "Find AI companies...", ...}
        >>> result = await stream.discover_rows(subdomain, columns, search_strategy)
        >>> print(f"Found {len(result['candidates'])} candidates")
    """

    def __init__(self, ai_client, prompt_loader, schema_validator):
        """
        Initialize row discovery stream.

        Args:
            ai_client: AI API client instance (supports Perplexity for web search)
            prompt_loader: PromptLoader instance for loading templates
            schema_validator: SchemaValidator instance for validating outputs
        """
        self.ai_client = ai_client
        self.prompt_loader = prompt_loader
        self.schema_validator = schema_validator

        logger.info("RowDiscoveryStream initialized")

    async def discover_rows_progressive(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        target_rows: int,
        escalation_strategy: List[Dict[str, Any]],
        global_counter: Optional[Dict[str, Any]] = None,
        global_counter_lock: Optional['asyncio.Lock'] = None,
        previous_search_improvements: Optional[List[str]] = None,
        soft_schema: bool = True,
        citation_start_number: int = 1
    ) -> Dict[str, Any]:
        """
        Discover rows using progressive model escalation.

        Tries each strategy in order, stopping early if sufficient candidates found.
        Returns ALL candidates from all rounds for later consolidation.

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Overall search strategy
            target_rows: Number of rows to target for this subdomain
            escalation_strategy: List of strategies to try:
              [
                {"model": "sonar", "search_context_size": "low", "min_candidates_percentage": 50},
                {"model": "sonar", "search_context_size": "high", "min_candidates_percentage": 75},
                {"model": "sonar-pro", "search_context_size": "high", "min_candidates_percentage": null}
              ]

        Returns:
            {
              "subdomain": str,
              "all_rounds": [
                {
                  "round": 1,
                  "model": "sonar",
                  "context": "low",
                  "candidates": [...],
                  "count": 5
                },
                ...
              ],
              "candidates": [...],  # All candidates combined
              "total_candidates": 15,
              "rounds_executed": 2,
              "rounds_skipped": 1,
              "processing_time": float
            }
        """
        start_time = time.time()
        subdomain_name = subdomain.get('name', 'Unknown')

        try:
            # Validate inputs
            self._validate_inputs(subdomain, columns, search_strategy)

            logger.info(
                f"Starting progressive row discovery for subdomain: {subdomain_name} "
                f"(target: {target_rows} rows, {len(escalation_strategy)} round(s) max)"
            )

            # Log escalation strategy details for debugging
            for idx, strat in enumerate(escalation_strategy, 1):
                logger.info(
                    f"  Strategy {idx}: model={strat.get('model')}, "
                    f"min_pct={strat.get('min_candidates_percentage')}, "
                    f"context={strat.get('search_context_size', 'high')}"
                )

            all_rounds = []
            accumulated_candidates = []
            all_search_improvements = []
            all_citations = {}  # Combined citations from all rounds
            current_citation = citation_start_number

            # Combine previous improvements from other subdomains with current subdomain's improvements
            combined_improvements = list(previous_search_improvements) if previous_search_improvements else []

            for round_idx, strategy in enumerate(escalation_strategy, 1):
                model = strategy['model']
                context = strategy.get('search_context_size', 'high')  # Default to 'high' if not specified
                max_web_searches = strategy.get('max_web_searches', 3)  # For Claude models
                min_percentage = strategy.get('min_candidates_percentage')
                findall = strategy.get('findall', False)  # For the-clone models
                findall_iterations = strategy.get('findall_iterations', 1)  # Max self-correction iterations

                logger.info(
                    f"[ESCALATION] {subdomain_name} entering round {round_idx}/{len(escalation_strategy)}: "
                    f"model={model}, min_pct={min_percentage}, accumulated={len(accumulated_candidates)}"
                )

                # === GLOBAL COUNTER CHECK (BEFORE executing this level) ===
                if global_counter:
                    # Get current global count (with lock if parallel)
                    if global_counter_lock:
                        async with global_counter_lock:
                            current_global = global_counter['total_discovered']
                            global_target = global_counter['target']
                            threshold_pct = global_counter['threshold_percentage']
                    else:
                        current_global = global_counter['total_discovered']
                        global_target = global_counter['target']
                        threshold_pct = global_counter['threshold_percentage']

                    # Calculate threshold
                    stop_at_count = int((global_target * threshold_pct) / 100)

                    # Check: Do we have enough globally?
                    if current_global >= stop_at_count:
                        rounds_skipped = len(escalation_strategy) - round_idx + 1
                        logger.info(
                            f"[GLOBAL STOP] {subdomain_name} Round {round_idx}: "
                            f"Global count {current_global} >= threshold {stop_at_count} "
                            f"({threshold_pct}% of {global_target}). Skipping {rounds_skipped} round(s)"
                        )
                        break
                    else:
                        logger.info(
                            f"[GLOBAL CHECK] {subdomain_name} Round {round_idx}: "
                            f"Global {current_global} < threshold {stop_at_count}, continuing"
                        )

                # Log round info with appropriate details
                if 'claude' in model.lower():
                    logger.info(
                        f"Round {round_idx}/{len(escalation_strategy)}: {model} ({max_web_searches} web searches)"
                    )
                else:
                    logger.info(
                        f"Round {round_idx}/{len(escalation_strategy)}: {model} ({context} context)"
                    )

                # Execute this round with combined improvements (from other subdomains + previous rounds)
                round_candidates = await self._discover_and_score(
                    subdomain,
                    columns,
                    search_strategy,
                    target_rows,
                    model,
                    context,
                    combined_improvements,  # Pass improvements from other subdomains AND previous rounds
                    max_web_searches,
                    findall,        # Pass findall flag for the-clone (position 9)
                    soft_schema,    # Pass soft_schema flag (position 10)
                    findall_iterations,  # Pass findall_iterations for the-clone (position 11)
                    current_citation  # Pass citation_start_number (position 12)
                )

                # Collect and renumber citations from this round
                round_citations = round_candidates.get('citations', {})
                if round_citations:
                    # Filter to numeric keys only (some models return non-standard formats)
                    numeric_citations = _filter_numeric_citations(round_citations)
                    all_citations.update(numeric_citations)
                    max_cite = _get_max_citation_number(numeric_citations)
                    if max_cite > 0:
                        current_citation = max_cite + 1

                # Tag each candidate with model/context info
                candidates = round_candidates.get('candidates', [])
                for candidate in candidates:
                    candidate['model_used'] = model
                    candidate['context_used'] = context
                    candidate['round'] = round_idx

                # Collect search improvements from this round
                search_improvements = round_candidates.get('search_improvements', [])
                if search_improvements:
                    all_search_improvements.extend(search_improvements)
                    # Add to combined list so next round can use them
                    combined_improvements.extend(search_improvements)
                    logger.info(
                        f"Round {round_idx}: Collected {len(search_improvements)} search improvement(s). "
                        f"Total improvements available: {len(combined_improvements)}"
                    )

                # Collect domain filtering recommendations from this round
                domain_recommendations = round_candidates.get('domain_filtering_recommendations', {})

                # Extract no_matches_reason if 0 candidates (for QC to understand why)
                no_matches_reason = round_candidates.get('no_matches_reason', '')

                # PHASE 1: Record round results with enhanced_data and prompt
                round_data = {
                    'round': round_idx,
                    'model': model,
                    'context': context,
                    'candidates': candidates,
                    'candidates_markdown': round_candidates.get('candidates_markdown', ''),  # Markdown table with scoring columns
                    'citations': round_candidates.get('citations', {}),  # Preserve citations for this round
                    'count': len(candidates),
                    'search_improvements': search_improvements,
                    'domain_filtering_recommendations': domain_recommendations,
                    'no_matches_reason': no_matches_reason,  # Include reason if 0 candidates
                    'enhanced_data': round_candidates.get('enhanced_data', {}),
                    'prompt_used': round_candidates.get('prompt_used', ''),
                    'call_description': f"Finding Rows - {subdomain_name} - Round {round_idx} ({model}-{context})"
                }
                all_rounds.append(round_data)

                # Accumulate candidates
                accumulated_candidates.extend(candidates)
                total_so_far = len(accumulated_candidates)

                # === UPDATE GLOBAL COUNTER (AFTER executing this level) ===
                if global_counter:
                    if global_counter_lock:
                        async with global_counter_lock:
                            global_counter['total_discovered'] += len(candidates)
                            global_counter['by_subdomain'][subdomain_name] = global_counter['by_subdomain'].get(subdomain_name, 0) + len(candidates)
                            global_counter['by_level'][f"Round {round_idx}"] = global_counter['by_level'].get(f"Round {round_idx}", 0) + len(candidates)
                            updated_global = global_counter['total_discovered']
                    else:
                        global_counter['total_discovered'] += len(candidates)
                        global_counter['by_subdomain'][subdomain_name] = global_counter['by_subdomain'].get(subdomain_name, 0) + len(candidates)
                        global_counter['by_level'][f"Round {round_idx}"] = global_counter['by_level'].get(f"Round {round_idx}", 0) + len(candidates)
                        updated_global = global_counter['total_discovered']

                    logger.info(
                        f"[GLOBAL COUNTER] {subdomain_name} Round {round_idx}: "
                        f"+{len(candidates)} candidates. "
                        f"Subdomain: {total_so_far}, Global: {updated_global}/{global_target}"
                    )
                else:
                    logger.info(f"Round {round_idx}: Found {len(candidates)} candidates (total: {total_so_far})")

                # Check if we should stop early (LOCAL check)
                if min_percentage is not None:
                    threshold = int(target_rows * (min_percentage / 100))

                    if total_so_far >= threshold:
                        rounds_skipped = len(escalation_strategy) - round_idx
                        logger.info(
                            f"[LOCAL STOP] {subdomain_name} Round {round_idx}: "
                            f"{total_so_far} candidates >= {threshold} threshold "
                            f"({min_percentage}% of {target_rows}). Skipping {rounds_skipped} round(s)"
                        )
                        break
                    else:
                        # Log that we're continuing (not stopping)
                        logger.info(
                            f"[LOCAL CHECK] {subdomain_name} Round {round_idx}: "
                            f"{total_so_far} < {threshold} threshold, continuing to next round"
                        )

            # Log why we exited the loop
            logger.info(
                f"[ESCALATION COMPLETE] {subdomain_name}: Exited after {len(all_rounds)} round(s), "
                f"{len(accumulated_candidates)} total candidates"
            )

            # Prepare result
            processing_time = time.time() - start_time
            rounds_executed = len(all_rounds)
            rounds_skipped = len(escalation_strategy) - rounds_executed

            # Combine candidates_markdown from all rounds
            # Note: scoring is now embedded in the markdown table (Rel, Src, Rec, Rationale columns)
            combined_markdown_parts = []
            for round_data in all_rounds:
                round_md = round_data.get('candidates_markdown', '')
                if round_md:
                    combined_markdown_parts.append(round_md)

            # Merge markdown tables (keep headers from first, append data rows from rest)
            combined_markdown = ''
            if combined_markdown_parts:
                combined_markdown = combined_markdown_parts[0]
                for md in combined_markdown_parts[1:]:
                    # Skip header rows (first 2 lines: header + separator)
                    lines = md.strip().split('\n')
                    if len(lines) > 2:
                        data_rows = '\n'.join(lines[2:])
                        combined_markdown += '\n' + data_rows

            result = {
                'subdomain': subdomain_name,
                'all_rounds': all_rounds,
                'candidates': accumulated_candidates,  # Parsed (with scoring from table columns)
                'candidates_markdown': combined_markdown,  # Raw markdown (includes scoring columns)
                'citations': all_citations,
                'max_citation_number': current_citation - 1 if current_citation > citation_start_number else citation_start_number,
                'total_candidates': len(accumulated_candidates),
                'rounds_executed': rounds_executed,
                'rounds_skipped': rounds_skipped,
                'search_improvements': all_search_improvements,
                'processing_time': processing_time
            }

            logger.info(
                f"Progressive discovery completed for '{subdomain_name}': "
                f"{len(accumulated_candidates)} candidates from {rounds_executed} round(s) "
                f"in {processing_time:.2f}s"
            )

            return result

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Progressive row discovery failed for '{subdomain_name}': {str(e)}"
            logger.error(error_msg)

            # Return empty result on error
            return {
                'subdomain': subdomain_name,
                'all_rounds': [],
                'candidates': [],
                'total_candidates': 0,
                'rounds_executed': 0,
                'rounds_skipped': len(escalation_strategy),
                'processing_time': processing_time,
                'error': error_msg
            }

    async def discover_rows(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        target_rows: int = 7,
        scoring_model: str = 'sonar-pro',
        escalation_strategy: Optional[List[Dict[str, Any]]] = None,
        global_counter: Optional[Dict[str, Any]] = None,
        global_counter_lock: Optional['asyncio.Lock'] = None,
        previous_search_improvements: Optional[List[str]] = None,
        soft_schema: bool = True,
        citation_start_number: int = 1
    ) -> Dict[str, Any]:
        """
        Discover candidate rows for a single subdomain using integrated scoring.

        If escalation_strategy is provided, uses progressive escalation.
        Otherwise, uses legacy two-step context escalation.

        Uses a single sonar-pro call to both search and score candidates.
        Scoring is based on three dimensions:
        - Relevancy to requirements (40%)
        - Source reliability (30%)
        - Recency of information (30%)

        Args:
            subdomain: Subdomain definition with:
                - name: str (e.g., "AI Research Companies")
                - focus: str (description of focus area)
                - search_queries: List[str] (specific queries for this subdomain)
                - target_rows: int (how many to find)
            columns: List of column definitions (ID + research columns)
            search_strategy: Overall search strategy with description
            target_rows: Number of candidates to find for this subdomain (default: 7)
            scoring_model: Model to use for integrated search+scoring (default: 'sonar-pro')
            escalation_strategy: Optional list of progressive strategies (default: None for legacy mode)

        Returns:
            Dictionary with:
            {
                "subdomain": str,
                "candidates": List[{
                    "id_values": Dict[str, str],
                    "match_score": float (0-1),
                    "score_breakdown": {
                        "relevancy": float (0-1),
                        "reliability": float (0-1),
                        "recency": float (0-1)
                    },
                    "match_rationale": str,
                    "source_urls": List[str],
                    "model_used": str (if progressive),
                    "context_used": str (if progressive),
                    "round": int (if progressive)
                }],
                "processing_time": float
            }

        Raises:
            ValueError: If subdomain or columns are malformed
            Exception: If integrated search/scoring fails
        """
        # If escalation_strategy provided, use progressive mode
        if escalation_strategy is not None:
            result = await self.discover_rows_progressive(
                subdomain, columns, search_strategy, target_rows, escalation_strategy,
                global_counter, global_counter_lock, previous_search_improvements, soft_schema,
                citation_start_number
            )
            # Return progressive result with all_rounds for detailed tracking
            return {
                'subdomain': result['subdomain'],
                'candidates': result['candidates'],
                'citations': result.get('citations', {}),
                'max_citation_number': result.get('max_citation_number', citation_start_number),
                'processing_time': result['processing_time'],
                'rounds_executed': result.get('rounds_executed', 0),
                'rounds_skipped': result.get('rounds_skipped', 0),
                'search_improvements': result.get('search_improvements', []),
                'all_rounds': result.get('all_rounds', []),  # Include all rounds with prompts/enhanced_data
                'error': result.get('error')
            }

        # Legacy mode: two-step context escalation
        start_time = time.time()
        subdomain_name = subdomain.get('name', 'Unknown')

        try:
            # Validate inputs
            self._validate_inputs(subdomain, columns, search_strategy)

            logger.info(
                f"Starting integrated row discovery for subdomain: {subdomain_name} "
                f"(target: {target_rows} rows)"
            )

            # Try low context first, escalate to high if insufficient results
            logger.info(f"Attempt 1: Trying low context search")
            candidates_data = await self._discover_and_score(
                subdomain,
                columns,
                search_strategy,
                target_rows,
                scoring_model,
                search_context_size='low',
                previous_search_improvements=None,
                max_web_searches=3,
                soft_schema=soft_schema
            )

            # Check if we got enough candidates
            candidate_count = len(candidates_data.get('candidates', []))
            min_required = max(3, target_rows // 2)  # At least 3 or half of target

            if candidate_count < min_required:
                logger.warning(
                    f"Low context found only {candidate_count} candidates "
                    f"(need {min_required}). Retrying with high context..."
                )
                candidates_data = await self._discover_and_score(
                    subdomain,
                    columns,
                    search_strategy,
                    target_rows,
                    scoring_model,
                    search_context_size='high',
                    previous_search_improvements=None,
                    max_web_searches=3,
                    soft_schema=soft_schema
                )
                candidate_count = len(candidates_data.get('candidates', []))
                logger.info(f"High context search found {candidate_count} candidates")

            # Validate output against schema
            is_valid, error = self.schema_validator.validate(
                candidates_data,
                'row_discovery_response'
            )

            if not is_valid:
                logger.error(f"Schema validation failed: {error}")
                raise ValueError(f"Row discovery output validation failed: {error}")

            # Add metadata
            processing_time = time.time() - start_time
            candidates_data['processing_time'] = processing_time

            candidate_count = len(candidates_data.get('candidates', []))
            logger.info(
                f"Row discovery completed for '{subdomain_name}': "
                f"{candidate_count} candidates found in {processing_time:.2f}s"
            )

            return candidates_data

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Row discovery failed for '{subdomain_name}': {str(e)}"
            logger.error(error_msg)

            # Return empty result on error (graceful degradation)
            return {
                'subdomain': subdomain_name,
                'candidates': [],
                'processing_time': processing_time,
                'error': error_msg
            }

    def _validate_inputs(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any]
    ):
        """
        Validate input parameters.

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Search strategy

        Raises:
            ValueError: If inputs are malformed
        """
        # Validate subdomain
        if not isinstance(subdomain, dict):
            raise ValueError("Subdomain must be a dictionary")

        required_subdomain_fields = ['name', 'focus', 'search_queries']
        for field in required_subdomain_fields:
            if field not in subdomain:
                raise ValueError(f"Subdomain missing required field: {field}")

        if not isinstance(subdomain['search_queries'], list):
            raise ValueError("Subdomain search_queries must be a list")

        if len(subdomain['search_queries']) == 0:
            raise ValueError("Subdomain must have at least one search query")

        # Validate columns
        if not isinstance(columns, list) or len(columns) == 0:
            raise ValueError("Columns must be a non-empty list")

        # Check for at least one ID column
        id_columns = [col for col in columns if col.get('importance', '').upper() == 'ID']
        if len(id_columns) == 0:
            raise ValueError("At least one column must have importance='ID'")

        # Validate search strategy
        if not isinstance(search_strategy, dict):
            raise ValueError("Search strategy must be a dictionary")

    async def _discover_and_score(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        target_rows: int,
        scoring_model: str,
        search_context_size: str = 'low',
        previous_search_improvements: Optional[List[str]] = None,
        max_web_searches: int = 3,
        findall: bool = False,
        soft_schema: bool = True,
        findall_iterations: int = 1,
        citation_start_number: int = 1
    ) -> Dict[str, Any]:
        """
        Execute web search with integrated scoring in ONE call.

        Uses sonar-pro (or configured model) to:
        1. Search for entities matching subdomain focus
        2. Score each entity using the rubric
        3. Return top N scored candidates

        Returns candidates with score_breakdown showing:
        - relevancy_score (0-1)
        - reliability_score (0-1)
        - recency_score (0-1)
        - final_score (weighted average)

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Search strategy
            target_rows: How many rows to find
            scoring_model: Model to use (default: sonar-pro)

        Returns:
            Dictionary matching row_discovery_response schema with score_breakdown
        """
        # Build prompt with integrated scoring rubric
        prompt = self._build_integrated_scoring_prompt(
            subdomain,
            columns,
            search_strategy,
            target_rows,
            previous_search_improvements,
            citation_start_number
        )

        # Load schema for structured output
        schema = self.schema_validator.load_schema('row_discovery_response')

        # Extract domain filtering parameters
        # First try subdomain-specific overrides
        include_domains = subdomain.get('included_domains')
        exclude_domains = subdomain.get('excluded_domains')

        # Fall back to search_strategy defaults if not in subdomain
        if include_domains is None:
            include_domains = search_strategy.get('default_included_domains')
        if exclude_domains is None:
            exclude_domains = search_strategy.get('default_excluded_domains')

        # Determine appropriate parameters based on model type
        is_claude = 'claude' in scoring_model.lower()

        if is_claude:
            logger.info(
                f"Calling {scoring_model} for integrated discovery+scoring: "
                f"'{subdomain['name']}' (target: {target_rows} rows, {max_web_searches} web searches)"
            )
        else:
            logger.info(
                f"Calling {scoring_model} for integrated discovery+scoring: "
                f"'{subdomain['name']}' (target: {target_rows} rows, context: {search_context_size})"
            )

        # Log domain filtering if configured
        if include_domains or exclude_domains:
            logger.info(
                f"Domain filtering: include={include_domains or 'none'}, "
                f"exclude={exclude_domains or 'none'}"
            )

        try:
            # Build debug_name for log identification (truncated to 30 chars)
            subdomain_name_clean = subdomain['name'].replace(' ', '_')[:20]
            debug_name = f"row_disc_{subdomain_name_clean}"

            # Single call with structured output (Perplexity or Claude with web search)
            result = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=scoring_model,
                tool_name='row_discovery_integrated',
                use_cache=True,  # Enable caching for testing/debugging (normally False because web results change)
                max_tokens=16000,  # Increased for finding multiple entities with details
                max_web_searches=max_web_searches,  # For Claude models (Perplexity uses subdomain queries)
                search_context_size=search_context_size,  # For Perplexity models
                soft_schema=soft_schema,  # Use config setting for schema strictness
                include_domains=include_domains,  # Domain filtering
                exclude_domains=exclude_domains,   # Domain filtering
                findall=findall,  # For the-clone models
                findall_iterations=findall_iterations,  # Max self-correction iterations for the-clone
                debug_name=debug_name  # For S3 debug logs (debug/clone/)
            )

            # call_structured_api returns dict with 'response', 'token_usage', etc.
            # Check if we got a valid response
            if 'response' not in result:
                raise ValueError(f"LLM call failed: {result.get('error', 'No response returned')}")

            # Log call metrics and debug paths for CloudWatch visibility
            processing_time = result.get('processing_time', 0)
            enhanced_data = result.get('enhanced_data', {})
            total_cost = enhanced_data.get('costs', {}).get('actual', {}).get('total', 0)
            debug_md_uri = result.get('debug_md_uri')
            debug_json_uri = result.get('debug_json_uri')
            is_cached = result.get('is_cached', False)

            logger.info(
                f"[ROW_DISCOVERY] '{subdomain['name']}' complete: "
                f"time={processing_time:.1f}s, cost=${total_cost:.4f}, cached={is_cached}"
            )
            if debug_md_uri:
                logger.info(f"[ROW_DISCOVERY] Debug log: {debug_md_uri}")
            if debug_json_uri:
                logger.info(f"[ROW_DISCOVERY] Debug JSON: {debug_json_uri}")

            # Extract structured response
            response_data = result.get('response', {})

            # If response is in Perplexity unified format, extract the JSON
            if isinstance(response_data, dict) and 'choices' in response_data:
                content = response_data['choices'][0]['message']['content']
                if isinstance(content, str):
                    response_data = json.loads(content)
            elif isinstance(response_data, str):
                response_data = json.loads(response_data)

            # Ensure subdomain is set correctly
            response_data['subdomain'] = subdomain['name']

            # Get candidates - handle both new format (candidates_markdown) and old format (candidates)
            candidates_markdown = response_data.get('candidates_markdown', '')
            candidates_raw = response_data.get('candidates', '')
            citations = response_data.get('citations', {})
            scoring = response_data.get('scoring', [])

            # Renumber citations if needed to avoid collisions
            # Wrapped in try-except to preserve rows even if citation processing fails
            if citations and citation_start_number > 1:
                try:
                    candidates_markdown, citations = _renumber_citations(
                        candidates_markdown,
                        citations,
                        citation_start_number
                    )
                    logger.info(f"[CITATION] Renumbered {len(citations)} citations starting from {citation_start_number}")
                except Exception as cite_err:
                    logger.warning(f"[CITATION] Failed to renumber citations: {cite_err}. Continuing without citation renumbering.")
                    # Filter to numeric citations only and continue
                    citations = _filter_numeric_citations(citations)

            # Parse candidates from new format (candidates_markdown with citations)
            # Each parsing attempt is wrapped in try-except for robustness
            candidates = []
            parse_method_used = None

            if candidates_markdown and isinstance(candidates_markdown, str):
                # Try new format: parse with full columns and citations
                try:
                    candidates = parse_candidates_markdown(
                        candidates_markdown,
                        columns,
                        citations,
                        scoring
                    )
                    parse_method_used = "new_format"
                    logger.info(f"[DISCOVERY] Parsed {len(candidates)} candidates from new format (candidates_markdown with {len(citations)} citations)")
                except Exception as parse_err:
                    logger.warning(f"[DISCOVERY] Failed to parse candidates_markdown: {parse_err}. Trying legacy format...")
                    # Fall through to try legacy parsing

            # Try legacy format if new format failed or wasn't available
            if not candidates and isinstance(candidates_raw, str) and candidates_raw:
                try:
                    # Legacy format: markdown in 'candidates' field with scoring columns
                    id_column_names = [col.get('name', '') for col in columns if col.get('importance', '').upper() == 'ID']
                    candidates = parse_candidates_markdown_legacy(candidates_raw, id_column_names)
                    parse_method_used = "legacy_markdown"
                    logger.info(f"[DISCOVERY] Parsed {len(candidates)} candidates from legacy markdown format")
                except Exception as legacy_err:
                    logger.warning(f"[DISCOVERY] Failed to parse legacy markdown: {legacy_err}")

            # Try JSON array format if still no candidates
            if not candidates and isinstance(candidates_raw, list):
                try:
                    candidates = candidates_raw
                    parse_method_used = "json_array"
                    logger.info(f"[DISCOVERY] Using {len(candidates)} candidates from JSON array (legacy)")
                except Exception as json_err:
                    logger.warning(f"[DISCOVERY] Failed to use JSON array candidates: {json_err}")

            # Last resort: try to parse candidates_markdown as legacy if we have it but parsing failed
            if not candidates and candidates_markdown and isinstance(candidates_markdown, str) and parse_method_used != "legacy_markdown":
                try:
                    id_column_names = [col.get('name', '') for col in columns if col.get('importance', '').upper() == 'ID']
                    candidates = parse_candidates_markdown_legacy(candidates_markdown, id_column_names)
                    parse_method_used = "fallback_legacy"
                    logger.info(f"[DISCOVERY] Parsed {len(candidates)} candidates using fallback legacy parser on candidates_markdown")
                except Exception as fallback_err:
                    logger.warning(f"[DISCOVERY] Fallback legacy parser also failed: {fallback_err}")

            # PHASE 2: DEBUG logging when 0 candidates found
            if len(candidates) == 0:
                logger.warning(f"[DEBUG] {scoring_model} ({search_context_size}) returned 0 candidates!")
                logger.warning(f"[DEBUG] Subdomain: {subdomain['name']}")
                logger.warning(f"[DEBUG] Search queries: {subdomain.get('search_queries', [])}")
                logger.warning(f"[DEBUG] Prompt (first 500 chars): {prompt[:500]}")
                logger.warning(f"[DEBUG] Response type: {type(response_data)}")
                logger.warning(f"[DEBUG] Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'N/A'}")
                logger.warning(f"[DEBUG] candidates_markdown: {candidates_markdown[:500] if candidates_markdown else 'empty'}")
                logger.warning(f"[DEBUG] candidates raw type: {type(candidates_raw)}")

                # Try to extract any text content
                raw_response = result.get('response', {})
                if 'choices' in raw_response:
                    try:
                        content = raw_response['choices'][0]['message']['content']
                        logger.warning(f"[DEBUG] Response content (first 500 chars): {str(content)[:500]}")
                    except Exception as e:
                        logger.warning(f"[DEBUG] Could not extract response content: {e}")

            response_data['candidates'] = candidates[:target_rows]
            # Preserve citations in response for downstream use
            response_data['citations'] = citations

            # Preserve original candidates_markdown for debugging and downstream use
            # Note: scoring is now extracted from table columns (Rel, Src, Rec, Rationale)
            response_data['candidates_markdown'] = candidates_markdown

            # PHASE 1: Include enhanced_data in return
            response_data['enhanced_data'] = result.get('enhanced_data', {})

            # Save prompt for debugging/analysis
            response_data['prompt_used'] = prompt

            return response_data

        except Exception as e:
            logger.error(f"Error in integrated discovery+scoring: {str(e)}")
            # Return empty candidates on error
            return {
                'subdomain': subdomain['name'],
                'candidates': [],
                'enhanced_data': {}
            }

    def _format_requirements(self, requirements: List[Dict[str, Any]]) -> str:
        """
        Format requirements as bullet list for prompts (backward compatibility helper).

        Args:
            requirements: List of requirement dictionaries

        Returns:
            Formatted string with bullet points, or "(None)" if empty
        """
        if not requirements or len(requirements) == 0:
            return "(None)"

        bullet_points = []
        for req in requirements:
            requirement_text = req.get('requirement', '')
            rationale = req.get('rationale', '')

            if rationale:
                bullet_points.append(f"- {requirement_text} ({rationale})")
            else:
                bullet_points.append(f"- {requirement_text}")

        return '\n'.join(bullet_points)

    def _build_integrated_scoring_prompt(
        self,
        subdomain: Dict[str, Any],
        columns: List[Dict[str, Any]],
        search_strategy: Dict[str, Any],
        target_rows: int,
        previous_search_improvements: Optional[List[str]] = None,
        citation_start_number: int = 1
    ) -> str:
        """
        Build prompt with integrated scoring rubric using template.

        Args:
            subdomain: Subdomain definition
            columns: Column definitions
            search_strategy: Search strategy
            target_rows: How many rows to find

        Returns:
            Filled prompt string from template
        """
        # Extract ID columns with descriptions
        id_columns = [col for col in columns if col.get('importance', '').upper() == 'ID']

        # Format ID columns with descriptions
        id_columns_text = []
        for col in id_columns:
            name = col['name']
            desc = col.get('description', 'No description')
            id_columns_text.append(f"- **{name}**: {desc}")

        # Extract research columns (non-ID columns) with descriptions
        # Check both importance='ID' and is_identification for compatibility
        research_columns = [
            col for col in columns
            if col.get('importance', '').upper() != 'ID' and not col.get('is_identification')
        ]

        # Format research columns with descriptions
        research_columns_text = []
        for col in research_columns:
            name = col['name']
            desc = col.get('description', 'No description')
            research_columns_text.append(f"- **{name}**: {desc}")

        # Build table header from ALL columns (ID first, then RESEARCH, then SCORING)
        all_column_names = [col['name'] for col in id_columns] + [col['name'] for col in research_columns]
        # Add scoring columns at the end
        scoring_columns = ['Rel', 'Src', 'Rec', 'Rationale']
        all_column_names_with_scoring = all_column_names + scoring_columns
        column_headers = "| " + " | ".join(all_column_names_with_scoring) + " |"
        column_separator = "|" + "|".join(["---"] * len(all_column_names_with_scoring)) + "|"
        column_headers_full = f"{column_headers}\n{column_separator}"

        # Format column descriptions for guidance
        column_descriptions = []
        for col in id_columns:
            column_descriptions.append(f"- **{col['name']}** (ID): {col.get('description', 'Identification column')}")
        for col in research_columns:
            column_descriptions.append(f"- **{col['name']}** (RESEARCH): {col.get('description', 'Research column')}")

        # Format previous search improvements if provided
        improvements_text = ""
        if previous_search_improvements and len(previous_search_improvements) > 0:
            improvements_text = "\n\n**Previous Search Improvements:**\n"
            improvements_text += "Based on earlier searches (from other subdomains and previous rounds), here are suggestions to improve your results:\n"
            for improvement in previous_search_improvements:
                improvements_text += f"- {improvement}\n"
            improvements_text += "\nConsider these insights when formulating your searches."

        # Try to load template (if exists), otherwise use inline
        try:
            # Extract or format requirements for prompt
            # Try to use pre-formatted requirements from column_definition_handler (Phase 1, Item 2)
            hard_requirements = search_strategy.get('formatted_hard_requirements')
            soft_requirements = search_strategy.get('formatted_soft_requirements')

            # Backward compatibility: If formatted versions don't exist, create them on the fly
            if hard_requirements is None or soft_requirements is None:
                requirements = search_strategy.get('requirements', [])
                hard_reqs = [r for r in requirements if r.get('type') == 'hard']
                soft_reqs = [r for r in requirements if r.get('type') == 'soft']

                # Format as bullet lists
                if hard_requirements is None:
                    hard_requirements = self._format_requirements(hard_reqs)
                if soft_requirements is None:
                    soft_requirements = self._format_requirements(soft_reqs)

            # Format authoritative source (lean - for search section)
            authoritative_source = ''
            has_url = subdomain.get('discovered_list_url') and subdomain['discovered_list_url'].strip()
            if has_url:
                authoritative_source = f"\n**Authoritative Source:** {subdomain['discovered_list_url']}\n"

            # Format example entities (for results/filtering section)
            example_entities = ''
            has_candidates = subdomain.get('candidates') and len(subdomain['candidates']) > 0
            if has_candidates:
                candidates_list = ', '.join(subdomain['candidates'][:10])
                example_entities = f"\n**Example Entities:** {candidates_list}\n"
                example_entities += "These show the type of entities to find. Find ALL relevant entities, not just these examples.\n"

            # Format priority search queries (top 3)
            priority_queries = '\n**Search Suggestions:**\n'
            priority_queries += '\n'.join(f'{i+1}. {q}' for i, q in enumerate(subdomain['search_queries'][:3]))

            # Keep old DISCOVERED_LIST_INFO for backward compatibility with any code that uses it
            discovered_list_info = ''
            if has_url or has_candidates:
                discovered_list_info = "\n## ⚠️ AUTHORITATIVE SOURCE FOUND - START HERE\n\n"
                if has_url:
                    discovered_list_info += f"**Authoritative List URL:** {subdomain['discovered_list_url']}\n\n"
                    discovered_list_info += f"**CRITICAL:** You MUST search this URL first to find entities. This is your primary data source.\n\n"
                if has_candidates:
                    candidates_list_bullet = '\n'.join(f'- {c}' for c in subdomain['candidates'][:10])
                    discovered_list_info += f"**Example Entities to Look For:**\n{candidates_list_bullet}\n\n"
                    discovered_list_info += f"**INSTRUCTIONS:**\n"
                    discovered_list_info += f"1. Search the authoritative list above for entities similar to these examples\n"
                    discovered_list_info += f"2. These examples show the EXACT TYPE of entities you need\n"
                    discovered_list_info += f"3. Find as many similar entities as possible from the authoritative source\n"
                    discovered_list_info += f"4. Only use general web search if the authoritative list is insufficient\n"
                    discovered_list_info += f"5. These are NOT constraints - find ALL relevant entities, not just these\n\n"

            variables = {
                'SUBDOMAIN_NAME': subdomain['name'],
                'SUBDOMAIN_FOCUS': subdomain['focus'],
                'SEARCH_REQUIREMENTS': search_strategy.get('description', 'Find relevant entities'),
                'HARD_REQUIREMENTS': hard_requirements,
                'SOFT_REQUIREMENTS': soft_requirements,
                'SEARCH_QUERIES': '\n'.join(f'- {q}' for q in subdomain['search_queries']),
                'TARGET_ROWS': str(target_rows),
                'ID_COLUMNS': '\n'.join(id_columns_text),
                'RESEARCH_COLUMNS': '\n'.join(research_columns_text) if research_columns_text else '(No research columns defined)',
                'COLUMN_HEADERS': column_headers_full,
                'COLUMN_DESCRIPTIONS': '\n'.join(column_descriptions),
                'USER_CONTEXT': search_strategy.get('user_context', 'General research table'),
                'TABLE_PURPOSE': search_strategy.get('table_purpose', search_strategy.get('description', '')),
                'TABLEWIDE_RESEARCH': search_strategy.get('tablewide_research', ''),
                'PREVIOUS_SEARCH_IMPROVEMENTS': improvements_text,
                'DISCOVERED_LIST_INFO': discovered_list_info,
                'AUTHORITATIVE_SOURCE': authoritative_source,
                'PRIORITY_SEARCH_QUERIES': priority_queries,
                'EXAMPLE_ENTITIES': example_entities,
                'CITATION_START_NUMBER': str(citation_start_number)
            }

            # Try template first
            prompt = self.prompt_loader.load_prompt('row_discovery', variables)
            return prompt

        except Exception as e:
            logger.debug(f"Could not load template, using inline prompt: {e}")

        # Fallback: Build inline (for backward compat)
        search_queries_text = '\n'.join(f'- {q}' for q in subdomain['search_queries'])
        id_columns_text = '\n'.join(f'- {col}' for col in id_columns)

        prompt = f"""You are finding and scoring entities for: {subdomain['name']}

FOCUS: {subdomain['focus']}

REQUIREMENTS: {search_strategy.get('description', 'Find relevant entities')}

TARGET: Find {target_rows} best-matching entities

SEARCH QUERIES (prioritize multi-row results):
{search_queries_text}

CRITICAL: Use EXACT field names for ID columns in your response:
{id_columns_text}

For example, if columns are "Company Name" and "Website", use those EXACT names:
  {{"id_values": {{"Company Name": "Anthropic", "Website": "https://anthropic.com"}}}}

Do NOT rename to "entity_name", "Entity Name", "company", etc.
Use the EXACT field names listed above.

SCORING RUBRIC (0-1.0 scale):
Final Score = (Relevancy × 0.4) + (Source Reliability × 0.3) + (Recency × 0.3)

**Relevancy (0-1.0):** How well does the entity match requirements?
  1.0 = Perfect match to all requirements
  0.7 = Matches most requirements, minor gaps
  0.4 = Matches core requirements only
  0.0 = Weak or no match

**Source Reliability (0-1.0):** How reliable are your sources?
  1.0 = Primary sources (company site, Crunchbase, official docs)
  0.7 = Secondary sources (TechCrunch, LinkedIn, WSJ, Bloomberg)
  0.4 = Tertiary sources (blogs, aggregators, forums)
  0.0 = Unreliable or unverified

**Recency (0-1.0):** How recent is the information?
  1.0 = <3 months old
  0.7 = 3-6 months old
  0.4 = 6-12 months old
  0.0 = >12 months or undated

For each entity:
1. Populate ID columns using EXACT field names from list above
2. Calculate individual dimension scores (relevancy, reliability, recency)
3. Calculate final weighted score: (relevancy × 0.4) + (reliability × 0.3) + (recency × 0.3)
4. Provide 1-sentence rationale explaining score
5. Include source URLs

Return top {target_rows} candidates sorted by final score (highest first).
"""
        return prompt


# Convenience function for easy usage
async def discover_rows(
    ai_client,
    prompt_loader,
    schema_validator,
    subdomain: Dict[str, Any],
    columns: List[Dict[str, Any]],
    search_strategy: Dict[str, Any],
    target_rows: int = 7,
    scoring_model: str = 'sonar-pro'
) -> Dict[str, Any]:
    """
    Convenience function to discover rows for a subdomain with integrated scoring.

    Args:
        ai_client: AI API client instance
        prompt_loader: PromptLoader instance
        schema_validator: SchemaValidator instance
        subdomain: Subdomain definition
        columns: Column definitions
        search_strategy: Search strategy
        target_rows: Number of rows to find (default: 7)
        scoring_model: Model for integrated scoring (default: sonar-pro)

    Returns:
        Row discovery results dictionary
    """
    stream = RowDiscoveryStream(ai_client, prompt_loader, schema_validator)
    return await stream.discover_rows(subdomain, columns, search_strategy, target_rows, scoring_model)
