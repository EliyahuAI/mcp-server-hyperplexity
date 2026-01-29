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
        background_research_result: Dict[str, Any] = None,
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 8000
    ) -> Dict[str, Any]:
        """
        Define precise column specifications and search strategy using background research.

        Args:
            conversation_context: Full conversation history and approved requirements
            background_research_result: Output from background_research_handler (REQUIRED)
            model: AI model to use (default: claude-sonnet-4-5, no web search needed)
            max_tokens: Maximum tokens for AI response

        Returns:
            Dictionary with results:
            {
                'success': bool,
                'columns': List[Dict],  # Column definitions
                'search_strategy': Dict,  # Requirements + subdomains (if trigger_row_discovery=true)
                'table_name': str,
                'rows': List[Dict],  # Rows generated from available data (as many as possible)
                'trigger_row_discovery': bool,  # Whether to run row discovery
                'skip_rationale': Optional[str],  # Why skipping (if trigger_row_discovery=false)
                'discovery_guidance': Optional[str],  # What discovery should do (if trigger_row_discovery=true)
                'processing_time': float,
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'columns': [],
            'search_strategy': {},
            'table_name': '',
            'rows': [],
            'trigger_row_discovery': True,  # Will be overridden by AI (should default to false if unsure)
            'processing_time': 0.0,
            'error': None
        }

        start_time = time.time()

        try:
            logger.info("Starting column definition process")

            # Extract conversation data
            conversation_history = self._format_conversation_history(conversation_context)
            user_requirements = self._extract_user_requirements(conversation_context)

            # Format background research for injection
            if background_research_result and background_research_result.get('success'):
                formatted_research = self._format_research_for_prompt(background_research_result)
                logger.info("[RESEARCH] Injected background research into prompt")

                # Log entity count for visibility
                starting_markdown = background_research_result.get('starting_tables_markdown', '')
                extracted_tables = background_research_result.get('extracted_tables', [])

                total_entities = 0

                # Count from starting_tables_markdown (exclude header and separator lines)
                if starting_markdown:
                    rows = [line for line in starting_markdown.split('\n')
                           if line.strip().startswith('|') and not line.strip().startswith('|-')]
                    total_entities = max(0, len(rows) - 1)  # -1 for header

                # Count from extracted_tables
                for table in extracted_tables:
                    total_entities += table.get('rows_extracted', 0)

                logger.info(f"[ENTITY COUNT] Total entities to generate: {total_entities}, max_tokens: {max_tokens}")
            else:
                formatted_research = "(No background research available)"
                logger.warning("[RESEARCH] No background research provided - column definition may struggle")

            # Check if this is a restructure (after 0 rows found)
            restructuring_guidance = conversation_context.get('restructuring_guidance', {})
            is_restructure = restructuring_guidance.get('is_restructure', False)

            # Build restructuring section conditionally (not hardcoded in prompt)
            if is_restructure:
                logger.info("[RESTRUCTURE] Building restructuring section from guidance")

                # Get the original failed structure for reference
                original_columns = restructuring_guidance.get('original_columns', [])
                original_requirements = restructuring_guidance.get('original_requirements', [])

                # Format original structure
                original_structure = "**Original Failed Structure:**\n\n"
                if original_columns:
                    original_structure += "**ID Columns:** "
                    id_cols = [c.get('name', '') for c in original_columns if c.get('importance') == 'ID']
                    original_structure += ", ".join(id_cols) if id_cols else "(None)"
                    original_structure += "\n\n"

                    original_structure += "**Research Columns:** "
                    research_cols = [c.get('name', '') for c in original_columns if c.get('importance') in ['RESEARCH', 'CRITICAL']]
                    original_structure += ", ".join(research_cols) if research_cols else "(None)"
                    original_structure += "\n\n"

                if original_requirements:
                    original_structure += "**Hard Requirements:** "
                    hard = [r.get('requirement', '') for r in original_requirements if r.get('type') == 'hard']
                    original_structure += "; ".join(hard) if hard else "(None)"
                    original_structure += "\n\n"

                    original_structure += "**Soft Requirements:** "
                    soft = [r.get('requirement', '') for r in original_requirements if r.get('type') == 'soft']
                    original_structure += "; ".join(soft) if soft else "(None)"
                    original_structure += "\n"

                restructuring_section = f"""
═══════════════════════════════════════════════════════════════
## 🔄 RESTRUCTURING MODE - Previous Attempt Failed (0 Rows Found)
═══════════════════════════════════════════════════════════════

**IMPORTANT: This is a RESTRUCTURE after your previous table structure failed to find any rows.**

