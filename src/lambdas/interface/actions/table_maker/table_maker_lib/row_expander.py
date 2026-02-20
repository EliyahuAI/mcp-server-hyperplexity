#!/usr/bin/env python3
"""
Row expander for table generation system.
Expands table rows using AI to generate additional sample data based on criteria.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class RowExpander:
    """Expand table rows using AI to generate additional samples."""

    def __init__(self, ai_client, prompt_loader, schema_validator):
        """
        Initialize row expander.

        Args:
            ai_client: AI API client instance (from ../../src/shared/ai_api_client.py)
            prompt_loader: PromptLoader instance
            schema_validator: SchemaValidator instance
        """
        self.ai_client = ai_client
        self.prompt_loader = prompt_loader
        self.schema_validator = schema_validator
        logger.info("Initialized RowExpander")

    async def expand_rows(
        self,
        table_structure: Dict[str, Any],
        existing_rows: List[Dict[str, Any]],
        expansion_request: str,
        row_count: int = 10,
        model: str = "claude-sonnet-4-6"
    ) -> Dict[str, Any]:
        """
        Generate additional rows based on user criteria.

        Args:
            table_structure: Current table structure with columns definition
            existing_rows: List of existing row data
            expansion_request: User's description of what rows to add
            row_count: Number of new rows to generate
            model: AI model to use

        Returns:
            Dictionary with expansion results:
            {
                'success': bool,
                'expanded_rows': List[Dict],
                'reasoning': str,
                'rows_generated': int,
                'error': Optional[str],
                'validation_errors': Optional[List[str]]
            }
        """
        result = {
            'success': False,
            'expanded_rows': [],
            'reasoning': '',
            'rows_generated': 0,
            'error': None,
            'validation_errors': None
        }

        try:
            logger.info(
                f"Expanding rows: request='{expansion_request[:50]}...', "
                f"count={row_count}, existing={len(existing_rows)}"
            )

            # Prepare prompt variables
            variables = {
                'TABLE_STRUCTURE': json.dumps(table_structure, indent=2),
                'EXISTING_ROWS': json.dumps(existing_rows, indent=2),
                'EXPANSION_REQUEST': expansion_request,
                'ROW_COUNT': str(row_count)
            }

            # Load and fill prompt template
            prompt = self.prompt_loader.load_prompt('row_expansion', variables)

            # Load schema for response validation
            schema = self.schema_validator.load_schema('row_expansion_response')

            # Call AI API with structured output
            logger.debug(f"Calling AI API with model: {model}")
            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=model,
                max_tokens=8000,
                use_cache=True,  # Enable caching for Lambda deployment
                debug_name="table_maker_row_expansion"
            )

            # Check if API call returned a response
            if 'response' not in api_response and 'error' in api_response:
                raise Exception(
                    f"AI API call failed: {api_response.get('error', 'Unknown error')}"
                )

            # Extract response content and parse structured response
            raw_response = api_response.get('response', {})

            # Parse structured response (same as conversation_handler)
            if 'choices' in raw_response:
                content = raw_response['choices'][0]['message']['content']
                if isinstance(content, str):
                    response_content = json.loads(content)
                else:
                    response_content = content
            else:
                response_content = raw_response

            # Validate response against schema
            validation_result = self.schema_validator.validate_ai_response(
                response_content,
                'row_expansion_response'
            )

            if not validation_result['is_valid']:
                result['validation_errors'] = validation_result['errors']
                raise Exception(
                    f"AI response validation failed: {validation_result['errors']}"
                )

            # Extract expanded rows and reasoning
            expanded_rows = response_content.get('expanded_rows', [])
            reasoning = response_content.get('reasoning', 'No reasoning provided')

            # Validate that rows match table structure
            validation_errors = self._validate_rows_structure(
                expanded_rows,
                table_structure
            )

            if validation_errors:
                result['validation_errors'] = validation_errors
                logger.warning(
                    f"Row structure validation warnings: {len(validation_errors)} issue(s)"
                )
                # Don't fail, just log warnings

            result['expanded_rows'] = expanded_rows
            result['reasoning'] = reasoning
            result['rows_generated'] = len(expanded_rows)
            result['success'] = True

            logger.info(
                f"Successfully expanded rows: generated {result['rows_generated']} new row(s)"
            )

            # Log token usage if available
            if 'token_usage' in api_response:
                token_usage = api_response['token_usage']
                logger.info(
                    f"Token usage - Input: {token_usage.get('input_tokens', 0)}, "
                    f"Output: {token_usage.get('output_tokens', 0)}"
                )

        except Exception as e:
            error_msg = f"Error expanding rows: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg

        return result

    def _validate_rows_structure(
        self,
        rows: List[Dict[str, Any]],
        table_structure: Dict[str, Any]
    ) -> List[str]:
        """
        Validate that generated rows match the expected table structure.

        Args:
            rows: List of generated rows
            table_structure: Table structure definition

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not rows:
            return errors

        # Extract expected column names from table structure
        columns = table_structure.get('columns', [])
        if not columns:
            # Try alternate structure
            columns = table_structure.get('proposed_columns', [])

        expected_columns = set(col['name'] for col in columns)

        # Validate each row
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"Row {idx + 1} is not a dictionary")
                continue

            # Exclude internal metadata fields (e.g., _row_key, _history)
            row_columns = set(k for k in row.keys() if not k.startswith('_'))

            # Check for missing columns
            missing = expected_columns - row_columns
            if missing:
                errors.append(
                    f"Row {idx + 1} missing columns: {', '.join(sorted(missing))}"
                )

            # Extra columns are okay (they'll be ignored), but log as info
            extra = row_columns - expected_columns
            if extra:
                logger.debug(f"Row {idx + 1} has extra columns: {', '.join(sorted(extra))}")

        return errors

    async def expand_rows_iteratively(
        self,
        table_structure: Dict[str, Any],
        existing_rows: List[Dict[str, Any]],
        expansion_request: str,
        total_rows_needed: int,
        batch_size: int = 10,
        model: str = "claude-sonnet-4-6",
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        Expand rows in batches to generate a large number of rows.

        Args:
            table_structure: Current table structure
            existing_rows: List of existing rows
            expansion_request: User's expansion criteria
            total_rows_needed: Total number of new rows to generate
            batch_size: Number of rows per API call
            model: AI model to use
            progress_callback: Optional callback(batch_num, total_batches, rows_generated) called after each batch

        Returns:
            Dictionary with expansion results including all generated rows
        """
        result = {
            'success': True,
            'expanded_rows': [],
            'reasoning': [],
            'rows_generated': 0,
            'batches_completed': 0,
            'errors': []
        }

        try:
            all_rows = list(existing_rows)  # Start with existing rows
            batches_needed = (total_rows_needed + batch_size - 1) // batch_size

            logger.info(
                f"Starting iterative expansion: {total_rows_needed} rows in "
                f"{batches_needed} batch(es) of {batch_size}"
            )

            for batch_num in range(batches_needed):
                rows_in_batch = min(batch_size, total_rows_needed - len(result['expanded_rows']))

                logger.info(f"Processing batch {batch_num + 1}/{batches_needed}")

                # Expand rows for this batch
                batch_result = await self.expand_rows(
                    table_structure=table_structure,
                    existing_rows=all_rows,
                    expansion_request=expansion_request,
                    row_count=rows_in_batch,
                    model=model
                )

                logger.info(f"[DEBUG] Batch {batch_num + 1} expand_rows returned, processing results...")

                if not batch_result['success']:
                    logger.error(f"[DEBUG] Batch {batch_num + 1} was not successful")
                    result['errors'].append(
                        f"Batch {batch_num + 1} failed: {batch_result.get('error')}"
                    )
                    # Continue with next batch
                    continue

                # Add generated rows to results
                logger.info(f"[DEBUG] Batch {batch_num + 1} extracting rows from result...")
                batch_rows = batch_result['expanded_rows']
                logger.info(f"[DEBUG] Batch {batch_num + 1} got {len(batch_rows)} rows, extending result...")
                result['expanded_rows'].extend(batch_rows)
                logger.info(f"[DEBUG] Batch {batch_num + 1} extended result, appending reasoning...")
                result['reasoning'].append(batch_result['reasoning'])
                logger.info(f"[DEBUG] Batch {batch_num + 1} appended reasoning, incrementing counter...")
                result['batches_completed'] += 1

                # Update all_rows for context in next batch
                logger.info(f"[DEBUG] Batch {batch_num + 1} extending all_rows...")
                all_rows.extend(batch_rows)

                logger.info(
                    f"Batch {batch_num + 1} completed: {len(batch_rows)} rows generated"
                )

                # Call progress callback if provided
                if progress_callback:
                    try:
                        progress_callback(batch_num + 1, batches_needed, len(result['expanded_rows']))
                    except Exception as e:
                        logger.warning(f"Progress callback failed: {e}")

            result['rows_generated'] = len(result['expanded_rows'])

            if result['errors']:
                result['success'] = len(result['errors']) < batches_needed

            logger.info(
                f"Iterative expansion completed: {result['rows_generated']} total rows, "
                f"{result['batches_completed']}/{batches_needed} batches successful"
            )

        except Exception as e:
            error_msg = f"Error in iterative expansion: {str(e)}"
            logger.error(error_msg)
            result['errors'].append(error_msg)
            result['success'] = False

        return result

    def merge_expanded_rows(
        self,
        existing_rows: List[Dict[str, Any]],
        expanded_rows: List[Dict[str, Any]],
        deduplicate: bool = True,
        dedup_keys: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Merge expanded rows with existing rows, optionally removing duplicates.

        Args:
            existing_rows: Current rows
            expanded_rows: New rows to add
            deduplicate: Whether to remove duplicate rows
            dedup_keys: List of column names to use for deduplication (all if None)

        Returns:
            Dictionary with merged results:
            {
                'merged_rows': List[Dict],
                'total_count': int,
                'duplicates_removed': int
            }
        """
        result = {
            'merged_rows': [],
            'total_count': 0,
            'duplicates_removed': 0
        }

        try:
            # Start with existing rows
            merged = list(existing_rows)

            if not deduplicate:
                # Simple append
                merged.extend(expanded_rows)
            else:
                # Deduplicate based on specified keys
                seen = set()

                # Add existing rows to seen set
                for row in existing_rows:
                    row_key = self._make_row_key(row, dedup_keys)
                    seen.add(row_key)

                # Add new rows, skipping duplicates
                for row in expanded_rows:
                    row_key = self._make_row_key(row, dedup_keys)
                    if row_key not in seen:
                        merged.append(row)
                        seen.add(row_key)
                    else:
                        result['duplicates_removed'] += 1

            result['merged_rows'] = merged
            result['total_count'] = len(merged)

            logger.info(
                f"Merged rows: {len(existing_rows)} existing + {len(expanded_rows)} new = "
                f"{result['total_count']} total ({result['duplicates_removed']} duplicates removed)"
            )

        except Exception as e:
            logger.error(f"Error merging rows: {e}")
            # Return existing rows on error
            result['merged_rows'] = existing_rows
            result['total_count'] = len(existing_rows)

        return result

    def _make_row_key(
        self,
        row: Dict[str, Any],
        keys: Optional[List[str]] = None
    ) -> str:
        """
        Create a unique key for a row for deduplication.

        Args:
            row: Row data
            keys: List of column names to use (all if None)

        Returns:
            String key representing the row
        """
        if keys:
            # Use only specified keys
            values = [str(row.get(k, '')) for k in sorted(keys) if k in row]
        else:
            # Use all keys
            values = [f"{k}:{row[k]}" for k in sorted(row.keys())]

        return '|'.join(values)
