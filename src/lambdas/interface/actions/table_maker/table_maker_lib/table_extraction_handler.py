#!/usr/bin/env python3
"""
Table extraction handler for table generation system.
Extracts complete tables from identified URLs after background research.
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

# Configure logging
logger = logging.getLogger(__name__)


class TableExtractionHandler:
    """Handle table extraction from identified sources."""

    def __init__(self, ai_client, prompt_loader, schema_validator):
        """
        Initialize table extraction handler.

        Args:
            ai_client: AI API client instance (from ../../src/shared/ai_api_client.py)
            prompt_loader: PromptLoader instance
            schema_validator: SchemaValidator instance
        """
        self.ai_client = ai_client
        self.prompt_loader = prompt_loader
        self.schema_validator = schema_validator

        logger.info("Initialized TableExtractionHandler")

    async def extract_tables(
        self,
        identified_tables: List[Dict[str, Any]],
        conversation_context: Dict[str, Any] = None,
        model: str = "sonar",
        max_tokens: int = 16000,
        search_context_size: str = "high",
        timeout: int = 120
    ) -> Dict[str, Any]:
        """
        Extract complete tables from identified URLs.

        Args:
            identified_tables: List of table metadata from background research
                Each should have: url, table_name, estimated_rows, columns, extract_table
                Optional: target_rows (string filter/specification for which rows to extract, e.g., "only winners")
            conversation_context: Optional conversation history (for context)
            model: AI model to use (default: sonar for Perplexity)
            max_tokens: Maximum tokens for AI response
            search_context_size: Search context size for Perplexity (low/medium/high)
            timeout: Timeout in seconds

        Returns:
            Dictionary with results:
            {
                'success': bool,
                'extracted_tables': List[Dict],  # One per input table
                'tables_extracted': int,
                'total_rows_extracted': int,
                'processing_time': float,
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'extracted_tables': [],
            'tables_extracted': 0,
            'total_rows_extracted': 0,
            'processing_time': 0.0,
            'error': None
        }

        start_time = time.time()

        try:
            logger.info(f"Starting table extraction for {len(identified_tables)} tables")

            extracted_tables = []
            total_rows = 0
            all_enhanced_data = []  # Track API metadata from all calls

            # Extract each table sequentially
            for idx, table_meta in enumerate(identified_tables):
                table_url = table_meta.get('url')
                table_name = table_meta.get('table_name', f'Table {idx + 1}')

                logger.info(f"Extracting table {idx + 1}/{len(identified_tables)}: {table_name} from {table_url}")

                try:
                    extraction_result = await self._extract_single_table(
                        table_meta=table_meta,
                        model=model,
                        max_tokens=max_tokens,
                        search_context_size=search_context_size,
                        timeout=timeout
                    )

                    if extraction_result.get('success'):
                        extracted_data = extraction_result.get('data', {})
                        rows_count = extracted_data.get('rows_extracted', 0)
                        extracted_tables.append(extracted_data)
                        total_rows += rows_count

                        # Track enhanced_data from this extraction
                        if 'enhanced_data' in extraction_result:
                            all_enhanced_data.append(extraction_result['enhanced_data'])

                        logger.info(
                            f"  [SUCCESS] Extracted {rows_count} rows from {table_name} "
                            f"(complete: {extracted_data.get('extraction_complete', False)})"
                        )
                    else:
                        error_msg = extraction_result.get('error', 'Unknown error')
                        logger.warning(f"  [FAILED] Could not extract {table_name}: {error_msg}")
                        # Continue with other tables even if one fails

                except Exception as e:
                    logger.error(f"Error extracting table {table_name}: {str(e)}", exc_info=True)
                    # Continue with other tables

            # Success if at least one table extracted
            result.update({
                'success': len(extracted_tables) > 0,
                'extracted_tables': extracted_tables,
                'tables_extracted': len(extracted_tables),
                'total_rows_extracted': total_rows,
                'processing_time': time.time() - start_time,
                'enhanced_data': all_enhanced_data  # API metadata from all extractions
            })

            if len(extracted_tables) == 0:
                result['error'] = 'No tables could be extracted'

            logger.info(
                f"Table extraction complete: {len(extracted_tables)}/{len(identified_tables)} tables, "
                f"{total_rows} total rows, time: {result['processing_time']:.2f}s"
            )

            return result

        except Exception as e:
            logger.error(f"Table extraction failed: {str(e)}", exc_info=True)
            result['error'] = str(e)
            result['processing_time'] = time.time() - start_time
            return result

    async def _extract_single_table(
        self,
        table_meta: Dict[str, Any],
        model: str,
        max_tokens: int,
        search_context_size: str,
        timeout: int
    ) -> Dict[str, Any]:
        """
        Extract a single table.

        Args:
            table_meta: Table metadata with url, table_name, estimated_rows, columns
            model: AI model to use
            max_tokens: Maximum tokens
            search_context_size: Search context size
            timeout: Timeout in seconds

        Returns:
            Dictionary with success flag and extracted data
        """
        result = {'success': False, 'data': {}, 'error': None}

        try:
            # Extract metadata
            table_url = table_meta.get('url')
            table_name = table_meta.get('table_name', 'Unknown Table')
            estimated_rows = table_meta.get('estimated_rows', 'unknown')
            expected_columns = table_meta.get('columns', [])
            target_rows = table_meta.get('target_rows')  # Optional

            if not table_url:
                result['error'] = 'No URL provided'
                return result

            # Format expected columns for prompt
            if isinstance(expected_columns, list):
                columns_text = ', '.join(expected_columns)
            else:
                columns_text = str(expected_columns)

            # Format target rows instruction
            if target_rows:
                target_instruction = f"**Target Rows Filter:** {target_rows}\n\nExtract ONLY rows matching this specification."
            else:
                target_instruction = "**Target:** Extract ALL rows from this table (complete extraction)."

            # Build prompt variables
            variables = {
                'TABLE_URL': table_url,
                'TABLE_NAME': table_name,
                'ESTIMATED_ROWS': str(estimated_rows),
                'EXPECTED_COLUMNS': columns_text,
                'TARGET_ROWS_INSTRUCTION': target_instruction
            }

            logger.debug(f"Loading table_extraction prompt for {table_name}")
            prompt = self.prompt_loader.load_prompt('table_extraction', variables)

            # Load schema
            schema = self.schema_validator.load_schema('table_extraction_response')

            # Extract domain from URL for site-specific search
            parsed_url = urlparse(table_url)
            domain = parsed_url.netloc
            if domain.startswith('www.'):
                domain = domain[4:]  # Remove www.

            logger.info(f"Calling AI API for table extraction with domain filter: {domain}")

            # Call API with domain-specific search
            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=model,
                max_tokens=max_tokens,
                use_cache=False,  # Don't cache extractions (data may change)
                search_context_size=search_context_size,
                include_domains=[domain],  # Prioritize the source domain
                debug_name=f"table_extraction_{table_name.replace(' ', '_')}"
            )

            # Check for API errors
            if 'response' not in api_response and 'error' in api_response:
                error_detail = api_response.get('error', 'Unknown error')
                logger.error(f"API call failed: {error_detail}")
                result['error'] = f"AI API call failed: {error_detail}"
                return result

            # Extract structured response
            raw_response = api_response.get('response', {})

            try:
                structured_response = self.ai_client.extract_structured_response(
                    raw_response,
                    tool_name="table_extraction"
                )
            except Exception as extract_error:
                logger.error(f"Failed to extract structured response: {extract_error}")
                result['error'] = f"Response extraction failed: {str(extract_error)}"
                return result

            # Validate required fields
            required_fields = ['table_name', 'source_url', 'extraction_complete',
                             'rows_extracted', 'rows']
            missing_fields = [f for f in required_fields if f not in structured_response]

            if missing_fields:
                logger.error(f"Missing required fields in AI response: {missing_fields}")
                result['error'] = f"Response missing fields: {', '.join(missing_fields)}"
                return result

            # Extract enhanced_data for API call tracking
            enhanced_data = api_response.get('enhanced_data', {})

            # Success
            result.update({
                'success': True,
                'data': structured_response,
                'enhanced_data': enhanced_data
            })

            return result

        except Exception as e:
            logger.error(f"Single table extraction failed: {str(e)}", exc_info=True)
            result['error'] = str(e)
            return result