### What Failed

**Failure Reason:** {restructuring_guidance.get('failure_reason', 'Zero rows discovered')}

{original_structure}

### QC's Analysis and Guidance

**Column Changes Needed:**
{restructuring_guidance.get('column_changes', 'No specific guidance provided')}

**Requirement Changes Needed:**
{restructuring_guidance.get('requirement_changes', 'No specific guidance provided')}

**Search Strategy Changes:**
{restructuring_guidance.get('search_broadening', 'No specific guidance provided')}

### Your Restructure Task

Apply QC's guidance above to create a MORE DISCOVERABLE table:
1. **Simplify ID columns** - Make them 1-5 words, simple identifiers
2. **Relax requirements** - Move hard → soft → research columns
3. **Broaden search** - Target where entities are actually listed
4. **Add support columns** - Break complex validations into steps
5. **Prioritize FINDABILITY** over specificity

**Key Principle:** The entities likely exist, but your previous structure made them impossible to find via web search. Make it simpler and broader while keeping the user's intent.

**The background research is still valid and will be reused** - same starting tables and authoritative sources, just restructure how you use them.

---

"""
            else:
                restructuring_section = ""  # Empty for normal mode

            # Build prompt with variables
            variables = {
                'CONVERSATION_CONTEXT': conversation_history,
                'USER_REQUIREMENTS': user_requirements,
                'BACKGROUND_RESEARCH': formatted_research,
                'RESTRUCTURING_SECTION': restructuring_section
            }

            logger.debug(f"Loading prompt template with {len(variables)} variables (restructure={is_restructure})")
            prompt = self.prompt_loader.load_prompt('column_definition', variables)

            # Load response schema
            schema = self.schema_validator.load_schema('column_definition_response')

            # Call API (no web search - extract from conversation if needed)
            logger.info(f"Calling AI API with model: {model} (no web search - using research output or conversation)")

            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=model,
                max_tokens=max_tokens,
                max_web_searches=0,  # NO web search - can extract from conversation history
                use_cache=True,  # Enable cache (standard practice)
                debug_name="column_definition"
            )

            # Check for API errors
            if 'response' not in api_response and 'error' in api_response:
                error_detail = api_response.get('error', 'Unknown error')
                logger.error(f"API call failed: {error_detail}")
                raise Exception(f"AI API call failed: {error_detail}")

            # Extract structured response using AI client's method (handles all formats)
            raw_response = api_response.get('response', {})

            logger.debug(f"Raw response keys: {list(raw_response.keys())}")

            # Use AI client's extract_structured_response method
            try:
                ai_response = self.ai_client.extract_structured_response(
                    raw_response,
                    tool_name="column_definition"
                )
                logger.debug(f"Extracted AI response keys: {list(ai_response.keys())}")
            except Exception as extract_error:
                logger.error(f"Failed to extract structured response: {extract_error}")
                logger.error(f"Response format: {json.dumps(raw_response, indent=2)[:500]}")
                raise

            # Pre-validation fix: If AI set trigger_row_discovery=true but forgot subdomains,
            # auto-generate a basic subdomain so row discovery can still run
            trigger_row_discovery = ai_response.get('trigger_row_discovery', True)
            search_strategy = ai_response.get('search_strategy', {})
            subdomains = search_strategy.get('subdomains', [])
            num_rows = len(ai_response.get('rows', []))
            table_name = ai_response.get('table_name', 'Research Table')
            discovery_guidance = ai_response.get('discovery_guidance', '')

            if trigger_row_discovery and len(subdomains) == 0:
                # Auto-generate a subdomain based on table context with smarter queries
                description = search_strategy.get('description', table_name)
                requirements = search_strategy.get('requirements', [])

                # Extract key terms from hard requirements for better queries
                hard_reqs = [r.get('requirement', '') for r in requirements if r.get('type') == 'hard']

                # Truncate table_name at word boundary if too long
                if len(table_name) > 35:
                    truncated_name = table_name[:35].rsplit(' ', 1)[0]
                else:
                    truncated_name = table_name

                # Build smarter search queries with year modifiers and list-finding terms
                search_queries = [
                    f"{description} complete list 2024 2025",
                    f"top {table_name} comprehensive database",
                    f"{description} directory all entries"
                ]

                # Add requirement-based query if available
                if hard_reqs and hard_reqs[0]:
                    search_queries.append(f"{hard_reqs[0]} list database 2024")

                # Limit to 4 queries max
                search_queries = search_queries[:4]

                auto_subdomain = {
                    "name": f"General {truncated_name}",
                    "focus": discovery_guidance if discovery_guidance else f"Find all {description}",
                    "search_queries": search_queries,
                    "target_rows": max(20, num_rows)  # Target at least 20 or match existing rows
                }

                # Inject the auto-generated subdomain
                search_strategy['subdomains'] = [auto_subdomain]
                ai_response['search_strategy'] = search_strategy

                logger.warning(
                    f"[AUTO-FIX] AI set trigger_row_discovery=true but provided no subdomains. "
                    f"Auto-generated subdomain: '{auto_subdomain['name']}' with {auto_subdomain['target_rows']} target rows. "
                    f"Queries: {search_queries}. "
                    f"Discovery guidance: {discovery_guidance[:100] if discovery_guidance else 'None'}..."
                )

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

            # Validate trigger_row_discovery + subdomains consistency
            trigger_row_discovery = ai_response.get('trigger_row_discovery', True)
            subdomains = search_strategy.get('subdomains', [])
            num_subdomains = len(subdomains)
            discovery_guidance = ai_response.get('discovery_guidance')
            skip_rationale = ai_response.get('skip_rationale')
            num_rows = len(ai_response.get('rows', []))

            if trigger_row_discovery:
                # TRUE path validation
                if num_subdomains == 0:
                    error_msg = (
                        f"🚨 COLUMN DEFINITION ERROR: trigger_row_discovery=true but no subdomains provided! "
                        f"AI generated {num_rows} rows. "
                        f"REQUIRED: Include 'subdomains' array (1-10 items) in search_strategy. "
                        f"OR: Set trigger_row_discovery=false if the {num_rows} rows are sufficient. "
                        f"Discovery guidance was: {discovery_guidance}"
                    )
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                if not discovery_guidance:
                    logger.warning("trigger_row_discovery=true but discovery_guidance is missing (should be required)")
            else:
                # FALSE path validation
                if num_subdomains > 0:
                    error_msg = (
                        f"trigger_row_discovery=false but subdomains were provided ({num_subdomains} subdomains). "
                        f"Subdomains should only be present when trigger_row_discovery=true."
                    )
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                if not skip_rationale:
                    logger.warning("trigger_row_discovery=false but skip_rationale is missing (should be required)")

            logger.info(f"Trigger validation passed: trigger_row_discovery={trigger_row_discovery}, subdomains={num_subdomains}, rows={num_rows}")

            # Build successful result
            result['success'] = True
            result['columns'] = ai_response.get('columns', [])
            result['search_strategy'] = search_strategy
            result['table_name'] = ai_response.get('table_name', '')
            result['rows'] = ai_response.get('rows', [])
            # NEW: Pass through markdown table format (schema now uses this instead of rows array)
            result['prepopulated_rows_markdown'] = ai_response.get('prepopulated_rows_markdown', '')
            result['citations'] = ai_response.get('citations', {})
            result['trigger_row_discovery'] = ai_response.get('trigger_row_discovery', True)
            result['skip_rationale'] = ai_response.get('skip_rationale')
            result['discovery_guidance'] = ai_response.get('discovery_guidance')

            # Log row generation (check both formats)
            row_count = len(result['rows'])
            has_markdown = bool(result.get('prepopulated_rows_markdown'))

            # If using new markdown format, estimate row count from markdown
            if has_markdown and row_count == 0:
                markdown_lines = result['prepopulated_rows_markdown'].split('\n')
                # Count non-empty lines excluding header and separator
                data_lines = [line for line in markdown_lines if line.strip() and not line.startswith('|---')]
                row_count_estimate = max(0, len(data_lines) - 1)  # Subtract header row
                format_info = f"{row_count_estimate} rows (markdown format)"
            else:
                format_info = f"{row_count} rows (array format)"

            trigger_discovery = result['trigger_row_discovery']

            if trigger_discovery:
                logger.info(
                    f"Column definition generated {format_info}, "
                    f"triggering row discovery to find/populate more"
                )
                if result.get('discovery_guidance'):
                    logger.info(f"Discovery guidance: {result['discovery_guidance'][:100]}...")
            else:
                logger.info(
                    f"Column definition generated {format_info}, "
                    f"skipping row discovery (complete set)"
                )
                if result.get('skip_rationale'):
                    logger.info(f"Skip rationale: {result['skip_rationale'][:100]}...")

            # Extract and format requirements for downstream use
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

                # Add formatted requirements to search_strategy
                result['search_strategy']['formatted_hard_requirements'] = result['formatted_hard_requirements']
                result['search_strategy']['formatted_soft_requirements'] = result['formatted_soft_requirements']

                # Add discovery guidance if provided (tells discovery what to focus on)
                if result.get('discovery_guidance'):
                    result['search_strategy']['discovery_guidance'] = result['discovery_guidance']

            # PHASE 1: Capture enhanced_data and call metadata
            enhanced_data = api_response.get('enhanced_data', {})
            result['enhanced_data'] = enhanced_data
            result['call_description'] = "Creating Columns"
            # Extract actual model from enhanced_data or fall back to requested model
            result['model_used'] = enhanced_data.get('model_used', model) if enhanced_data else model

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
                if col.get('importance', '').upper() != 'ID'
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
            # Check if this is a research column (importance != "ID")
            if col.get('importance', '').upper() != 'ID':
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
        id_columns = [col for col in columns if col.get('importance', '').upper() == 'ID']
        research_columns = [col for col in columns if col.get('importance', '').upper() != 'ID']

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

    def _format_research_for_prompt(self, research_result: Dict[str, Any]) -> str:
        """
        Format background research result for injection into column definition prompt.

        Args:
            research_result: Output from background_research_handler.conduct_research()

        Returns:
            Formatted research string for prompt injection
        """
        if not research_result or not research_result.get('success'):
            return "(Background research unavailable)"

        output = []

        # Tablewide Research Summary
        tablewide = research_result.get('tablewide_research', '')
        if tablewide:
            output.append("### Research Summary\n")
            output.append(tablewide)
            output.append("\n")

        # Authoritative Sources
        sources = research_result.get('authoritative_sources', [])
        if sources:
            output.append("\n### Authoritative Sources\n")
            for source in sources:
                output.append(f"**{source.get('name')}** ({source.get('type')})")
                output.append(f"- URL: {source.get('url')}")
                output.append(f"- Coverage: {source.get('coverage')}")
                output.append(f"- {source.get('description')}")
                output.append("")

        # Extracted Tables (from Step 0b - PRIORITY for JUMP START)
        extracted = research_result.get('extracted_tables', [])
        if extracted:
            output.append("\n### Extracted Tables (Complete Data from Step 0b)\n")
            output.append("**PRIORITY: Use these for JUMP START mode (complete_rows)**\n")
            for table in extracted:
                output.append(f"\n**{table.get('table_name')}**")
                output.append(f"- Primary Source: {table.get('source_url')}")

                # Handle NEW simple extraction format (markdown_table)
                if 'markdown_table' in table:
                    output.append(f"- Extraction Method: {table.get('extraction_method')}")
                    output.append(f"- Sources Count: {table.get('rows_count')}")  # Number of sources in simple extraction

                    # List all source URLs
                    source_urls = table.get('source_urls', [])
                    if source_urls:
                        output.append(f"\n**Source URLs ({len(source_urls)} total):**")
                        for url in source_urls:
                            output.append(f"  - {url}")

                    # Show markdown table data
                    markdown = table.get('markdown_table', '')
                    if markdown:
                        output.append(f"\n**Extracted Table Data (Markdown):**\n")
                        output.append("```")
                        output.append(markdown)
                        output.append("```")

                    output.append("\n**Parse this markdown to define columns and extract rows.**")
                    output.append(f"**For each row you extract, populate source_urls with: {source_urls}**")

                # Handle OLD structured extraction format (backward compatibility)
                elif 'rows' in table:
                    output.append(f"- Rows Extracted: {table.get('rows_extracted')}")
                    output.append(f"- Extraction Complete: {table.get('extraction_complete')}")

                    rows = table.get('rows', [])
                    if rows and len(rows) > 0:
                        output.append(f"\n**ALL Extracted Rows ({len(rows)} total):**")
                        for i, row in enumerate(rows):
                            output.append(f"  Row {i+1}: {row}")

                    output.append("\n**Use these rows - all extracted data is shown above.**")

                output.append("")

        # Starting Tables (markdown format with citations)
        starting_markdown = research_result.get('starting_tables_markdown', '')
        citations = research_result.get('citations', {})
        is_complete = research_result.get('is_complete_enumeration', False)

        if starting_markdown:
            output.append("\n### Starting Entities from Research\n")
            if is_complete:
                output.append("**COMPLETE ENUMERATION: This is an exhaustive list - ALL entities are included.**\n")
            else:
                output.append("**Use these entities as reference when designing ID columns. Add to prepopulated_rows_markdown.**\n")
            output.append(starting_markdown)
            output.append("")

            # Add citations below the table
            if citations:
                output.append("\n### Source Citations\n")
                for num, url in sorted(citations.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
                    output.append(f"[{num}] {url}")
                output.append("")

        return "\n".join(output)
