#!/usr/bin/env python3
"""
Background research handler for table generation system.
Conducts initial research to find authoritative sources and starting tables BEFORE column definition.
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class BackgroundResearchHandler:
    """Handle background research to find authoritative sources and starting tables."""

    def __init__(self, ai_client, prompt_loader, schema_validator):
        """
        Initialize background research handler.

        Args:
            ai_client: AI API client instance (from ../../src/shared/ai_api_client.py)
            prompt_loader: PromptLoader instance
            schema_validator: SchemaValidator instance
        """
        self.ai_client = ai_client
        self.prompt_loader = prompt_loader
        self.schema_validator = schema_validator

        logger.info("Initialized BackgroundResearchHandler")

    async def conduct_research(
        self,
        conversation_context: Dict[str, Any],
        context_research_items: List[str] = None,
        model: str = "sonar-pro",
        max_tokens: int = 8000,
        search_context_size: str = "high",
        max_web_searches: int = 5
    ) -> Dict[str, Any]:
        """
        Conduct background research to find authoritative sources and starting tables.

        Args:
            conversation_context: Full conversation history and user requirements
            context_research_items: Optional list of specific items to research
            model: AI model to use (default: sonar-pro for Perplexity)
            max_tokens: Maximum tokens for AI response
            search_context_size: FOR PERPLEXITY ONLY - Search context size (low/medium/high, default: high)
            max_web_searches: FOR ANTHROPIC ONLY - Number of web searches (default: 5)

        Returns:
            Dictionary with results:
            {
                'success': bool,
                'tablewide_research': str,  # 2-3 paragraph overview (includes discovery patterns, domain context)
                'authoritative_sources': List[Dict],  # Databases, directories, APIs (name, url, description)
                'starting_tables_markdown': str,  # Markdown table with citations
                'citations': Dict,  # Citation number -> URL mapping
                'is_complete_enumeration': bool,  # True if all entities provided
                'identified_tables': List[Dict],  # Tables for Step 0b extraction (>15 rows)
                'processing_time': float,  # Seconds
                'enhanced_data': Dict,  # API call metadata
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'tablewide_research': '',
            'authoritative_sources': [],
            'starting_tables_markdown': '',  # New markdown format with citations
            'citations': {},  # Citation number -> URL mapping
            'is_complete_enumeration': False,
            'identified_tables': [],  # For Step 0b triggering
            'processing_time': 0.0,
            'enhanced_data': {},
            'error': None
        }

        start_time = time.time()

        try:
            logger.info("Starting background research process")

            # Extract conversation data
            conversation_history = self._format_conversation_history(conversation_context)
            user_requirements = self._extract_user_requirements(conversation_context)

            # Note: Token boost for complete enumeration removed - background research only outputs
            # 15 sample entities max. Column definition handles outputting complete rows and gets
            # token boost based on entity count.

            # Format context research items if provided
            research_items_text = ""
            if context_research_items and len(context_research_items) > 0:
                research_items_text = "\n\n**Specific Research Items:**\n"
                for item in context_research_items:
                    research_items_text += f"- {item}\n"
                research_items_text += "\nIncorporate findings about these items into your research output."

            # Build prompt with variables
            variables = {
                'CONVERSATION_CONTEXT': conversation_history,
                'USER_REQUIREMENTS': user_requirements,
                'CONTEXT_RESEARCH_ITEMS': research_items_text
            }

            logger.debug(f"Loading prompt template with {len(variables)} variables")
            logger.info(f"Context research items: {len(context_research_items) if context_research_items else 0}")
            prompt = self.prompt_loader.load_prompt('background_research', variables)

            # Load response schema
            schema = self.schema_validator.load_schema('background_research_response')

            # Determine which web search parameter to use based on model family
            is_perplexity = model.startswith('sonar')
            is_anthropic = model.startswith('claude')

            if is_perplexity:
                logger.info(
                    f"Calling AI API with Perplexity model: {model}, "
                    f"search_context_size: {search_context_size}"
                )
            elif is_anthropic:
                logger.info(
                    f"Calling AI API with Anthropic model: {model}, "
                    f"max_web_searches: {max_web_searches}"
                )
            else:
                logger.warning(f"Unknown model family: {model}, will pass both parameters")

            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=model,
                max_tokens=max_tokens,
                use_cache=True,  # Enable cache (standard practice)
                max_web_searches=max_web_searches,  # Used by Anthropic models
                search_context_size=search_context_size,  # Used by Perplexity models
                debug_name="background_research"
            )

            # Check for API errors
            if 'response' not in api_response and 'error' in api_response:
                error_detail = api_response.get('error', 'Unknown error')
                logger.error(f"API call failed: {error_detail}")
                raise Exception(f"AI API call failed: {error_detail}")

            # Extract structured response using AI client's method (handles all formats)
            raw_response = api_response.get('response', {})

            logger.debug(f"Raw response keys: {list(raw_response.keys())}")

            # Use AI client's extract_structured_response method (handles both Claude and Perplexity formats)
            try:
                structured_response = self.ai_client.extract_structured_response(
                    raw_response,
                    tool_name="background_research"  # Tool name for extraction
                )
                logger.debug(f"Extracted response keys: {list(structured_response.keys())}")
            except Exception as extract_error:
                logger.error(f"Failed to extract structured response: {extract_error}")
                logger.error(f"Response format: {json.dumps(raw_response, indent=2)[:1000]}")
                raise

            # Validate required fields (simplified schema)
            required_fields = ['tablewide_research', 'authoritative_sources', 'starting_tables_markdown', 'citations']
            missing_fields = [f for f in required_fields if f not in structured_response]

            if missing_fields:
                logger.error(f"Missing required fields in AI response: {missing_fields}")
                raise Exception(f"AI response missing fields: {', '.join(missing_fields)}")

            # Log markdown table info
            starting_markdown = structured_response.get('starting_tables_markdown', '')
            citations = structured_response.get('citations', {})
            row_count = len([line for line in starting_markdown.split('\n') if line.strip().startswith('|') and not line.strip().startswith('|-')])
            logger.info(f"Starting tables markdown has ~{row_count} rows, {len(citations)} citations")

            # Extract enhanced_data for API call tracking
            enhanced_data = api_response.get('enhanced_data', {})

            # Success!
            result.update({
                'success': True,
                'tablewide_research': structured_response['tablewide_research'],
                'authoritative_sources': structured_response['authoritative_sources'],
                'starting_tables_markdown': starting_markdown,
                'citations': citations,
                'is_complete_enumeration': structured_response.get('is_complete_enumeration', False),
                'identified_tables': structured_response.get('identified_tables', []),
                'enhanced_data': enhanced_data,
                'processing_time': time.time() - start_time
            })

            logger.info(
                f"Background research complete: "
                f"{len(result['authoritative_sources'])} sources, "
                f"{row_count} starting table rows, "
                f"{len(result.get('identified_tables', []))} identified tables, "
                f"time: {result['processing_time']:.2f}s"
            )

            # Log summary of identified tables
            for table in result.get('identified_tables', []):
                logger.info(
                    f"  Identified table: {table.get('table_name')} "
                    f"({table.get('estimated_rows')} rows, extract_table={table.get('extract_table')})"
                )

            return result

        except Exception as e:
            logger.error(f"Background research failed: {str(e)}", exc_info=True)
            result['error'] = str(e)
            result['processing_time'] = time.time() - start_time
            return result

    def _format_conversation_history(self, conversation_context: Dict[str, Any]) -> str:
        """
        Format conversation history for prompt.

        Args:
            conversation_context: Full conversation context

        Returns:
            Formatted conversation history string
        """
        # Try conversation_turns first (old format), then messages (new format)
        turns = conversation_context.get('conversation_turns', [])
        if not turns:
            turns = conversation_context.get('messages', [])

        if not turns:
            return "(No conversation history available)"

        formatted = []
        for turn in turns:
            role = turn.get('role', 'unknown')
            content = turn.get('content', '')

            if role == 'user':
                formatted.append(f"Turn {len(formatted)//2 + 1} - USER: {content}")
            elif role == 'assistant':
                # For assistant messages, check if it's JSON (interview response)
                # If so, extract the ai_message field for readability
                try:
                    parsed = json.loads(content) if isinstance(content, str) and content.startswith('{') else None
                    if parsed and 'ai_message' in parsed:
                        formatted.append(f"Turn {len(formatted)//2 + 1} - ASSISTANT: {parsed['ai_message']}")
                    else:
                        formatted.append(f"Turn {len(formatted)//2 + 1} - ASSISTANT: {content}")
                except:
                    formatted.append(f"Turn {len(formatted)//2 + 1} - ASSISTANT: {content}")

        return "\n\n".join(formatted)

    def _extract_user_requirements(self, conversation_context: Dict[str, Any]) -> str:
        """
        Extract user's requirements from conversation context.

        Args:
            conversation_context: Full conversation context

        Returns:
            User requirements string
        """
        # Try to get from approved_structure or table_purpose
        approved_structure = conversation_context.get('approved_structure', {})
        table_purpose = approved_structure.get('table_purpose', '')

        if table_purpose:
            return table_purpose

        # Fallback: Extract from last user turn
        turns = conversation_context.get('conversation_turns', [])
        user_turns = [t['content'] for t in turns if t.get('role') == 'user']

        if user_turns:
            return user_turns[-1]

        return "(No clear requirements extracted)"

    def format_research_for_column_definition(self, research_result: Dict[str, Any]) -> str:
        """
        Format research result for injection into column definition prompt.

        Args:
            research_result: Output from conduct_research()

        Returns:
            Formatted research string for column definition prompt
        """
        if not research_result.get('success'):
            return "(Background research failed - no data available)"

        output = []

        # Tablewide Research (now includes discovery patterns and domain context)
        output.append("## Background Research Summary\n")
        output.append(research_result['tablewide_research'])
        output.append("\n")

        # Authoritative Sources (simplified format)
        sources = research_result.get('authoritative_sources', [])
        if sources:
            output.append("\n## Authoritative Sources Found\n")
            for source in sources:
                output.append(f"**{source.get('name')}**")
                output.append(f"- URL: {source.get('url')}")
                output.append(f"- {source.get('description')}")
                output.append("")

        # Starting Tables (markdown format with citations)
        starting_markdown = research_result.get('starting_tables_markdown', '')
        citations = research_result.get('citations', {})
        is_complete = research_result.get('is_complete_enumeration', False)

        if starting_markdown:
            output.append("\n## Starting Entities from Research\n")
            if is_complete:
                output.append("**COMPLETE ENUMERATION: This is an exhaustive list - ALL entities are included.**\n")
            else:
                output.append("**CRITICAL: Use these entities as reference when designing ID columns. Add to prepopulated_rows_markdown.**\n")
            output.append(starting_markdown)
            output.append("")

            # Add citations below the table
            if citations:
                output.append("\n### Source Citations\n")
                for num, url in sorted(citations.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
                    output.append(f"[{num}] {url}")
                output.append("")

        return "\n".join(output)
