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
                'tablewide_research': str,  # 2-3 paragraph overview
                'authoritative_sources': List[Dict],  # Databases, directories, APIs
                'starting_tables': List[Dict],  # Tables with sample entities (≤15 rows)
                'discovery_patterns': Dict,  # How entities are found
                'domain_specific_context': Dict,  # Key facts and identifiers
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
            'starting_tables': [],
            'discovery_patterns': {},
            'domain_specific_context': {},
            'identified_tables': [],  # NEW - for Step 0b triggering
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

            # Check if complete enumeration is requested (needs more tokens)
            is_complete_enumeration = False
            if context_research_items:
                is_complete_enumeration = any(
                    item.startswith('COMPLETE ENUMERATION:')
                    for item in context_research_items
                )

            # Boost max_tokens for complete enumeration cases (need room for full lists)
            if is_complete_enumeration:
                original_max_tokens = max_tokens
                max_tokens = min(max_tokens * 3, 24000)  # Triple tokens, cap at 24k
                logger.info(
                    f"[COMPLETE ENUMERATION] Detected - increasing max_tokens from "
                    f"{original_max_tokens} to {max_tokens} to accommodate full entity list"
                )

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

            # Validate required fields
            required_fields = ['tablewide_research', 'authoritative_sources', 'starting_tables',
                             'discovery_patterns', 'domain_specific_context']
            missing_fields = [f for f in required_fields if f not in structured_response]

            if missing_fields:
                logger.error(f"Missing required fields in AI response: {missing_fields}")
                raise Exception(f"AI response missing fields: {', '.join(missing_fields)}")

            # Validate starting tables have sample entities
            starting_tables = structured_response.get('starting_tables', [])
            for idx, table in enumerate(starting_tables):
                sample_entities = table.get('sample_entities', [])
                if len(sample_entities) < 5:
                    logger.warning(
                        f"Starting table {idx} '{table.get('source_name', 'unknown')}' "
                        f"has only {len(sample_entities)} sample entities (minimum 5 required)"
                    )

            # Extract enhanced_data for API call tracking
            enhanced_data = api_response.get('enhanced_data', {})

            # Success!
            result.update({
                'success': True,
                'tablewide_research': structured_response['tablewide_research'],
                'authoritative_sources': structured_response['authoritative_sources'],
                'starting_tables': structured_response['starting_tables'],
                'discovery_patterns': structured_response['discovery_patterns'],
                'domain_specific_context': structured_response['domain_specific_context'],
                'identified_tables': structured_response.get('identified_tables', []),  # NEW - for Step 0b
                'enhanced_data': enhanced_data,
                'processing_time': time.time() - start_time
            })

            logger.info(
                f"Background research complete: "
                f"{len(result['authoritative_sources'])} sources, "
                f"{len(result['starting_tables'])} starting tables, "
                f"{len(result.get('identified_tables', []))} identified tables, "
                f"time: {result['processing_time']:.2f}s"
            )

            # Log summary of starting tables
            for table in result['starting_tables']:
                logger.info(
                    f"  Starting table: {table.get('source_name')} "
                    f"({len(table.get('sample_entities', []))} sample entities)"
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

        # Tablewide Research
        output.append("## Background Research Summary\n")
        output.append(research_result['tablewide_research'])
        output.append("\n")

        # Authoritative Sources
        sources = research_result.get('authoritative_sources', [])
        if sources:
            output.append("\n## Authoritative Sources Found\n")
            for source in sources:
                output.append(f"**{source.get('name')}** ({source.get('type')})")
                output.append(f"- URL: {source.get('url')}")
                output.append(f"- Coverage: {source.get('coverage')}")
                output.append(f"- Access: {source.get('access')}")
                output.append(f"- {source.get('description')}")
                output.append("")

        # Starting Tables (MOST IMPORTANT)
        tables = research_result.get('starting_tables', [])
        if tables:
            output.append("\n## Starting Tables with Sample Entities\n")
            output.append("**CRITICAL: Use these sample entities as reference when designing ID columns and subdomains.**\n")
            for table in tables:
                output.append(f"\n**{table.get('source_name')}**")
                output.append(f"- Source: {table.get('source_url')}")
                output.append(f"- Entity Type: {table.get('entity_type')}")
                output.append(f"- Count: {table.get('entity_count_estimate')}")
                output.append(f"- Completeness: {table.get('completeness')}")
                output.append(f"\nSample Entities:")
                for entity in table.get('sample_entities', []):
                    output.append(f"  - {entity}")
                if table.get('discovery_notes'):
                    output.append(f"\nNotes: {table.get('discovery_notes')}")
                output.append("")

        # Discovery Patterns
        patterns = research_result.get('discovery_patterns', {})
        if patterns:
            output.append("\n## Discovery Strategy Recommendations\n")
            output.append(f"**Primary Pattern:** {patterns.get('primary_pattern')}")
            output.append(f"\n{patterns.get('description')}\n")

            challenges = patterns.get('challenges', [])
            if challenges:
                output.append("\n**Challenges:**")
                for challenge in challenges:
                    output.append(f"- {challenge}")

            recommendations = patterns.get('recommendations', [])
            if recommendations:
                output.append("\n**Recommendations:**")
                for rec in recommendations:
                    output.append(f"- {rec}")
            output.append("")

        # Domain Context
        context = research_result.get('domain_specific_context', {})
        if context:
            output.append("\n## Domain-Specific Context\n")

            key_facts = context.get('key_facts', [])
            if key_facts:
                output.append("**Key Facts:**")
                for fact in key_facts:
                    output.append(f"- {fact}")

            identifiers = context.get('common_identifiers', [])
            if identifiers:
                output.append("\n**Common Identifiers:**")
                for identifier in identifiers:
                    output.append(f"- {identifier}")

            availability = context.get('data_availability')
            if availability:
                output.append(f"\n**Data Availability:** {availability}")

        return "\n".join(output)
