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
        max_rows: int = 50
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
                'error': Optional[str]
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
                'DISCOVERED_ROWS': self._format_rows(discovered_rows)
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
                max_tokens=16000,  # Increased for thorough review
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
            rejected_rows = ai_response.get('rejected_rows', [])
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
                    merged = original_row.copy()
                    qc_score = qc_row.get('qc_score', 0)
                    row_score = qc_row.get('row_score', merged.get('match_score', 0))

                    # If qc_rationale not provided and scores match, generate default
                    qc_rationale = qc_row.get('qc_rationale', '')
                    if not qc_rationale and abs(qc_score - row_score) < 0.01:
                        qc_rationale = "QC confirms discovery assessment"

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

            # Sort by qc_score descending
            approved_rows_sorted = sorted(
                approved_rows,
                key=lambda x: x.get('qc_score', 0),
                reverse=True
            )

            # Apply max_rows limit
            final_approved = approved_rows_sorted[:max_rows]

            # Track rows that were filtered out by limits
            filtered_by_limit = len(approved_rows_sorted) - len(final_approved)
            if filtered_by_limit > 0:
                logger.info(f"Filtered {filtered_by_limit} rows due to max_rows limit ({max_rows})")

            # Build successful result
            result['success'] = True
            result['approved_rows'] = final_approved
            result['rejected_rows'] = rejected_rows
            result['qc_summary'] = qc_summary
            result['reviewed_rows'] = reviewed_rows

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
                f"Rejected: {len(rejected_rows)}, "
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
            result['error'] = error_msg
            result['processing_time'] = time.time() - start_time

        return result

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

    def _format_rows(self, rows: List[Dict]) -> str:
        """
        Format discovered rows for prompt with row_id.

        Args:
            rows: List of discovered row dictionaries

        Returns:
            Formatted rows string
        """
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
        reasoning = qc_summary.get('reasoning', '')

        logger.info(
            f"QC Summary - Total: {total}, "
            f"Kept: {kept}, "
            f"Rejected: {rejected}, "
            f"Promoted: {promoted}, "
            f"Demoted: {demoted}, "
            f"Final (after limits): {final_approved}"
        )

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
