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
        model: str = "claude-haiku-4-5",
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

            # ALWAYS enable web search for column definition to find authoritative lists
            # Use more searches if we have context research items, but always search
            has_context_research = context_web_research and len(context_web_research) > 0
            web_searches = 5 if has_context_research else 3

            # Use sonar-pro (best search model) for column definition since we always need web access
            actual_model = "sonar-pro"

            logger.info(
                f"Calling AI API with model: {actual_model}, "
                f"web_searches: {web_searches} (always enabled for list discovery), "
                f"context_items: {len(context_web_research) if context_web_research else 0}"
            )

            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=actual_model,
                max_tokens=max_tokens,
                use_cache=False,  # Disable cache for local testing
                max_web_searches=web_searches,  # Always enabled to find authoritative lists
                search_context_size='high',  # Always use high context for comprehensive list discovery
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

            # Validate requirements (Phase 1, Item 2)
            search_strategy = ai_response.get('search_strategy', {})
            requirements = search_strategy.get('requirements', [])

            if not requirements or len(requirements) == 0:
                error_msg = "search_strategy.requirements must have at least 1 item (hard or soft)"
                logger.error(error_msg)
                raise ValueError(error_msg)

            logger.info(f"Requirements validation passed: {len(requirements)} requirements found")

            # Build successful result
            result['success'] = True
            result['columns'] = ai_response.get('columns', [])
            result['search_strategy'] = search_strategy
            result['table_name'] = ai_response.get('table_name', '')
            result['tablewide_research'] = ai_response.get('tablewide_research', '')

            # Extract and format requirements for downstream use (Phase 1, Items 2 and 4)
            hard_reqs, soft_reqs = self._separate_requirements(requirements)
            result['formatted_hard_requirements'] = self._format_requirements_for_prompt(hard_reqs)
            result['formatted_soft_requirements'] = self._format_requirements_for_prompt(soft_reqs)

            # Extract domain filtering for downstream use
            result['default_included_domains'] = search_strategy.get('default_included_domains', [])
            result['default_excluded_domains'] = search_strategy.get('default_excluded_domains', [])

            logger.info(
                f"Requirements formatted: {len(hard_reqs)} hard, {len(soft_reqs)} soft | "
                f"Domain filtering: {len(result['default_included_domains'])} included, "
                f"{len(result['default_excluded_domains'])} excluded"
            )

            # Add full context to search_strategy for row discovery and QC
            user_request = conversation_context.get('user_request', '')
            if user_request and result['search_strategy']:
                result['search_strategy']['user_context'] = user_request
                result['search_strategy']['table_purpose'] = result['search_strategy'].get('description', '')
                result['search_strategy']['tablewide_research'] = result.get('tablewide_research', '')

                # Add formatted requirements to search_strategy (Phase 1, Item 2)
                result['search_strategy']['formatted_hard_requirements'] = result['formatted_hard_requirements']
                result['search_strategy']['formatted_soft_requirements'] = result['formatted_soft_requirements']

            # PHASE 1: Capture enhanced_data and call metadata
            enhanced_data = api_response.get('enhanced_data', {})
            result['enhanced_data'] = enhanced_data
            result['call_description'] = "Creating Columns"
            result['model_used'] = actual_model

            # Include cost information from enhanced_data
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
            # Extract conversation log (try new 'messages' field first, then fall back to old 'conversation_log')
            conversation_log = conversation_context.get('messages', []) or conversation_context.get('conversation_log', [])

            if not conversation_log:
                logger.warning("No conversation history found in conversation_context")
                return "No conversation history available"

            history_lines = []

            for idx, msg in enumerate(conversation_log, 1):
                role = msg.get('role', 'unknown').lower()
                content = msg.get('content', '')

                if role == 'user':
                    history_lines.append(f"Turn {idx} - USER: {content}")
                elif role == 'assistant':
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

            if requirements_parts:
                return '\n'.join(requirements_parts)

            # Fallback 1: Use raw user request if no proposal structure
            user_request = conversation_context.get('user_request', '')
            if user_request:
                logger.info("No current_proposal found, using raw user_request")
                return f"User Request:\n{user_request}"

            # Fallback 2: Extract from messages array (new interview system)
            messages = conversation_context.get('messages', [])
            if messages:
                # Get full conversation (user + AI)
                conversation_lines = []
                for msg in messages:
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    if role == 'user':
                        conversation_lines.append(f"**User:** {content}")
                    elif role == 'assistant':
                        conversation_lines.append(f"**AI:** {content}")

                if conversation_lines:
                    logger.info("Extracting full conversation as context for column definition")
                    return "Conversation History:\n\n" + '\n\n'.join(conversation_lines)

            return "No specific requirements captured"

        except Exception as e:
            logger.warning(f"Error extracting user requirements: {e}")
            # Fallback: Use raw user request
            user_request = conversation_context.get('user_request', '')
            if user_request:
                return f"User Request:\n{user_request}"
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

    def _separate_requirements(self, requirements: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Separate requirements into hard and soft lists.

        Args:
            requirements: List of requirement dictionaries with 'type' field

        Returns:
            Tuple of (hard_requirements, soft_requirements)
        """
        hard_requirements = [req for req in requirements if req.get('type') == 'hard']
        soft_requirements = [req for req in requirements if req.get('type') == 'soft']

        logger.debug(
            f"Separated requirements: {len(hard_requirements)} hard, "
            f"{len(soft_requirements)} soft"
        )

        return hard_requirements, soft_requirements

    def _format_requirements_for_prompt(self, requirements: List[Dict[str, Any]]) -> str:
        """
        Format requirements as bullet list for prompts.

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

        formatted = '\n'.join(bullet_points)
        logger.debug(f"Formatted {len(requirements)} requirements into bullet list")

        return formatted
