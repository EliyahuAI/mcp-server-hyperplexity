#!/usr/bin/env python3
"""
QC Reviewer for table generation system.

Reviews discovered rows and decides which to keep, reject, or reprioritize.
Provides flexible quality control beyond the discovery rubric.
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class QCReviewer:
    """Quality control reviewer for discovered table rows."""

    def __init__(self, ai_client, prompt_loader, schema_validator):
        """
        Initialize QC reviewer.

        Args:
            ai_client: AI API client instance (from ../../src/shared/ai_api_client.py)
            prompt_loader: PromptLoader instance
            schema_validator: SchemaValidator instance
        """
        self.ai_client = ai_client
        self.prompt_loader = prompt_loader
        self.schema_validator = schema_validator

        logger.info("Initialized QCReviewer")

    async def review_rows(
        self,
        discovered_rows: List[Dict],
        columns: List[Dict],
        user_context: str,
        table_name: str,
        table_purpose: str = "",
        tablewide_research: str = "",
        user_requirements: str = "",
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 8000,
        min_qc_score: float = 0.5,
        max_rows: int = 50,
        min_row_count: int = 4,
        search_strategy: Dict = None,
        discovery_result: Dict = None,
        retrigger_allowed: bool = True
    ) -> Dict[str, Any]:
        """
        Review and filter discovered rows using QC criteria.

        Process:
        1. Build comprehensive prompt with all row context
        2. Call Claude Sonnet 4.5 for QC review (no web search needed)
        3. Extract approved rows (keep=true, qc_score >= threshold)
        4. Sort by qc_score descending
        5. Apply min/max row limits
        6. Return results with enhanced_data for cost tracking

        Args:
            discovered_rows: List of consolidated candidates from row discovery
            columns: List of column definitions
            user_requirements: Original user requirements/request
            table_name: Name of the table
            model: AI model to use (default: claude-sonnet-4-5)
            max_tokens: Maximum tokens for AI response
            min_qc_score: Minimum QC score to keep row (default: 0.5)
            max_rows: Maximum number of rows to return (default: 50)
            min_row_count: Minimum number of rows to guarantee (default: 4)
            search_strategy: Search strategy with requirements and domain filters (optional)
            discovery_result: Discovery result with aggregated recommendations (optional)
            retrigger_allowed: Whether to allow QC to request retrigger (default: True)

        Returns:
            Dictionary with results:
            {
                'success': bool,
                'approved_rows': List[Dict],  # Rows with keep=true, sorted by qc_score
                'rejected_rows': List[Dict],  # Rows with keep=false
                'qc_summary': Dict,  # Summary statistics
                'reviewed_rows': List[Dict],  # All reviewed rows
                'enhanced_data': Dict,  # API call metadata for cost tracking
                'processing_time': float,  # Seconds
                'error': Optional[str],
                'insufficient_rows_statement': Optional[str],  # If discovered < min_row_count
                'insufficient_rows_recommendations': Optional[List[Dict]],  # If discovered < min_row_count
                'retrigger_discovery': Optional[Dict]  # If QC requests retrigger
            }
        """
        result = {
            'success': False,
            'approved_rows': [],
            'rejected_rows': [],
            'qc_summary': {},
            'reviewed_rows': [],
            'enhanced_data': {},
            'processing_time': 0.0,
            'error': None
        }

        start_time = time.time()

        try:
            logger.info(f"Starting QC review of {len(discovered_rows)} rows")

            # Validate inputs
            if not discovered_rows:
                logger.warning("No rows to review")
                result['success'] = True
                result['qc_summary'] = {
                    'total_reviewed': 0,
                    'kept': 0,
                    'rejected': 0,
                    'promoted': 0,
                    'demoted': 0,
                    'reasoning': 'No rows provided for review'
                }
                result['processing_time'] = time.time() - start_time
                return result

            # Build prompt variables with full context
            variables = {
                'TABLE_NAME': table_name,
                'USER_CONTEXT': user_context,  # Full user request
                'TABLE_PURPOSE': table_purpose,  # What the table is for
                'USER_REQUIREMENTS': user_requirements,  # Structured requirements
                'ID_COLUMNS': self._format_id_columns(columns),  # ID fields with descriptions
                'COLUMN_DEFINITIONS': self._format_columns(columns),  # All columns
                'TABLEWIDE_RESEARCH': tablewide_research,  # Research context
                'ROW_COUNT': str(len(discovered_rows)),
                'DISCOVERED_ROWS': self._format_rows(discovered_rows, columns),
                # New variables for requirements and retrigger context
                'HARD_REQUIREMENTS': self._format_requirements_for_prompt(search_strategy, 'hard'),
                'SOFT_REQUIREMENTS': self._format_requirements_for_prompt(search_strategy, 'soft'),
                'SUBDOMAIN_RESULTS_SUMMARY': self._format_subdomain_results(discovery_result),
                'AGGREGATED_SEARCH_IMPROVEMENTS': self._format_search_improvements(discovery_result),
                'AGGREGATED_DOMAIN_RECOMMENDATIONS': self._format_domain_recommendations(discovery_result),
                'CURRENT_INCLUDED_DOMAINS': self._format_domain_list(search_strategy, 'included'),
                'CURRENT_EXCLUDED_DOMAINS': self._format_domain_list(search_strategy, 'excluded'),
                'RETRIGGER_ALLOWED': 'true' if retrigger_allowed else 'false'
            }

            logger.debug(f"Loading QC review prompt with {len(variables)} variables")
            prompt = self.prompt_loader.load_prompt('qc_review', variables)

            # Load response schema
            schema = self.schema_validator.load_schema('qc_review_response')

            logger.info(f"Calling AI API with model: {model} (no web search)")

            # Call AI API - Claude Sonnet 4.5, no web search needed
            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=model,
                max_tokens=8000,
                use_cache=True,  # Enable cache for Lambda
                max_web_searches=0,  # No web search for QC
                search_context_size='low',
                debug_name="qc_review",
                soft_schema=False  # Use hard schema for strict validation
            )

            # Check for API errors
            if 'response' not in api_response and 'error' in api_response:
                error_detail = api_response.get('error', 'Unknown error')
                logger.error(f"API call failed: {error_detail}")
                raise Exception(f"AI API call failed: {error_detail}")

            # Extract structured response
            raw_response = api_response.get('response', {})

            # Parse the structured content
            if 'choices' in raw_response and len(raw_response['choices']) > 0:
                content = raw_response['choices'][0]['message']['content']
                ai_response = json.loads(content) if isinstance(content, str) else content
            elif 'reviewed_rows' in raw_response and 'qc_summary' in raw_response:
                # Response is already structured
                ai_response = raw_response
            else:
                logger.error(f"Unexpected response structure: {json.dumps(raw_response, indent=2)[:500]}")
                raise Exception("Failed to extract structured QC review response")

            logger.debug(f"Extracted AI response keys: {list(ai_response.keys())}")

            # Defensive parsing: Handle double-encoded JSON fields
            # Sometimes AI models return fields as JSON strings instead of parsed objects
            if isinstance(ai_response.get('reviewed_rows'), str):
                logger.warning("reviewed_rows is a JSON string, parsing it...")
                try:
                    ai_response['reviewed_rows'] = json.loads(ai_response['reviewed_rows'])
                    logger.info(f"Successfully parsed reviewed_rows string into array of {len(ai_response['reviewed_rows'])} items")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse reviewed_rows JSON string: {e}")
                    raise Exception(f"reviewed_rows is a malformed JSON string: {e}")

            # Same defensive parsing for other array/object fields that might be strings
            if isinstance(ai_response.get('rejected_rows'), str):
                logger.warning("rejected_rows is a JSON string, parsing it...")
                try:
                    ai_response['rejected_rows'] = json.loads(ai_response['rejected_rows'])
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse rejected_rows JSON string: {e}")
                    # Non-critical, can continue without it
                    ai_response['rejected_rows'] = []

            if isinstance(ai_response.get('qc_summary'), str):
                logger.warning("qc_summary is a JSON string, parsing it...")
                try:
                    ai_response['qc_summary'] = json.loads(ai_response['qc_summary'])
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse qc_summary JSON string: {e}")
                    # Non-critical, set default
                    ai_response['qc_summary'] = {}

            # Validate response against schema
            validation_result = self.schema_validator.validate_ai_response(
                ai_response,
                'qc_review_response'
            )

            if not validation_result['is_valid']:
                error_msg = f"AI response validation failed: {validation_result['errors']}"
                logger.error(error_msg)
                raise Exception(error_msg)

            # Extract results
            reviewed_rows = ai_response.get('reviewed_rows', [])
            qc_summary = ai_response.get('qc_summary', {})

            # Merge QC results with original discovery data
            # QC returns: id_values, row_score, qc_score, qc_rationale, keep, priority_adjustment
            # Original has: id_values, match_score, score_breakdown, model_used, context_used, match_rationale, source_urls, etc.

            # Create mapping of discovered rows by row_id (for fast lookup)
            discovered_map = {}
            discovered_by_position = {}  # Fallback: match by position and score

            for idx, orig in enumerate(discovered_rows, 1):
                # Create row_id: row number + first ID column value
                id_vals = orig.get('id_values', {})
                first_id_value = list(id_vals.values())[0] if id_vals else 'Unknown'
                row_id = f"{idx}-{first_id_value}"
                discovered_map[row_id] = orig

                # Also store by position and score for fallback
                row_score = orig.get('match_score', 0)
                position_key = f"{idx}:{row_score:.2f}"
                discovered_by_position[position_key] = orig

            logger.info(f"Created mapping of {len(discovered_map)} discovered rows by row_id")

            merged_rows = []
            matches_found = 0
            fallback_matches = 0

            for qc_row in reviewed_rows:
                # Try matching by row_id first
                row_id = qc_row.get('row_id', '')
                original_row = discovered_map.get(row_id)

                # Fallback: Try matching by extracting row number and score
                if not original_row and row_id:
                    try:
                        # Extract row number from row_id (e.g., "1-Benchling" → "1")
                        row_num = row_id.split('-')[0]
                        qc_score_from_response = qc_row.get('row_score', 0)
                        fallback_key = f"{row_num}:{qc_score_from_response:.2f}"

                        original_row = discovered_by_position.get(fallback_key)
                        if original_row:
                            logger.info(f"[FALLBACK_MATCH] Matched row_id '{row_id}' using position {row_num} and score {qc_score_from_response:.2f}")
                            fallback_matches += 1
                    except Exception as e:
                        logger.warning(f"[FALLBACK_MATCH] Failed to extract position from row_id '{row_id}': {e}")

                if original_row:
                    # Merge: start with original, overlay QC fields
                    # Defensive check: ensure original_row is a dict before calling .copy()
                    if isinstance(original_row, dict):
                        merged = original_row.copy()
                    else:
                        logger.error(f"original_row is not a dict: {type(original_row).__name__} - {original_row}")
                        merged = {}

                    qc_score = qc_row.get('qc_score', 0)
                    row_score = qc_row.get('row_score', merged.get('match_score', 0))

                    # If qc_rationale not provided and scores match, generate default
                    qc_rationale = qc_row.get('qc_rationale', '')
                    if not qc_rationale and abs(qc_score - row_score) < 0.01:
                        qc_rationale = "QC confirms discovery assessment"

                    merged['row_score'] = row_score  # Set row_score for frontend display
                    merged['qc_score'] = qc_score
                    merged['qc_rationale'] = qc_rationale
                    merged['keep'] = qc_row.get('keep', False)
                    merged['priority_adjustment'] = qc_row.get('priority_adjustment', 'none')
                    merged['row_id'] = row_id  # Preserve row_id for tracking
                    merged_rows.append(merged)
                    matches_found += 1
                else:
                    # QC row has no matching original (shouldn't happen)
                    logger.warning(f"QC row has no matching original: row_id={row_id}")
                    merged_rows.append(qc_row)

            if fallback_matches > 0:
                logger.info(f"Merged {matches_found}/{len(reviewed_rows)} QC rows with original metadata ({fallback_matches} fallback matches)")
            else:
                logger.info(f"Merged {matches_found}/{len(reviewed_rows)} QC rows with original metadata")

            # Filter approved rows (keep=true, qc_score >= threshold)
            approved_rows = [
                row for row in merged_rows
                if row.get('keep', False) and row.get('qc_score', 0) >= min_qc_score
            ]

            # Separate rejected rows for potential promotion
            rejected_rows_pool = [
                row for row in merged_rows
                if not row.get('keep', False)
            ]

            # Check if we need to apply minimum row guarantee
            minimum_guarantee_applied = False
            promoted_count = 0

            if len(approved_rows) < min_row_count and rejected_rows_pool:
                # Sort rejected rows by qc_score descending
                rejected_sorted = sorted(
                    rejected_rows_pool,
                    key=lambda x: x.get('qc_score', 0),
                    reverse=True
                )

                # Calculate how many we need to promote
                needed = min_row_count - len(approved_rows)
                to_promote = rejected_sorted[:needed]

                # Promote rejected rows to demoted status
                for row in to_promote:
                    row['keep'] = True
                    row['priority_adjustment'] = 'demote'
                    # Add a note about promotion in qc_rationale
                    existing_rationale = row.get('qc_rationale', '')
                    if existing_rationale:
                        row['qc_rationale'] = f"{existing_rationale} [Promoted to meet minimum row count]"
                    else:
                        row['qc_rationale'] = "Promoted to meet minimum row count"
                    approved_rows.append(row)
                    promoted_count += 1

                minimum_guarantee_applied = True
                logger.info(f"[MIN_GUARANTEE] Promoted {promoted_count} rejected rows to meet minimum of {min_row_count}")

            # Sort approved rows by priority tier, then by qc_score within each tier
            # Priority order: promote > none > demote
            priority_order = {'promote': 0, 'none': 1, 'demote': 2}

            approved_rows_sorted = sorted(
                approved_rows,
                key=lambda x: (
                    priority_order.get(x.get('priority_adjustment', 'none'), 1),
                    -x.get('qc_score', 0)  # Negative for descending
                ),
            )

            # Apply max_rows limit
            final_approved = approved_rows_sorted[:max_rows]

            # Track rows that were filtered out by limits
            filtered_by_limit = len(approved_rows_sorted) - len(final_approved)
            if filtered_by_limit > 0:
                logger.info(f"Filtered {filtered_by_limit} rows due to max_rows limit ({max_rows})")

            # Check for insufficient rows scenario (discovered < min_row_count)
            insufficient_rows = len(discovered_rows) < min_row_count
            insufficient_rows_statement = ai_response.get('insufficient_rows_statement', '')
            insufficient_rows_recommendations = ai_response.get('insufficient_rows_recommendations', [])

            # Update qc_summary with new fields
            qc_summary['minimum_guarantee_applied'] = minimum_guarantee_applied
            qc_summary['insufficient_rows'] = insufficient_rows

            # Track promoted count from minimum guarantee (different from AI's 'promoted' which is priority_adjustment)
            if promoted_count > 0:
                qc_summary['minimum_guarantee_promoted'] = promoted_count

            # Count demoted rows in final output
            demoted_count = sum(1 for row in final_approved if row.get('priority_adjustment') == 'demote')
            if 'demoted' not in qc_summary:
                qc_summary['demoted'] = demoted_count

            # Calculate final rejected rows (all merged rows that weren't approved)
            final_rejected = [row for row in merged_rows if not row.get('keep', False)]

            # Build successful result
            result['success'] = True
            result['approved_rows'] = final_approved
            result['rejected_rows'] = final_rejected
            result['qc_summary'] = qc_summary
            result['reviewed_rows'] = reviewed_rows

            # Add insufficient rows details if applicable
            if insufficient_rows:
                result['insufficient_rows_statement'] = insufficient_rows_statement
                result['insufficient_rows_recommendations'] = insufficient_rows_recommendations
                logger.warning(
                    f"[INSUFFICIENT_ROWS] Only {len(discovered_rows)} rows discovered (< {min_row_count}). "
                    f"Statement: {insufficient_rows_statement[:100]}..."
                )

            # Add retrigger_discovery if present in AI response
            retrigger_discovery = ai_response.get('retrigger_discovery', {})
            if retrigger_discovery and retrigger_discovery.get('should_retrigger', False):
                result['retrigger_discovery'] = retrigger_discovery
                logger.info(
                    f"[RETRIGGER_REQUESTED] QC requested retrigger: {retrigger_discovery.get('reason', 'No reason provided')}"
                )

            # Capture enhanced_data for cost tracking
            enhanced_data = api_response.get('enhanced_data', {})
            result['enhanced_data'] = enhanced_data
            result['call_description'] = "QC Review - Filtering and Prioritizing Rows"
            result['model_used'] = model

            # Include cost information
            if enhanced_data:
                costs = enhanced_data.get('costs', {})
                result['cost'] = costs.get('actual', {}).get('total_cost', 0.0)
                logger.info(f"QC review cost from enhanced_data: ${result['cost']:.4f}")
            else:
                # Fallback: Calculate cost from token_usage
                logger.warning("No enhanced_data in API response, calculating cost from token_usage")
                token_usage = api_response.get('token_usage', {})
                input_tokens = token_usage.get('input_tokens', 0)
                output_tokens = token_usage.get('output_tokens', 0)

                # Claude Sonnet 4.5 pricing: $3/MTok input, $15/MTok output
                cost = (input_tokens / 1_000_000 * 3.0) + (output_tokens / 1_000_000 * 15.0)
                result['cost'] = cost
                logger.info(f"QC review cost calculated: ${cost:.4f} (input={input_tokens}, output={output_tokens})")

            # Calculate processing time
            result['processing_time'] = time.time() - start_time

            logger.info(
                f"QC review completed successfully. "
                f"Reviewed: {len(reviewed_rows)}, "
                f"Approved: {len(final_approved)}, "
                f"Rejected: {len(final_rejected)}, "
                f"Time: {result['processing_time']:.1f}s"
            )

            # Log QC summary details
            self._log_qc_summary(qc_summary, len(final_approved))

            # Log token usage if available
            if 'token_usage' in api_response:
                self._log_token_usage(api_response['token_usage'])

        except Exception as e:
            error_msg = f"Error during QC review: {str(e)}"
            logger.error(error_msg)

            # Check if this was a refusal error - skip QC and return all rows with warning
            if "[ALL_MODELS_REFUSED]" in str(e) or "[REFUSAL]" in str(e):
                logger.warning("[QC_REFUSAL] AI provider refused QC review - bypassing QC and returning all rows sorted by quality")

                # Sort discovered rows by match_score descending
                sorted_rows = sorted(
                    discovered_rows,
                    key=lambda x: x.get('match_score', 0),
                    reverse=True
                )

                # Mark all rows as kept (bypass QC)
                for idx, row in enumerate(sorted_rows, 1):
                    row['keep'] = True
                    row['qc_score'] = row.get('match_score', 0)  # Use discovery score as QC score
                    row['qc_rationale'] = 'QC bypassed - using discovery score'
                    row['priority_adjustment'] = 'none'
                    # Ensure row_id is set
                    if 'row_id' not in row:
                        id_vals = row.get('id_values', {})
                        first_id_value = list(id_vals.values())[0] if id_vals else 'Unknown'
                        row['row_id'] = f"{idx}-{first_id_value}"

                # Apply max_rows limit
                final_rows = sorted_rows[:max_rows] if max_rows else sorted_rows

                # Build successful result with warning
                result['success'] = True
                result['approved_rows'] = final_rows
                result['rejected_rows'] = []
                result['reviewed_rows'] = final_rows  # All rows passed through
                result['qc_bypassed'] = True
                result['warning'] = {
                    'type': 'qc_refused',
                    'title': 'Automated Quality Review Unavailable',
                    'message': 'The AI provider declined to perform quality review on this table. '
                               'All discovered rows have been included, sorted by discovery quality score. '
                               'You may want to manually review the results.',
                    'rows_included': len(final_rows),
                    'reason': 'AI safety filters may have been triggered when reviewing this type of content'
                }
                result['qc_summary'] = {
                    'total_reviewed': len(discovered_rows),
                    'kept': len(final_rows),
                    'rejected': 0,
                    'promoted': 0,
                    'demoted': 0,
                    'reasoning': 'QC bypassed due to AI provider refusal - all rows included sorted by discovery score'
                }
                result['processing_time'] = time.time() - start_time

                logger.info(f"[QC_BYPASSED] Returning {len(final_rows)} rows without QC filtering")

            else:
                # Non-refusal error - actual failure
                result['error'] = error_msg
                result['processing_time'] = time.time() - start_time

        return result

    def _format_requirements_for_prompt(self, search_strategy: Dict, type_filter: str) -> str:
        """
        Format requirements as bullet list for prompt.

        Args:
            search_strategy: Search strategy dictionary with requirements
            type_filter: 'hard' or 'soft' to filter requirements by type

        Returns:
            Formatted requirements string (bullet list) or "(None)" if not available
        """
        if not search_strategy:
            return "(Not available)"

        # Defensive check: ensure search_strategy is a dict
        if not isinstance(search_strategy, dict):
            logger.warning(f"search_strategy is not a dict: {type(search_strategy).__name__}")
            return "(Not available)"

        requirements = search_strategy.get('requirements', [])
        filtered = [req for req in requirements if req.get('type') == type_filter]

        if not filtered:
            return "(None)"

        lines = []
        for req in filtered:
            requirement_text = req.get('requirement', '')
            rationale = req.get('rationale', '')
            if requirement_text:
                line = f"- {requirement_text}"
                if rationale:
                    line += f" (Rationale: {rationale})"
                lines.append(line)

        return '\n'.join(lines) if lines else "(None)"

    def _format_subdomain_results(self, discovery_result: Dict) -> str:
        """
        Format subdomain names with row counts from discovery result.
        For subdomains with 0 results, include no_matches_reason from the LAST round.

        Args:
            discovery_result: Discovery result dictionary with stream_results or subdomain_results

        Returns:
            Formatted subdomain summary or "(Not available)"
        """
        if not discovery_result:
            return "(Not available)"

        # Defensive check: ensure discovery_result is a dict
        if not isinstance(discovery_result, dict):
            logger.warning(f"discovery_result is not a dict: {type(discovery_result).__name__}")
            return "(Not available)"

        # Try stream_results first (current key), fall back to subdomain_results (legacy)
        subdomain_results = discovery_result.get('stream_results', discovery_result.get('subdomain_results', []))
        if not subdomain_results:
            return "(No subdomain results)"

        lines = []
        for subdomain_result in subdomain_results:
            subdomain_name = subdomain_result.get('subdomain', 'Unknown')
            candidates = subdomain_result.get('candidates', [])
            row_count = len(candidates)

            # Format subdomain with row count
            line = f"- \"{subdomain_name}\" ({row_count} results)"

            # If 0 results, include no_matches_reason from LAST round
            if row_count == 0:
                no_matches_reason = subdomain_result.get('no_matches_reason', '')
                if no_matches_reason:
                    line += f" - Reason: {no_matches_reason}"
                else:
                    line += " - Reason: Not provided"

            lines.append(line)

        return '\n'.join(lines) if lines else "(No subdomain results)"

    def _format_search_improvements(self, discovery_result: Dict) -> str:
        """
        Format aggregated search improvements from discovery result.

        Args:
            discovery_result: Discovery result dictionary with search improvements

        Returns:
            Formatted search improvements or "(Not available)"
        """
        if not discovery_result:
            return "(Not available)"

        # Defensive check: ensure discovery_result is a dict
        if not isinstance(discovery_result, dict):
            logger.warning(f"discovery_result is not a dict: {type(discovery_result).__name__}")
            return "(Not available)"

        # Try stream_results first (current key), fall back to subdomain_results (legacy)
        subdomain_results = discovery_result.get('stream_results', discovery_result.get('subdomain_results', []))
        if not subdomain_results:
            return "(No search improvements)"

        formatted_items = []
        for subdomain_result in subdomain_results:
            subdomain_name = subdomain_result.get('subdomain', 'Unknown')
            improvements = subdomain_result.get('search_improvements', [])

            for improvement in improvements:
                # improvement is a STRING according to schema, not a dict
                if isinstance(improvement, str) and improvement.strip():
                    formatted_items.append({
                        'subdomain': subdomain_name,
                        'improvement': improvement
                    })
                elif isinstance(improvement, dict):
                    # Legacy support if some are dicts (fallback)
                    improvement_text = improvement.get('improvement', improvement.get('recommendation', str(improvement)))
                    if improvement_text:
                        formatted_items.append({
                            'subdomain': subdomain_name,
                            'improvement': improvement_text
                        })
                else:
                    logger.warning(f"Skipping invalid improvement: {type(improvement).__name__} - {improvement}")

        if not formatted_items:
            return "(No search improvements)"

        # Format as numbered list with subdomain context
        lines = []
        for idx, item in enumerate(formatted_items, 1):
            lines.append(f"{idx}. [{item['subdomain']}] {item['improvement']}")

        return '\n'.join(lines) if lines else "(No search improvements)"

    def _format_domain_recommendations(self, discovery_result: Dict) -> str:
        """
        Format aggregated domain filtering recommendations from discovery result.

        Args:
            discovery_result: Discovery result dictionary with domain recommendations

        Returns:
            Formatted domain recommendations or "(Not available)"
        """
        if not discovery_result:
            return "(Not available)"

        # Defensive check: ensure discovery_result is a dict
        if not isinstance(discovery_result, dict):
            logger.warning(f"discovery_result is not a dict: {type(discovery_result).__name__}")
            return "(Not available)"

        # Try stream_results first (current key), fall back to subdomain_results (legacy)
        subdomain_results = discovery_result.get('stream_results', discovery_result.get('subdomain_results', []))
        if not subdomain_results:
            return "(No domain recommendations)"

        all_recommendations = []
        for subdomain_result in subdomain_results:
            subdomain_name = subdomain_result.get('subdomain', 'Unknown')
            domain_rec = subdomain_result.get('domain_filtering_recommendations', {})

            # Defensive check: ensure domain_rec is a dict before processing
            if isinstance(domain_rec, dict) and domain_rec and any(domain_rec.values()):
                recommendation_with_context = domain_rec.copy()
                recommendation_with_context['from_subdomain'] = subdomain_name
                all_recommendations.append(recommendation_with_context)
            elif domain_rec and not isinstance(domain_rec, dict):
                logger.warning(f"Skipping non-dict domain recommendation: {type(domain_rec).__name__} - {domain_rec}")

        if not all_recommendations:
            return "(No domain recommendations)"

        lines = []
        for idx, rec in enumerate(all_recommendations, 1):
            from_subdomain = rec.get('from_subdomain', 'Unknown')
            add_to_included = rec.get('add_to_included', [])
            add_to_excluded = rec.get('add_to_excluded', [])
            reasoning = rec.get('reasoning', '')

            lines.append(f"{idx}. [From: {from_subdomain}]")
            if add_to_included:
                lines.append(f"   Add to included: {', '.join(add_to_included)}")
            if add_to_excluded:
                lines.append(f"   Add to excluded: {', '.join(add_to_excluded)}")
            if reasoning:
                lines.append(f"   Reasoning: {reasoning}")
            lines.append("")  # Blank line between recommendations

        return '\n'.join(lines) if lines else "(No domain recommendations)"

    def _format_domain_list(self, search_strategy: Dict, domain_type: str) -> str:
        """
        Format domain list as comma-separated string or "(None)".

        Args:
            search_strategy: Search strategy dictionary with domain filters
            domain_type: 'included' or 'excluded' to specify which domain list

        Returns:
            Formatted domain list or "(None)"
        """
        if not search_strategy:
            return "(Not available)"

        # Defensive check: ensure search_strategy is a dict
        if not isinstance(search_strategy, dict):
            logger.warning(f"search_strategy is not a dict: {type(search_strategy).__name__}")
            return "(Not available)"

        if domain_type == 'included':
            domains = search_strategy.get('default_included_domains', [])
        elif domain_type == 'excluded':
            domains = search_strategy.get('default_excluded_domains', [])
        else:
            return "(Invalid domain type)"

        if not domains:
            return "(None)"

        return ', '.join(domains)

    def _format_id_columns(self, columns: List[Dict]) -> str:
        """
        Format ID column definitions for prompt.

        Args:
            columns: List of column definition dictionaries

        Returns:
            Formatted ID columns string with descriptions
        """
        id_cols = [col for col in columns if col.get('is_identification')]
        lines = []
        for col in id_cols:
            col_name = col.get('name', 'Unknown')
            col_desc = col.get('description', 'No description')
            lines.append(f"- **{col_name}**: {col_desc}")

        return '\n'.join(lines) if lines else "No ID columns defined"

    def _format_columns(self, columns: List[Dict]) -> str:
        """
        Format all column definitions for prompt.

        Args:
            columns: List of column definition dictionaries

        Returns:
            Formatted column definitions string
        """
        lines = []
        for col in columns:
            col_name = col.get('name', 'Unknown')
            col_desc = col.get('description', 'No description')
            col_type = "ID" if col.get('is_identification') else "CRITICAL"
            val_strat = col.get('validation_strategy', '')

            line = f"- **{col_name}** ({col_type}): {col_desc}"
            if val_strat:
                line += f"\n  Validation: {val_strat}"
            lines.append(line)

        return '\n'.join(lines)

    def _format_rows(self, rows: List[Dict], columns: List[Dict]) -> str:
        """
        Format discovered rows for prompt with row_id.

        Args:
            rows: List of discovered row dictionaries
            columns: List of column definition dictionaries

        Returns:
            Formatted rows string
        """
        # Calculate total research columns (non-ID columns)
        total_research_cols = len([c for c in columns if not c.get('is_identification')])

        lines = []
        for idx, row in enumerate(rows, 1):
            id_values = row.get('id_values', {})
            row_score = row.get('match_score', 0)
            match_rationale = row.get('match_rationale', '')
            found_by = row.get('found_by_models', [])
            source_subdomain = row.get('source_subdomain', 'Unknown')

            # Create row_id: row number + first ID column value
            first_id_value = list(id_values.values())[0] if id_values else 'Unknown'
            row_id = f"{idx}-{first_id_value}"

            # Format full ID values for context
            id_str = ', '.join(f"{k}: {v}" for k, v in id_values.items())

            lines.append(f"\n**Row {idx}:**")
            lines.append(f"- **row_id (use this in your response):** `{row_id}`")
            lines.append(f"- Full ID: {id_str}")
            lines.append(f"- Discovery Score: {row_score:.2f}")
            lines.append(f"- Rationale: {match_rationale}")
            if found_by:
                lines.append(f"- Found by: {', '.join(found_by)}")
            lines.append(f"- Source: {source_subdomain}")

            # Show populated research columns count only (not values)
            research_values = row.get('research_values', {})
            populated_columns = row.get('populated_columns', [])

            if research_values or populated_columns:
                # Count populated research columns (exclude ID columns)
                if research_values:
                    populated_count = len(research_values)
                else:
                    populated_count = len([c for c in populated_columns if c not in id_values])

                # Show simple ratio: X/Y columns populated
                if populated_count > 0:
                    lines.append(f"- Research Data: {populated_count}/{total_research_cols} columns populated")

        return '\n'.join(lines)

    def _log_qc_summary(self, qc_summary: Dict, final_approved: int) -> None:
        """
        Log QC summary statistics.

        Args:
            qc_summary: QC summary dictionary
            final_approved: Final number of approved rows after limits
        """
        total = qc_summary.get('total_reviewed', 0)
        kept = qc_summary.get('kept', 0)
        rejected = qc_summary.get('rejected', 0)
        promoted = qc_summary.get('promoted', 0)
        demoted = qc_summary.get('demoted', 0)
        min_guarantee_promoted = qc_summary.get('minimum_guarantee_promoted', 0)
        reasoning = qc_summary.get('reasoning', '')

        log_parts = [
            f"QC Summary - Total: {total}",
            f"Kept: {kept}",
            f"Rejected: {rejected}",
            f"Promoted: {promoted}",
            f"Demoted: {demoted}"
        ]

        if min_guarantee_promoted > 0:
            log_parts.append(f"MinGuarantee Promoted: {min_guarantee_promoted}")

        log_parts.append(f"Final (after limits): {final_approved}")

        logger.info(", ".join(log_parts))

        if reasoning:
            logger.info(f"QC Reasoning: {reasoning}")

    def _log_token_usage(self, token_usage: Dict) -> None:
        """
        Log token usage statistics.

        Args:
            token_usage: Token usage dictionary
        """
        input_tokens = token_usage.get('input_tokens', 0)
        output_tokens = token_usage.get('output_tokens', 0)
        total_tokens = input_tokens + output_tokens

        logger.info(
            f"Token usage - Input: {input_tokens}, "
            f"Output: {output_tokens}, "
            f"Total: {total_tokens}"
        )

    def get_qc_summary_text(self, result: Dict[str, Any]) -> str:
        """
        Generate a human-readable QC summary.

        Args:
            result: Result from review_rows() method

        Returns:
            Formatted summary string
        """
        qc_summary = result.get('qc_summary', {})
        approved_rows = result.get('approved_rows', [])
        rejected_rows = result.get('rejected_rows', [])

        lines = []
        lines.append("=== QC Review Summary ===")
        lines.append("")
        lines.append(f"Total reviewed: {qc_summary.get('total_reviewed', 0)}")
        lines.append(f"Kept: {qc_summary.get('kept', 0)}")
        lines.append(f"Rejected: {qc_summary.get('rejected', 0)}")
        lines.append(f"Promoted: {qc_summary.get('promoted', 0)}")
        lines.append(f"Demoted: {qc_summary.get('demoted', 0)}")
        lines.append(f"Final approved (after limits): {len(approved_rows)}")
        lines.append(f"Processing time: {result.get('processing_time', 0):.1f}s")
        lines.append("")

        reasoning = qc_summary.get('reasoning', '')
        if reasoning:
            lines.append(f"Reasoning: {reasoning}")
            lines.append("")

        if approved_rows:
            lines.append("Top 5 approved rows:")
            for idx, row in enumerate(approved_rows[:5], 1):
                id_values = row.get('id_values', {})
                qc_score = row.get('qc_score', 0)
                qc_rationale = row.get('qc_rationale', '')
                priority_adj = row.get('priority_adjustment', 'none')

                # Format ID values
                id_str = ', '.join(f"{k}={v}" for k, v in id_values.items())
                lines.append(f"  {idx}. {id_str}")
                lines.append(f"     QC Score: {qc_score:.2f}")
                lines.append(f"     Rationale: {qc_rationale}")
                if priority_adj != 'none':
                    lines.append(f"     Priority: {priority_adj.upper()}")
                lines.append("")

        if rejected_rows:
            lines.append(f"Rejected rows ({len(rejected_rows)}):")
            for idx, row in enumerate(rejected_rows[:3], 1):
                id_values = row.get('id_values', {})
                rejection_reason = row.get('rejection_reason', '')

                id_str = ', '.join(f"{k}={v}" for k, v in id_values.items())
                lines.append(f"  {idx}. {id_str}")
                lines.append(f"     Reason: {rejection_reason}")
                lines.append("")

        return '\n'.join(lines)
