#!/usr/bin/env python3
"""
Column definition handler for table generation system.
Defines precise column specifications and search strategy from approved conversation context.
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class ColumnDefinitionHandler:
    """Handle column definition and search strategy creation from conversation context."""

    def __init__(self, ai_client, prompt_loader, schema_validator):
        """
        Initialize column definition handler.

        Args:
            ai_client: AI API client instance (from ../../src/shared/ai_api_client.py)
            prompt_loader: PromptLoader instance
            schema_validator: SchemaValidator instance
        """
        self.ai_client = ai_client
        self.prompt_loader = prompt_loader
        self.schema_validator = schema_validator

        logger.info("Initialized ColumnDefinitionHandler")

    async def define_columns(
        self,
        conversation_context: Dict[str, Any],
        context_web_research: List[str] = None,
        model: str = "sonar-pro",
        max_tokens: int = 8000
    ) -> Dict[str, Any]:
        """
        Define precise column specifications and search strategy from conversation context.

        Args:
            conversation_context: Full conversation history and approved requirements
            model: AI model to use (default: claude-sonnet-4-5)
            max_tokens: Maximum tokens for AI response

        Returns:
            Dictionary with results:
            {
                'success': bool,
                'columns': List[Dict],  # Column definitions with validation strategies
                'search_strategy': Dict,  # Search strategy with subdomain hints
                'table_name': str,
                'tablewide_research': str,
                'processing_time': float,  # Seconds
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'columns': [],
            'search_strategy': {},
            'table_name': '',
            'tablewide_research': '',
            'processing_time': 0.0,
            'error': None
        }

        start_time = time.time()

        try:
            logger.info("Starting column definition process")

            # Extract conversation data
            conversation_history = self._format_conversation_history(conversation_context)
            user_requirements = self._extract_user_requirements(conversation_context)

            # Format context research items if provided
            research_context = ""
            if context_web_research and len(context_web_research) > 0:
                research_context = "\n\n**CONTEXT TO RESEARCH** (affects column design and validation):\n"
                for item in context_web_research:
                    research_context += f"- {item}\n"
                research_context += "\nUse web search to understand these items, then incorporate findings into column descriptions and validation strategies."

            # Build prompt with variables
            variables = {
                'CONVERSATION_CONTEXT': conversation_history,
                'USER_REQUIREMENTS': user_requirements,
                'CONTEXT_RESEARCH': research_context
            }

            logger.debug(f"Loading prompt template with {len(variables)} variables")
            logger.info(f"Context research items: {len(context_web_research) if context_web_research else 0}")
            prompt = self.prompt_loader.load_prompt('column_definition', variables)

            # Load response schema
            schema = self.schema_validator.load_schema('column_definition_response')

            # Call AI API with structured output using sonar-pro (has web search for context research)
            web_searches = 3 if (context_web_research and len(context_web_research) > 0) else 0
            logger.info(f"Calling AI API with model: {model}, web_searches: {web_searches}")
            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=model,
                max_tokens=max_tokens,
                use_cache=False,  # Disable cache for local testing
                max_web_searches=web_searches,  # Enable web search if context items provided
                search_context_size='high',  # Use high context for better research
                debug_name="column_definition"
            )

            # Check for API errors
            if 'response' not in api_response and 'error' in api_response:
                error_detail = api_response.get('error', 'Unknown error')
                logger.error(f"API call failed: {error_detail}")
                raise Exception(f"AI API call failed: {error_detail}")

            # Extract structured response (same pattern as interview.py)
            raw_response = api_response.get('response', {})

            # Parse the structured content from choices[0].message.content
            if 'choices' in raw_response and len(raw_response['choices']) > 0:
                content = raw_response['choices'][0]['message']['content']
                ai_response = json.loads(content) if isinstance(content, str) else content
            elif 'columns' in raw_response and 'search_strategy' in raw_response:
                # Response is already structured (from cache or direct format)
                ai_response = raw_response
            else:
                logger.error(f"Unexpected response structure: {json.dumps(raw_response, indent=2)[:500]}")
                # Fallback to old extraction method
                ai_response = self._extract_structured_response(raw_response)

            logger.debug(f"Extracted AI response keys: {list(ai_response.keys())}")

            # Validate response against schema
            validation_result = self.schema_validator.validate_ai_response(
                ai_response,
                'column_definition_response'
            )

            if not validation_result['is_valid']:
                error_msg = f"AI response validation failed: {validation_result['errors']}"
                logger.error(error_msg)
                raise Exception(error_msg)

            # Verify validation strategies for research columns
            self._validate_column_strategies(ai_response.get('columns', []))

            # Build successful result
            result['success'] = True
            result['columns'] = ai_response.get('columns', [])
            result['search_strategy'] = ai_response.get('search_strategy', {})
            result['table_name'] = ai_response.get('table_name', '')
            result['tablewide_research'] = ai_response.get('tablewide_research', '')

            # Include cost information from enhanced_data
            enhanced_data = api_response.get('enhanced_data', {})
            if enhanced_data:
                costs = enhanced_data.get('costs', {})
                result['cost'] = costs.get('actual', {}).get('total_cost', 0.0)
                logger.info(f"Column definition cost from enhanced_data: ${result['cost']:.4f}")
            else:
                # Fallback: Calculate cost manually from token_usage
                logger.warning("No enhanced_data in API response, calculating cost from token_usage")
                token_usage = api_response.get('token_usage', {})
                input_tokens = token_usage.get('input_tokens', 0)
                output_tokens = token_usage.get('output_tokens', 0)

                # Claude Sonnet 4.5 pricing: $3/MTok input, $15/MTok output
                cost = (input_tokens / 1_000_000 * 3.0) + (output_tokens / 1_000_000 * 15.0)
                result['cost'] = cost
                logger.info(f"Column definition cost calculated: ${cost:.4f} (input={input_tokens}, output={output_tokens})")

            # Calculate processing time
            result['processing_time'] = time.time() - start_time

            logger.info(
                f"Column definition completed successfully. "
                f"Columns: {len(result['columns'])}, "
                f"Subdomains: {len(result['search_strategy'].get('subdomain_hints', []))}, "
                f"Time: {result['processing_time']:.1f}s"
            )

            # Log token usage if available
            if 'token_usage' in api_response:
                self._log_token_usage(api_response['token_usage'])

        except Exception as e:
            error_msg = f"Error defining columns: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['processing_time'] = time.time() - start_time

        return result

    def _format_conversation_history(self, conversation_context: Dict[str, Any]) -> str:
        """
        Format conversation history for prompt.

        Args:
            conversation_context: Conversation context dictionary

        Returns:
            Formatted conversation history string
        """
        try:
            # Extract conversation log
            conversation_log = conversation_context.get('conversation_log', [])

            if not conversation_log:
                return "No conversation history available"

            history_lines = []

            for idx, msg in enumerate(conversation_log, 1):
                role = msg.get('role', 'unknown').upper()
                content = msg.get('content', '')

                if role == 'USER':
                    history_lines.append(f"Turn {idx} - USER: {content}")
                elif role == 'ASSISTANT':
                    # For assistant, extract the natural language message
                    if isinstance(content, dict):
                        ai_message = content.get('ai_message', '')
                        history_lines.append(f"Turn {idx} - ASSISTANT: {ai_message}")
                    else:
                        history_lines.append(f"Turn {idx} - ASSISTANT: {content}")

            return '\n\n'.join(history_lines)

        except Exception as e:
            logger.warning(f"Error formatting conversation history: {e}")
            return "Error formatting conversation history"

    def _extract_user_requirements(self, conversation_context: Dict[str, Any]) -> str:
        """
        Extract user's approved requirements from conversation context.

        Args:
            conversation_context: Conversation context dictionary

        Returns:
            Formatted user requirements string
        """
        try:
            # Get the current proposal (what user approved)
            current_proposal = conversation_context.get('current_proposal', {})

            if not current_proposal:
                return "No specific requirements captured"

            # Format proposal as readable text
            rows_info = current_proposal.get('rows', {})
            columns_info = current_proposal.get('columns', [])

            requirements_parts = []

            # Add identification columns
            id_columns = rows_info.get('identification_columns', [])
            if id_columns:
                requirements_parts.append(f"**Identification Columns**: {', '.join(id_columns)}")

            # Add research columns
            research_columns = [
                col['name'] for col in columns_info
                if not col.get('is_identification', False)
            ]
            if research_columns:
                requirements_parts.append(f"**Research Columns**: {', '.join(research_columns)}")

            # Add column details
            if columns_info:
                requirements_parts.append("\n**Column Details**:")
                for col in columns_info:
                    col_desc = f"- {col['name']}: {col.get('description', 'No description')}"
                    requirements_parts.append(col_desc)

            # Add sample rows count
            sample_rows = rows_info.get('sample_rows', [])
            if sample_rows:
                requirements_parts.append(f"\n**Sample Rows Provided**: {len(sample_rows)}")

            return '\n'.join(requirements_parts)

        except Exception as e:
            logger.warning(f"Error extracting user requirements: {e}")
            return "Error extracting user requirements"

    def _extract_structured_response(self, raw_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured response from raw API response.

        Args:
            raw_response: Raw API response

        Returns:
            Parsed structured response dictionary
        """
        try:
            # Check if response is already structured
            if 'columns' in raw_response and 'search_strategy' in raw_response:
                return raw_response

            # Extract from Perplexity/Anthropic response format
            if 'choices' in raw_response:
                content = raw_response['choices'][0]['message']['content']
                if isinstance(content, str):
                    return json.loads(content)
                return content

            # Check for content field
            if 'content' in raw_response:
                content = raw_response['content']
                if isinstance(content, str):
                    return json.loads(content)
                elif isinstance(content, list) and len(content) > 0:
                    # Anthropic format: content[0]['text']
                    text_content = content[0].get('text', '{}')
                    return json.loads(text_content)
                return content

            # Fallback
            logger.warning(f"Unknown response structure, keys: {list(raw_response.keys())}")
            return raw_response

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from response: {e}")
            raise Exception(f"Failed to parse structured response: {e}")
        except Exception as e:
            logger.error(f"Error extracting structured response: {e}")
            raise

    def _validate_column_strategies(self, columns: list):
        """
        Validate that all research columns have validation strategies.

        Args:
            columns: List of column definitions

        Raises:
            ValueError: If research columns are missing validation strategies
        """
        missing_strategies = []

        for col in columns:
            # Check if this is a research column (not identification)
            if not col.get('is_identification', False):
                # Research column must have validation_strategy
                if not col.get('validation_strategy'):
                    missing_strategies.append(col.get('name', 'unknown'))

        if missing_strategies:
            error_msg = (
                f"Research columns missing validation_strategy: "
                f"{', '.join(missing_strategies)}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.debug(f"All {len(columns)} columns have proper validation strategies")

    def _log_token_usage(self, token_usage: Dict[str, Any]):
        """
        Log token usage information.

        Args:
            token_usage: Token usage dictionary from API response
        """
        input_tokens = token_usage.get('input_tokens', 0)
        output_tokens = token_usage.get('output_tokens', 0)
        total_tokens = token_usage.get('total_tokens', 0)

        logger.info(
            f"Token usage - Input: {input_tokens}, Output: {output_tokens}, "
            f"Total: {total_tokens}"
        )

    def get_search_strategy_summary(self, search_strategy: Dict[str, Any]) -> str:
        """
        Get a human-readable summary of the search strategy.

        Args:
            search_strategy: Search strategy dictionary

        Returns:
            Formatted summary string
        """
        description = search_strategy.get('description', 'No description')
        subdomain_hints = search_strategy.get('subdomain_hints', [])
        search_queries = search_strategy.get('search_queries', [])

        summary_parts = [
            f"**Description**: {description}",
            f"\n**Subdomains ({len(subdomain_hints)})**:"
        ]

        for idx, subdomain in enumerate(subdomain_hints, 1):
            summary_parts.append(f"  {idx}. {subdomain}")

        summary_parts.append(f"\n**Search Queries ({len(search_queries)})**:")
        for idx, query in enumerate(search_queries, 1):
            summary_parts.append(f"  {idx}. {query}")

        return '\n'.join(summary_parts)

    def get_columns_summary(self, columns: list) -> Dict[str, Any]:
        """
        Get a summary of the column definitions.

        Args:
            columns: List of column definitions

        Returns:
            Summary dictionary with statistics
        """
        id_columns = [col for col in columns if col.get('is_identification', False)]
        research_columns = [col for col in columns if not col.get('is_identification', False)]

        return {
            'total_columns': len(columns),
            'id_columns': len(id_columns),
            'research_columns': len(research_columns),
            'id_column_names': [col['name'] for col in id_columns],
            'research_column_names': [col['name'] for col in research_columns],
            'all_have_validation_strategies': all(
                col.get('validation_strategy') for col in research_columns
            )
        }
