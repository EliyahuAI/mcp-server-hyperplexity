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
        retrigger_allowed: bool = True,
        column_result: Dict = None,
        target_row_count: int = 0
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

            # Extract prepopulated rows from column_definition (if available)
            prepopulated_markdown = ""
            prepopulated_citations = {}
            pre_row_count = 0
            if column_result:
                prepopulated_markdown = column_result.get('prepopulated_rows_markdown', '')
                prepopulated_citations = column_result.get('citations', {})
                # Count rows in markdown (lines minus header and separator)
                if prepopulated_markdown:
                    # Count actual table rows (lines starting with | but not |---)
                    table_rows = [l for l in prepopulated_markdown.split('\n') if l.strip().startswith('|') and not l.strip().startswith('|---')]
                    pre_row_count = max(0, len(table_rows) - 1)  # Subtract header row
                    # Debug: Log the markdown length and row count
                    logger.info(f"[QC_PREPOPULATED] Markdown length: {len(prepopulated_markdown)}, table rows: {len(table_rows)}, data rows (pre_row_count): {pre_row_count}")
                    logger.info(f"[QC_PREPOPULATED] First 500 chars: {prepopulated_markdown[:500]}")

            # Add P-prefixed row_ids to prepopulated markdown for QC to reference
            if prepopulated_markdown:
                prepopulated_markdown = self._add_row_ids_to_prepopulated_markdown(prepopulated_markdown, columns)

            if not prepopulated_markdown:
                prepopulated_markdown = "(No pre-existing rows from column_definition)"

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
                # Prepopulated rows from column_definition
                'PRE_ROW_COUNT': str(pre_row_count),
                'PREPOPULATED_ROWS_MARKDOWN': prepopulated_markdown,
                'PREPOPULATED_CITATIONS': json.dumps(prepopulated_citations, indent=2) if prepopulated_citations else '(None)',
                # New variables for requirements and retrigger context
                'ID_COLUMNS': self._format_id_columns(columns),
                'HARD_REQUIREMENTS': self._format_requirements_for_prompt(search_strategy, 'hard'),
                'SOFT_REQUIREMENTS': self._format_requirements_for_prompt(search_strategy, 'soft'),
                'SUBDOMAIN_RESULTS_SUMMARY': self._format_subdomain_results(discovery_result),
                'AGGREGATED_SEARCH_IMPROVEMENTS': self._format_search_improvements(discovery_result),
                'AGGREGATED_DOMAIN_RECOMMENDATIONS': self._format_domain_recommendations(discovery_result),
                'CURRENT_INCLUDED_DOMAINS': self._format_domain_list(search_strategy, 'included'),
                'CURRENT_EXCLUDED_DOMAINS': self._format_domain_list(search_strategy, 'excluded'),
                'RETRIGGER_ALLOWED': 'true' if retrigger_allowed else 'false',
                'MIN_ROW_COUNT': str(min_row_count),  # Configurable threshold from config
                'TARGET_ROW_COUNT': str(target_row_count) if target_row_count > 0 else 'not specified'
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

            # Log the raw response structure for debugging
            logger.info(f"[QC_RESPONSE] Raw response keys: {list(raw_response.keys())}")

            # Parse the structured content
            if 'choices' in raw_response and len(raw_response['choices']) > 0:
                content = raw_response['choices'][0]['message']['content']
                ai_response = json.loads(content) if isinstance(content, str) else content
                logger.info(f"[QC_RESPONSE] Parsed from choices format, keys={list(ai_response.keys())}")

                # Check if parsed content is in simplified format (has 'action' but not 'reviewed_rows')
                # and needs conversion to old format
                if 'action' in ai_response and 'reviewed_rows' not in ai_response:
                    action = ai_response.get('action', 'unknown')
                    remove_count = len(ai_response.get('remove_row_ids', []) or [])
                    logger.info(f"[QC_RESPONSE] Simplified format inside choices: action={action}, remove_row_ids={remove_count}")
                    ai_response = self._convert_simplified_response(ai_response, discovered_rows)
                elif 'reviewed_rows' in ai_response:
                    logger.info(f"[QC_RESPONSE] Old format inside choices: reviewed_rows={len(ai_response.get('reviewed_rows', []))}")
                else:
                    logger.warning(f"[QC_RESPONSE] Unknown format inside choices, keys={list(ai_response.keys())}")
            elif 'action' in raw_response:
                # New simplified format - convert to old format for backward compatibility
                action = raw_response.get('action', 'unknown')
                remove_count = len(raw_response.get('remove_row_ids', []) or [])
                logger.info(f"[QC_RESPONSE] Simplified format: action={action}, remove_row_ids={remove_count}")
                ai_response = self._convert_simplified_response(raw_response, discovered_rows)
            elif 'reviewed_rows' in raw_response and 'qc_summary' in raw_response:
                # Old format - already structured
                ai_response = raw_response
                logger.info(f"[QC_RESPONSE] Old format: reviewed_rows={len(raw_response.get('reviewed_rows', []))}")
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

            # Additional action-specific validation (since schema is now flat)
            self._validate_qc_response(ai_response)

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

            # Check if QC provided explicit keep list with ordering
            keep_row_ids_in_order = ai_response.get('keep_row_ids_in_order', None)

            if keep_row_ids_in_order and isinstance(keep_row_ids_in_order, list) and len(keep_row_ids_in_order) > 0:
                # Use QC's explicit keep list - this handles BOTH filtering AND ordering
                logger.info(f"[QC_ORDER] Using QC's keep_row_ids_in_order ({len(keep_row_ids_in_order)} rows to keep)")

                # Create a mapping of row_id to row for fast lookup
                all_rows_by_id = {}
                for row in merged_rows:
                    row_id = row.get('row_id', '')
                    all_rows_by_id[row_id] = row
                    # Also map by just the entity name part (after the number prefix)
                    if '-' in row_id:
                        entity_name = row_id.split('-', 1)[1]
                        all_rows_by_id[entity_name] = row

                # Build ordered list of rows to keep
                approved_rows_sorted = []
                seen_ids = set()
                for keep_id in keep_row_ids_in_order:
                    if keep_id in all_rows_by_id and keep_id not in seen_ids:
                        row = all_rows_by_id[keep_id]
                        row['keep'] = True  # Mark as kept
                        approved_rows_sorted.append(row)
                        seen_ids.add(keep_id)
                        # Also mark the full row_id as seen if we matched by entity name
                        seen_ids.add(row.get('row_id', ''))
                    else:
                        if keep_id not in seen_ids:
                            logger.warning(f"[QC_ORDER] Row '{keep_id}' in keep list but not found in merged rows")

                # Log removal reasons if provided
                removal_reasons = ai_response.get('removal_reasons', {})
                if removal_reasons:
                    for row_id, reason in removal_reasons.items():
                        logger.info(f"[QC_REMOVED] {row_id}: {reason}")

                # Update approved_rows to only include kept rows
                approved_rows = approved_rows_sorted

            else:
                # No explicit keep list - keep all approved rows in original order
                logger.info(f"[QC_ORDER] No keep_row_ids_in_order, keeping all {len(approved_rows)} approved rows in original order")
                approved_rows_sorted = approved_rows  # Keep original order

            # Extract remove_prepopulated_row_ids from QC response
            remove_prepopulated_row_ids = ai_response.get('remove_prepopulated_row_ids', None)
            if remove_prepopulated_row_ids and isinstance(remove_prepopulated_row_ids, list):
                logger.info(f"[QC_PREPOPULATED_REMOVAL] QC flagged {len(remove_prepopulated_row_ids)} pre-existing rows for removal: {remove_prepopulated_row_ids}")
                # Log removal reasons for prepopulated rows
                removal_reasons = ai_response.get('removal_reasons', {}) or {}
                for row_id in remove_prepopulated_row_ids:
                    reason = removal_reasons.get(row_id, 'Removed by QC')
                    logger.info(f"[QC_PREPOPULATED_REMOVED] {row_id}: {reason}")

            # Apply max_rows limit
            final_approved = approved_rows_sorted[:max_rows]

            # Track rows that were filtered out by limits
            filtered_by_limit = len(approved_rows_sorted) - len(final_approved)
            if filtered_by_limit > 0:
                logger.info(f"Filtered {filtered_by_limit} rows due to max_rows limit ({max_rows})")

            # Check for insufficient rows scenario
            # IMPORTANT: Consider BOTH prepopulated rows AND discovered rows (after QC approval)
            # Adjust pre_row_count for QC-requested removals
            adjusted_pre_count = pre_row_count
            if remove_prepopulated_row_ids and isinstance(remove_prepopulated_row_ids, list):
                adjusted_pre_count = max(0, pre_row_count - len(remove_prepopulated_row_ids))
            total_rows = adjusted_pre_count + len(final_approved)
            insufficient_rows = total_rows < min_row_count
            insufficient_rows_statement = ai_response.get('insufficient_rows_statement', '')
            insufficient_rows_recommendations = ai_response.get('insufficient_rows_recommendations', [])

            logger.info(
                f"[INSUFFICIENT_CHECK] Prepopulated: {pre_row_count} (adjusted: {adjusted_pre_count}), "
                f"QC approved: {len(final_approved)}, Total: {total_rows}, "
                f"Min required: {min_row_count}, Insufficient: {insufficient_rows}"
            )

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
            result['prepopulated_row_count'] = pre_row_count  # For execution to know total
            result['remove_prepopulated_row_ids'] = remove_prepopulated_row_ids  # For execution to filter initial_rows

            # Add insufficient rows details if applicable
            if insufficient_rows:
                result['insufficient_rows_statement'] = insufficient_rows_statement
                result['insufficient_rows_recommendations'] = insufficient_rows_recommendations
                logger.warning(
                    f"[INSUFFICIENT_ROWS] Only {total_rows} total rows ({pre_row_count} prepopulated + "
                    f"{len(final_approved)} QC approved) < {min_row_count} required. "
                    f"Statement: {insufficient_rows_statement[:100] if insufficient_rows_statement else 'N/A'}..."
                )

            # Add retrigger_discovery if present in AI response
            retrigger_discovery = ai_response.get('retrigger_discovery', {})
            if retrigger_discovery and retrigger_discovery.get('should_retrigger', False):
                result['retrigger_discovery'] = retrigger_discovery
                logger.info(
                    f"[RETRIGGER_REQUESTED] QC requested retrigger: {retrigger_discovery.get('reason', 'No reason provided')}"
                )

            # Add recovery_decision if present in AI response (for restructure/give_up decisions)
            recovery_decision = ai_response.get('recovery_decision', {})
            if recovery_decision:
                result['recovery_decision'] = recovery_decision
                logger.info(
                    f"[RECOVERY_DECISION] QC provided recovery decision: {recovery_decision.get('decision', 'unknown')}"
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

    def _validate_qc_response(self, response: Dict) -> None:
        """
        Validate QC response fields match action type.
        Since the schema is now flat (no allOf/if/then), we validate action-specific
        requirements here in code.

        New format: rows are KEPT BY DEFAULT, only remove_row_ids specified.

        Args:
            response: Parsed QC response

        Raises:
            ValueError: If response doesn't match action requirements
        """
        action = response.get('action')

        if action == 'pass':
            if response.get('overall_score') is None:
                raise ValueError("overall_score required for pass action")
            # remove_row_ids should be null or empty for pass action
            if response.get('remove_row_ids'):
                logger.warning("remove_row_ids should be null/empty for pass action, treating as filter")

        elif action == 'filter':
            if response.get('overall_score') is None:
                raise ValueError("overall_score required for filter action")
            # Filter action needs at least one filtering mechanism:
            # - keep_row_ids_in_order (filter/reorder discovered rows)
            # - remove_row_ids (legacy format)
            # - remove_prepopulated_row_ids (filter pre-existing rows)
            has_discovered_filter = bool(response.get('keep_row_ids_in_order')) or bool(response.get('remove_row_ids'))
            has_prepopulated_filter = bool(response.get('remove_prepopulated_row_ids'))
            if not has_discovered_filter and not has_prepopulated_filter:
                raise ValueError("filter action requires at least one of: keep_row_ids_in_order, remove_row_ids, or remove_prepopulated_row_ids")

        elif action == 'retrigger_discovery':
            if response.get('overall_score') is None:
                raise ValueError("overall_score required for retrigger_discovery action")
            if response.get('new_subdomains') is None:
                raise ValueError("new_subdomains required for retrigger_discovery action")
            if response.get('discovery_guidance') is None:
                raise ValueError("discovery_guidance required for retrigger_discovery action")

        elif action == 'restructure':
            # overall_score should be null for restructure
            if response.get('restructuring_guidance') is None:
                raise ValueError("restructuring_guidance required for restructure action")
            if response.get('user_message') is None:
                raise ValueError("user_message required for restructure action")

        logger.info(f"[QC] Action-specific validation passed for action: {action}")

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
        # Check both importance='ID' and is_identification for compatibility
        id_cols = [
            col for col in columns
            if col.get('importance', '').upper() == 'ID' or col.get('is_identification')
        ]
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
            # Check both importance='ID' and is_identification for compatibility
            is_id = col.get('importance', '').upper() == 'ID' or col.get('is_identification')
            col_type = "ID" if is_id else "CRITICAL"
            val_strat = col.get('validation_strategy', '')

            line = f"- **{col_name}** ({col_type}): {col_desc}"
            if val_strat:
                line += f"\n  Validation: {val_strat}"
            lines.append(line)

        return '\n'.join(lines)

    def _format_rows(self, rows: List[Dict], columns: List[Dict]) -> str:
        """
        Format discovered rows as a markdown table for the prompt.

        Args:
            rows: List of discovered row dictionaries
            columns: List of column definition dictionaries

        Returns:
            Formatted markdown table string
        """
        if not rows:
            return "(No discovered rows)"

        # Get ID column names - check both importance='ID' and is_identification for compatibility
        id_column_names = [
            c.get('name', '') for c in columns
            if c.get('importance', '').upper() == 'ID' or c.get('is_identification')
        ]

        # Build markdown table header: row_id | ID columns... | Score | Source
        header_cols = ['row_id'] + id_column_names + ['Score', 'Source']
        header = '| ' + ' | '.join(header_cols) + ' |'
        separator = '|' + '|'.join(['---'] * len(header_cols)) + '|'

        lines = [header, separator]

        for idx, row in enumerate(rows, 1):
            id_values = row.get('id_values', {})
            row_score = row.get('match_score', 0)
            source_subdomain = row.get('source_subdomain', 'Unknown')

            # Create row_id: row number + first ID column value
            first_id_value = list(id_values.values())[0] if id_values else 'Unknown'
            row_id = f"{idx}-{first_id_value}"

            # Build row values
            row_values = [row_id]
            for col_name in id_column_names:
                val = id_values.get(col_name, '')
                # Escape pipe characters in values
                val_str = str(val).replace('|', '\\|') if val else ''
                row_values.append(val_str)
            row_values.append(f"{row_score:.2f}")
            row_values.append(source_subdomain)

            lines.append('| ' + ' | '.join(row_values) + ' |')

        return '\n'.join(lines)

    def _add_row_ids_to_prepopulated_markdown(self, markdown: str, columns: List[Dict]) -> str:
        """
        Add P-prefixed row_ids to prepopulated markdown table for QC to reference.

        Transforms:
            | Company | Funding |
            |---------|---------|
            | Anthropic[1] | $7.3B[2] |

        Into:
            | row_id | Company | Funding |
            |--------|---------|---------|
            | P1-Anthropic | Anthropic[1] | $7.3B[2] |

        Args:
            markdown: Prepopulated rows markdown table
            columns: Column definitions (to identify first ID column)

        Returns:
            Modified markdown with row_id column prepended
        """
        import re

        if not markdown or not markdown.strip():
            return markdown

        lines = markdown.strip().split('\n')
        if len(lines) < 3:
            return markdown

        # Get first ID column name for row_id generation
        id_column_names = [
            c.get('name', '') for c in columns
            if c.get('importance', '').upper() == 'ID' or c.get('is_identification')
        ]
        first_id_col = id_column_names[0] if id_column_names else None

        # Parse header to find column positions
        header_line = lines[0].strip()
        headers = [h.strip() for h in header_line.split('|')[1:-1]]

        # Find the index of the first ID column in the headers
        first_id_col_idx = None
        if first_id_col:
            for idx, h in enumerate(headers):
                if h == first_id_col:
                    first_id_col_idx = idx
                    break

        new_lines = []
        data_row_counter = 0  # Track data rows independently of line index

        # Count expected columns from header for cell-count validation
        header_cells = [h.strip() for h in lines[0].strip().split('|')[1:-1]]
        expected_cols = len(header_cells)

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith('|'):
                new_lines.append(line)
                continue

            if i == 0:
                # Header row - prepend row_id column
                new_lines.append('| row_id ' + stripped)
            elif self._is_separator_line(stripped):
                # Separator row - prepend separator
                new_lines.append('|---' + stripped)
            else:
                # Potential data row - validate cell count matches header
                # This MUST match _parse_markdown_table_with_citations behavior
                cells = [c.strip() for c in stripped.split('|')[1:-1]]

                if len(cells) != expected_cols:
                    # Malformed row - skip (don't increment counter)
                    # _parse_markdown_table_with_citations also skips these
                    logger.warning(
                        f"[ROW_ID] Skipping malformed row (line {i}): "
                        f"{len(cells)} cells vs {expected_cols} expected"
                    )
                    new_lines.append(stripped)
                    continue

                data_row_counter += 1

                # Get first ID column value for row_id
                entity_name = 'Unknown'
                if first_id_col_idx is not None and first_id_col_idx < len(cells):
                    # Remove citations from the value for row_id
                    raw_val = cells[first_id_col_idx]
                    entity_name = re.sub(r'\[\d+\]', '', raw_val).strip() or 'Unknown'

                row_id = f"P{data_row_counter}-{entity_name}"
                new_lines.append(f'| {row_id} ' + stripped)

        return '\n'.join(new_lines)

    @staticmethod
    def _is_separator_line(line: str) -> bool:
        """
        Check if a markdown table line is a separator (e.g., |---|---|---|).
        Only returns True if the line contains ONLY pipes, dashes, colons, and whitespace.
        This prevents data rows containing '---' (e.g., 'Phase III---Approved') from
        being misidentified as separators.
        """
        # Remove all valid separator characters - if anything remains, it's not a separator
        import re
        cleaned = re.sub(r'[\|\-\:\s]', '', line)
        return len(cleaned) == 0 and '---' in line

    def _filter_markdown_by_row_ids(
        self,
        markdown: str,
        keep_row_ids: List[str],
        citations: Dict[str, str]
    ) -> tuple:
        """
        Filter markdown table to only include rows in keep_row_ids.
        Also prune citations that are no longer referenced.

        Args:
            markdown: Markdown table string
            keep_row_ids: List of row_ids to keep
            citations: Map of citation numbers to URLs

        Returns:
            (filtered_markdown, pruned_citations)
        """
        import re

        if not markdown:
            return markdown, citations

        lines = markdown.strip().split('\n')
        kept_lines = []
        used_citations = set()

        # Convert keep_row_ids to set for faster lookup
        keep_set = set(keep_row_ids)

        for line in lines:
            stripped = line.strip()

            # Keep header and separator lines
            if not stripped.startswith('|') or self._is_separator_line(stripped):
                kept_lines.append(line)
                continue

            # Check if this is the header row (contains "row_id" or first row after start)
            if 'row_id' in stripped.lower():
                kept_lines.append(line)
                continue

            # Extract row_id from first column
            parts = [p.strip() for p in stripped.split('|')[1:-1]]
            if not parts:
                continue

            row_id = parts[0]

            # Check if this row should be kept
            if row_id in keep_set:
                kept_lines.append(line)
                # Track citations used in this line
                for cite_num in re.findall(r'\[(\d+)\]', line):
                    used_citations.add(cite_num)

        # Prune citations that are no longer referenced
        pruned_citations = {k: v for k, v in citations.items() if k in used_citations}

        return '\n'.join(kept_lines), pruned_citations

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

    def _convert_simplified_response(self, simplified: Dict[str, Any], discovered_rows: List[Dict]) -> Dict[str, Any]:
        """
        Convert new simplified QC response format to old format for backward compatibility.

        New format: {action, remove_row_ids, overall_score, discovery_guidance, new_subdomains, ...}
        Old format: {reviewed_rows, qc_summary, rejected_rows, retrigger_discovery, recovery_decision, ...}

        Key change: Rows are KEPT BY DEFAULT. Only removed rows are specified.

        Args:
            simplified: New simplified response
            discovered_rows: Original discovered rows for generating row_ids

        Returns:
            Response in old format
        """
        action = simplified.get('action', 'pass')
        overall_score = simplified.get('overall_score', 0.8)

        # Build row_id -> row mapping from discovered_rows
        row_id_to_row = {}
        for idx, row in enumerate(discovered_rows, 1):
            id_vals = row.get('id_values', {})
            # Fix: Check for non-empty dict to avoid IndexError on empty {}
            first_id_value = list(id_vals.values())[0] if id_vals and len(id_vals) > 0 else 'Unknown'
            row_id = f"{idx}-{first_id_value}"
            row_id_to_row[row_id] = row
            # Also store by just the first_id_value for flexible matching
            row_id_to_row[first_id_value] = row

        # Check for new format (keep_row_ids_in_order) vs old format (remove_row_ids)
        keep_row_ids_in_order = simplified.get('keep_row_ids_in_order', None)
        remove_row_ids = simplified.get('remove_row_ids', []) or []
        removal_reasons = simplified.get('removal_reasons', {}) or {}

        # Build row_id mapping for discovered rows
        row_id_map = {}
        for idx, row in enumerate(discovered_rows, 1):
            id_vals = row.get('id_values', {})
            first_id_value = list(id_vals.values())[0] if id_vals and len(id_vals) > 0 else 'Unknown'
            row_id = f"{idx}-{first_id_value}"
            row_id_map[row_id] = (idx, row, first_id_value)
            row_id_map[first_id_value] = (idx, row, first_id_value)
            row_id_map[str(idx)] = (idx, row, first_id_value)

        reviewed_rows = []
        rejected_rows = []

        if keep_row_ids_in_order and isinstance(keep_row_ids_in_order, list):
            # NEW FORMAT: keep_row_ids_in_order specifies which rows to keep AND their order
            kept_ids = set()
            for keep_id in keep_row_ids_in_order:
                if keep_id in row_id_map:
                    idx, row, first_id_value = row_id_map[keep_id]
                    row_id = f"{idx}-{first_id_value}"
                    if row_id not in kept_ids:
                        row_score = row.get('match_score', 0.7)
                        reviewed_rows.append({
                            'row_id': row_id,
                            'row_score': row_score,
                            'qc_score': overall_score if overall_score is not None else row_score,
                            'qc_rationale': '',
                            'keep': True,
                            'priority_adjustment': 'none'
                        })
                        kept_ids.add(row_id)

            # Build rejected rows from those not in keep list
            for idx, row in enumerate(discovered_rows, 1):
                id_vals = row.get('id_values', {})
                first_id_value = list(id_vals.values())[0] if id_vals and len(id_vals) > 0 else 'Unknown'
                row_id = f"{idx}-{first_id_value}"
                if row_id not in kept_ids:
                    reason = removal_reasons.get(row_id, removal_reasons.get(first_id_value, 'Removed by QC'))
                    rejected_rows.append({
                        'row_id': row_id,
                        'rejection_reason': reason
                    })

        else:
            # OLD FORMAT: remove_row_ids specifies rows to remove (kept for backward compatibility)
            removed_row_ids = set()
            for item in remove_row_ids:
                row_id = item.get('row_id', '') if isinstance(item, dict) else str(item)
                reason = item.get('reason', 'No reason provided') if isinstance(item, dict) else 'Removed by QC'
                removed_row_ids.add(row_id)
                rejected_rows.append({
                    'row_id': row_id,
                    'rejection_reason': reason
                })

            # All rows kept except those in remove_row_ids
            for idx, row in enumerate(discovered_rows, 1):
                id_vals = row.get('id_values', {})
                first_id_value = list(id_vals.values())[0] if id_vals and len(id_vals) > 0 else 'Unknown'
                row_id = f"{idx}-{first_id_value}"

                should_remove = (
                    row_id in removed_row_ids or
                    first_id_value in removed_row_ids or
                    str(idx) in removed_row_ids
                )

                if not should_remove:
                    row_score = row.get('match_score', 0.7)
                    reviewed_rows.append({
                        'row_id': row_id,
                        'row_score': row_score,
                        'qc_score': overall_score if overall_score is not None else row_score,
                        'qc_rationale': '',
                        'keep': True,
                        'priority_adjustment': 'none'
                    })

        # Build qc_summary
        kept_count = len(reviewed_rows)
        total_reviewed = len(discovered_rows)
        qc_summary = {
            'total_reviewed': total_reviewed,
            'kept': kept_count,
            'rejected': len(rejected_rows),
            'promoted': 0,
            'demoted': 0,
            'reasoning': f'QC {action}: {kept_count} rows kept, {len(rejected_rows)} removed'
        }

        # Build old format response
        # IMPORTANT: Preserve action, overall_score, and action-specific fields for schema validation
        old_format = {
            'action': action,  # Required by schema
            'overall_score': overall_score,  # Required by schema (except restructure)
            'reviewed_rows': reviewed_rows,
            'rejected_rows': rejected_rows,
            'qc_summary': qc_summary
        }

        # Preserve keep_row_ids_in_order if provided (for explicit row filtering and ordering)
        if keep_row_ids_in_order and isinstance(keep_row_ids_in_order, list):
            old_format['keep_row_ids_in_order'] = keep_row_ids_in_order
            logger.info(f"[QC] Preserving keep_row_ids_in_order with {len(keep_row_ids_in_order)} entries")

        # Preserve remove_prepopulated_row_ids for filtering pre-existing rows
        remove_prepopulated = simplified.get('remove_prepopulated_row_ids', None)
        if remove_prepopulated and isinstance(remove_prepopulated, list):
            old_format['remove_prepopulated_row_ids'] = remove_prepopulated
            logger.info(f"[QC] Preserving remove_prepopulated_row_ids with {len(remove_prepopulated)} entries")

        # Preserve action-specific fields required by _validate_qc_response
        if action == 'filter':
            # filter action uses keep_row_ids_in_order (new) or remove_row_ids (legacy)
            if keep_row_ids_in_order:
                old_format['keep_row_ids_in_order'] = keep_row_ids_in_order
            else:
                old_format['remove_row_ids'] = remove_row_ids

        # Handle retrigger_discovery action
        if action == 'retrigger_discovery':
            old_format['retrigger_discovery'] = {
                'should_retrigger': True,
                'reason': simplified.get('discovery_guidance', 'Need more rows'),
                'new_subdomains': simplified.get('new_subdomains', [])
            }
            # Also preserve fields needed for action-specific validation
            old_format['new_subdomains'] = simplified.get('new_subdomains', [])
            old_format['discovery_guidance'] = simplified.get('discovery_guidance', '')

        # Handle restructure action
        if action == 'restructure':
            old_format['recovery_decision'] = {
                'decision': 'restructure',
                'reasoning': 'QC determined table needs restructuring',
                'restructuring_guidance': simplified.get('restructuring_guidance', {}),
                'user_facing_message': simplified.get('user_message', 'Restructuring table...')
            }
            # Also preserve fields needed for action-specific validation
            old_format['restructuring_guidance'] = simplified.get('restructuring_guidance', {})
            old_format['user_message'] = simplified.get('user_message', '')

        logger.info(f"[QC] Converted simplified response: action={action}, kept={kept_count}, removed={len(rejected_rows)}")

        return old_format

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
