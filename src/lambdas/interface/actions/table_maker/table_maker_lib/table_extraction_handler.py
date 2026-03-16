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

from shared.table_extractor import TableExtractor

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

        # Initialize standalone table extractor
        self.table_extractor = TableExtractor(ai_client, schema_validator)

        logger.info("Initialized TableExtractionHandler with TableExtractor")

    async def extract_tables(
        self,
        identified_tables: List[Dict[str, Any]],
        conversation_context: Dict[str, Any] = None,
        model: str = "sonar",
        max_tokens: int = 16000,
        search_context_size: str = "high",
        max_web_searches: int = 3,
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
            max_web_searches: Maximum web searches for Claude models
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
                        max_web_searches=max_web_searches,
                        timeout=timeout
                    )

                    if extraction_result.get('success'):
                        extracted_data = extraction_result.get('data', {})
                        rows_count = extracted_data.get('rows_count', 0)  # Simple extraction uses rows_count
                        extracted_tables.append(extracted_data)
                        total_rows += rows_count

                        # Track enhanced_data from this extraction
                        if 'enhanced_data' in extraction_result:
                            all_enhanced_data.append(extraction_result['enhanced_data'])

                        logger.info(
                            f"  [SUCCESS] Extracted {rows_count} rows, "
                            f"{len(extracted_data.get('columns_found', []))} columns from {table_name} "
                            f"(method: {extracted_data.get('extraction_method', 'unknown')})"
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
        max_web_searches: int,
        timeout: int
    ) -> Dict[str, Any]:
        """
        Extract a single table using the standalone TableExtractor.

        Args:
            table_meta: Table metadata with url, table_name, estimated_rows, columns, url_quality
            model: AI model to use
            max_tokens: Maximum tokens
            search_context_size: Search context size
            max_web_searches: Maximum web searches for Claude models
            timeout: Timeout in seconds

        Returns:
            Dictionary with success flag and extracted data
        """
        result = {'success': False, 'data': {}, 'error': None}

        try:
            # Extract metadata
            table_url = table_meta.get('url')
            table_name = table_meta.get('table_name', 'Unknown Table')
            estimated_rows = table_meta.get('estimated_rows', 0)
            expected_columns = table_meta.get('columns', [])
            url_quality = table_meta.get('url_quality', 0.85)  # From background research
            target_rows = table_meta.get('target_rows')  # Optional filter

            if not table_url:
                result['error'] = 'No URL provided'
                return result

            # Ensure expected_columns is a list
            if not isinstance(expected_columns, list):
                expected_columns = [str(expected_columns)]

            # Parse estimated_rows to int
            if isinstance(estimated_rows, str):
                try:
                    estimated_rows = int(estimated_rows)
                except (ValueError, TypeError):
                    estimated_rows = None

            logger.info(f"Extracting table with simple schema-free extraction: {table_name}")
            logger.info(f"  URL: {table_url}")

            # Use SIMPLE extraction (no schema, returns markdown)
            extraction_result = await self.table_extractor.extract_simple_table(
                description=table_name,
                url=table_url
            )

            if not extraction_result['success']:
                result['error'] = extraction_result.get('error', 'Extraction failed')
                logger.warning(f"  [FAILED] Simple extraction failed: {result['error']}")
                return result

            # Extract metadata (including costs) from extraction result
            extraction_metadata = extraction_result.get('metadata', {})

            # Convert simple extraction result to expected format
            # Simple extraction returns markdown_table instead of structured rows
            source_urls = extraction_result.get('source_urls', [])
            structured_response = {
                'table_name': table_name,
                'source_url': extraction_result['url'],  # Primary URL
                'source_urls': source_urls,  # All URLs that contributed (may be multiple from parallel extraction)
                'markdown_table': extraction_result['markdown_table'],  # Raw markdown table
                'rows_count': extraction_result['rows_count'],
                'columns_found': extraction_result['columns_found'],
                'extraction_method': extraction_result['extraction_method'],
                'extraction_notes': f"Method: {extraction_result['extraction_method']}, "
                                  f"Rows: {extraction_result['rows_count']}, "
                                  f"Columns: {len(extraction_result['columns_found'])}, "
                                  f"Sources: {len(source_urls)}, "
                                  f"Cost: ${extraction_metadata.get('total_cost', 0.0):.4f}",
                'metadata': extraction_metadata
            }

            # Apply target_rows filter note if specified
            if target_rows:
                logger.info(f"  Note: target_rows filter '{target_rows}' will be applied by column definition")
                structured_response['target_rows_filter'] = target_rows

            # Quality check: did we extract enough structured rows vs estimated?
            # search_api_source_selection returns source-count not row-count — flag low-yield cases
            if estimated_rows and estimated_rows > 0:
                detected = extraction_result.get('rows_count', 0)
                coverage = detected / float(estimated_rows)
                if coverage < 0.90:
                    logger.warning(
                        f"  [EXTRACTION_QUALITY] Low yield: detected {detected} items vs "
                        f"estimated {estimated_rows} ({coverage*100:.1f}%). "
                        f"Flagging for column_definition to parse raw content directly."
                    )
                    structured_response['estimated_rows_in_content'] = estimated_rows
                    structured_response['low_yield_warning'] = (
                        f"Simple extraction detected only {detected} structured items but source "
                        f"is estimated to contain ~{estimated_rows} rows. "
                        f"The raw content above likely contains all rows as prose or a list — "
                        f"column_definition must parse them directly."
                    )

            # Create enhanced_data for tracking (format for usage tracking system)
            cost_by_provider = extraction_metadata.get('cost_by_provider', {})
            total_cost = extraction_metadata.get('total_cost', 0.0)

            # Build call_info in the format expected by usage tracking
            call_info = {
                'cost': total_cost,
                'api_provider': extraction_result['extraction_method'],
                'model': extraction_result['extraction_method'],
                'processing_time': extraction_metadata.get('processing_time', 0.0),
                'cost_breakdown': cost_by_provider
            }

            enhanced_data = {
                'call_info': call_info,
                'extraction_method': extraction_result['extraction_method'],
                'rows_count': extraction_result['rows_count'],
                'columns_found': extraction_result['columns_found'],
                # Include full metadata for reference
                'table_extraction_metadata': extraction_metadata
            }

            # Success
            result.update({
                'success': True,
                'data': structured_response,
                'enhanced_data': enhanced_data
            })

            logger.info(
                f"  [SUCCESS] Simple extraction: {structured_response['rows_count']} rows, "
                f"method={extraction_result['extraction_method']}, "
                f"columns={len(extraction_result['columns_found'])}, "
                f"cost=${extraction_metadata.get('total_cost', 0.0):.4f}"
            )

            return result

        except Exception as e:
            logger.error(f"Single table extraction failed: {str(e)}", exc_info=True)
            result['error'] = str(e)
            return result
