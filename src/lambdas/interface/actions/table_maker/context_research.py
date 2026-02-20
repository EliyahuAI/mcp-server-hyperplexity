#!/usr/bin/env python3
"""
Context research module for table maker lambda integration.

Performs web search to understand user's domain and research needs,
extracting key insights to enhance table generation.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ContextResearcher:
    """
    Perform web search-based context research to understand user's domain.

    Uses Perplexity API (sonar models) to search the web for domain context,
    key players, common data points, and research patterns in the user's field.
    """

    def __init__(self, ai_client, config: Dict[str, Any]):
        """
        Initialize context researcher.

        Args:
            ai_client: AI API client instance (supports Perplexity sonar models)
            config: Table maker configuration dict (from table_maker_config.json)
        """
        self.ai_client = ai_client
        self.config = config

        # Extract configuration
        conv_config = config.get('conversation', {})
        self.enabled = config.get('features', {}).get('enable_context_research', True)
        self.max_searches = conv_config.get('context_web_searches', 3)
        self.model = conv_config.get('model', 'claude-sonnet-4-6')

        # Use sonar model for web searches (Perplexity)
        self.search_model = 'sonar-pro'  # Perplexity's web search model

        logger.info(
            f"ContextResearcher initialized: enabled={self.enabled}, "
            f"max_searches={self.max_searches}, search_model={self.search_model}"
        )

    async def perform_context_research(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Perform web search to understand user's domain and research needs.

        Args:
            user_message: User's initial request or latest message
            conversation_history: Optional list of previous conversation messages

        Returns:
            Dictionary with research results:
            {
                'success': bool,
                'insights': str,           # Summary of key insights
                'domain': str,             # Identified domain/field
                'key_entities': List[str], # Important entities/players
                'data_patterns': List[str],# Common data patterns in domain
                'sources': List[str],      # URLs used for research
                'search_performed': bool,  # Whether search was actually performed
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'insights': '',
            'domain': 'unknown',
            'key_entities': [],
            'data_patterns': [],
            'sources': [],
            'search_performed': False,
            'error': None
        }

        try:
            # Check if context research is enabled
            if not self.enabled:
                logger.info("Context research disabled in config")
                result['success'] = True
                result['insights'] = 'Context research disabled'
                result['search_performed'] = False
                return result

            logger.info(f"Starting context research for: '{user_message[:100]}...'")

            # Build research query from user message
            research_query = self._build_research_query(user_message, conversation_history)

            # Perform web search using Perplexity API
            search_result = await self._perform_web_search(research_query)

            if not search_result['success']:
                # Non-fatal error - continue without context research
                logger.warning(f"Web search failed: {search_result.get('error')}")
                result['success'] = True
                result['insights'] = 'Context research unavailable'
                result['error'] = search_result.get('error')
                return result

            # Extract domain insights from search results
            insights_data = self.extract_domain_insights(
                search_result['response'],
                user_message
            )

            # Build result
            result['success'] = True
            result['insights'] = insights_data['insights']
            result['domain'] = insights_data['domain']
            result['key_entities'] = insights_data['key_entities']
            result['data_patterns'] = insights_data['data_patterns']
            result['sources'] = search_result.get('sources', [])
            result['search_performed'] = True

            logger.info(
                f"Context research completed. Domain: {result['domain']}, "
                f"Entities: {len(result['key_entities'])}, Sources: {len(result['sources'])}"
            )

        except Exception as e:
            error_msg = f"Error in context research: {str(e)}"
            logger.error(error_msg)
            # Non-fatal - return success with error note
            result['success'] = True
            result['insights'] = 'Context research encountered an error'
            result['error'] = error_msg

        return result

    def _build_research_query(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, Any]]]
    ) -> str:
        """
        Build research query for web search.

        Args:
            user_message: User's message
            conversation_history: Optional conversation history

        Returns:
            Research query string optimized for web search
        """
        # Extract key concepts from user message
        # Focus on: domain, entities, data types, research purpose

        query_parts = [
            "Research the following domain and provide context:",
            "",
            user_message,
            "",
            "Identify:",
            "1. What domain/field is this in?",
            "2. What are the key entities, companies, or players in this space?",
            "3. What data points are commonly tracked in this domain?",
            "4. What are typical research patterns or use cases?",
        ]

        # Add conversation context if available
        if conversation_history and len(conversation_history) > 0:
            query_parts.extend([
                "",
                "Additional context from conversation:",
                self._format_conversation_context(conversation_history)
            ])

        return '\n'.join(query_parts)

    def _format_conversation_context(self, conversation_history: List[Dict[str, Any]]) -> str:
        """Format conversation history for research query."""
        context_lines = []

        for msg in conversation_history[-3:]:  # Last 3 messages only
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')

            if role == 'user':
                context_lines.append(f"User: {content}")
            elif role == 'assistant' and isinstance(content, dict):
                ai_msg = content.get('ai_message', '')
                if ai_msg:
                    context_lines.append(f"Assistant: {ai_msg}")

        return '\n'.join(context_lines)

    async def _perform_web_search(self, query: str) -> Dict[str, Any]:
        """
        Perform web search using Perplexity API.

        Args:
            query: Search query

        Returns:
            Dictionary with search results:
            {
                'success': bool,
                'response': str,      # AI response with search results
                'sources': List[str], # Source URLs
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'response': '',
            'sources': [],
            'error': None
        }

        try:
            logger.info(f"Performing web search with model: {self.search_model}")

            # Use Perplexity's sonar model for web search
            # This model automatically searches the web and provides citations
            api_response = await self.ai_client.validate_with_perplexity(
                prompt=query,
                model=self.search_model,
                search_context_size='high',  # Use high context for comprehensive research
                use_cache=True  # Cache research results
            )

            # Extract response text
            response_text = self._extract_response_text(api_response.get('response', {}))

            # Extract citations/sources
            citations = api_response.get('citations', [])
            sources = [cite.get('url', '') for cite in citations if cite.get('url')]

            result['success'] = True
            result['response'] = response_text
            result['sources'] = sources

            logger.info(f"Web search completed. Sources found: {len(sources)}")

        except Exception as e:
            error_msg = f"Web search failed: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg

        return result

    def _extract_response_text(self, response: Dict[str, Any]) -> str:
        """
        Extract response text from API response.

        Args:
            response: API response dictionary

        Returns:
            Extracted response text
        """
        try:
            # Handle different response formats
            if isinstance(response, str):
                return response

            if 'choices' in response:
                # OpenAI/Perplexity format
                content = response['choices'][0]['message']['content']
                if isinstance(content, str):
                    return content
                elif isinstance(content, dict):
                    return content.get('text', str(content))

            if 'content' in response:
                # Anthropic format
                content = response['content']
                if isinstance(content, str):
                    return content
                elif isinstance(content, list) and len(content) > 0:
                    return content[0].get('text', '')

            # Fallback: convert to string
            return str(response)

        except Exception as e:
            logger.error(f"Error extracting response text: {e}")
            return str(response)

    def extract_domain_insights(
        self,
        search_response: str,
        user_message: str
    ) -> Dict[str, Any]:
        """
        Extract domain insights from web search results.

        Args:
            search_response: Web search response text
            user_message: Original user message

        Returns:
            Dictionary with extracted insights:
            {
                'insights': str,           # Summary of key insights
                'domain': str,             # Identified domain
                'key_entities': List[str], # Important entities
                'data_patterns': List[str] # Common data patterns
            }
        """
        result = {
            'insights': '',
            'domain': 'unknown',
            'key_entities': [],
            'data_patterns': []
        }

        try:
            # Use simple heuristics to extract insights from search response
            # In production, could use additional AI call to structure this

            # Extract domain
            domain = self._identify_domain(search_response, user_message)
            result['domain'] = domain

            # Extract key entities (companies, institutions, key terms)
            entities = self._extract_entities(search_response)
            result['key_entities'] = entities[:10]  # Top 10 entities

            # Extract common data patterns
            patterns = self._extract_data_patterns(search_response, user_message)
            result['data_patterns'] = patterns

            # Build comprehensive insights summary
            insights_parts = [
                f"Domain: {domain}",
                "",
                "Search results indicate this is related to "
                f"{domain.lower()}. "
            ]

            if entities:
                insights_parts.append(
                    f"Key entities/players include: {', '.join(entities[:5])}. "
                )

            if patterns:
                insights_parts.append(
                    f"Common data points tracked: {', '.join(patterns[:5])}. "
                )

            # Add excerpt from search response (first 500 chars)
            excerpt = search_response[:500].strip()
            if len(search_response) > 500:
                excerpt += "..."

            insights_parts.extend([
                "",
                "Research Context:",
                excerpt
            ])

            result['insights'] = '\n'.join(insights_parts)

        except Exception as e:
            logger.error(f"Error extracting domain insights: {e}")
            result['insights'] = f"Context research completed. Search response available but insights extraction failed: {str(e)}"

        return result

    def _identify_domain(self, search_response: str, user_message: str) -> str:
        """
        Identify the domain/field from search results.

        Args:
            search_response: Search results text
            user_message: User's original message

        Returns:
            Identified domain string
        """
        # Common domain keywords
        domain_keywords = {
            'biotech': ['biotech', 'pharmaceutical', 'drug', 'therapy', 'clinical'],
            'ai_ml': ['artificial intelligence', 'machine learning', 'deep learning', 'neural network', 'AI', 'ML'],
            'finance': ['financial', 'investment', 'banking', 'trading', 'market'],
            'healthcare': ['healthcare', 'medical', 'patient', 'hospital', 'health'],
            'research': ['research', 'academic', 'scientific', 'paper', 'publication'],
            'technology': ['technology', 'software', 'hardware', 'tech', 'computing'],
            'business': ['business', 'company', 'enterprise', 'corporate', 'startup'],
            'energy': ['energy', 'renewable', 'solar', 'wind', 'power'],
            'education': ['education', 'learning', 'teaching', 'school', 'university']
        }

        combined_text = (user_message + ' ' + search_response).lower()

        # Count keyword matches
        domain_scores = {}
        for domain, keywords in domain_keywords.items():
            score = sum(1 for kw in keywords if kw.lower() in combined_text)
            if score > 0:
                domain_scores[domain] = score

        # Return domain with highest score
        if domain_scores:
            best_domain = max(domain_scores.items(), key=lambda x: x[1])[0]
            return best_domain.replace('_', ' ').title()

        return 'General Research'

    def _extract_entities(self, search_response: str) -> List[str]:
        """
        Extract key entities (companies, institutions) from search results.

        Args:
            search_response: Search results text

        Returns:
            List of entity names
        """
        entities = []

        # Simple capitalized word extraction (proper nouns)
        # In production, could use NER (Named Entity Recognition)
        words = search_response.split()

        for i, word in enumerate(words):
            # Look for capitalized words (not at sentence start)
            if word and word[0].isupper():
                # Check if previous word suggests this is an entity
                if i > 0:
                    prev_word = words[i-1].lower()
                    # Entity indicators
                    if prev_word in ['company', 'inc.', 'corp.', 'ltd.', 'llc', 'university', 'institute']:
                        clean_word = word.strip('.,;:!?')
                        if len(clean_word) > 2:
                            entities.append(clean_word)
                    # Also capture standalone capitalized words (likely proper nouns)
                    elif len(word) > 3 and word.isalpha():
                        entities.append(word)

        # Remove duplicates while preserving order
        seen = set()
        unique_entities = []
        for entity in entities:
            if entity not in seen:
                seen.add(entity)
                unique_entities.append(entity)

        return unique_entities

    def _extract_data_patterns(self, search_response: str, user_message: str) -> List[str]:
        """
        Extract common data patterns from search results.

        Args:
            search_response: Search results text
            user_message: User's original message

        Returns:
            List of common data patterns
        """
        patterns = []

        # Common data pattern keywords
        data_keywords = {
            'metrics': ['metric', 'kpi', 'measurement', 'score', 'rating'],
            'identifiers': ['id', 'identifier', 'code', 'number', 'reference'],
            'temporal': ['date', 'time', 'year', 'period', 'duration'],
            'financial': ['price', 'cost', 'revenue', 'funding', 'valuation'],
            'quantitative': ['count', 'quantity', 'volume', 'amount', 'total'],
            'qualitative': ['description', 'category', 'type', 'classification', 'status'],
            'location': ['location', 'address', 'country', 'region', 'area'],
            'contact': ['email', 'phone', 'contact', 'website', 'url']
        }

        combined_text = (user_message + ' ' + search_response).lower()

        # Find mentioned data patterns
        for pattern_type, keywords in data_keywords.items():
            if any(kw in combined_text for kw in keywords):
                patterns.append(pattern_type.replace('_', ' ').title() + ' Data')

        return patterns

    def is_enabled(self) -> bool:
        """
        Check if context research is enabled.

        Returns:
            True if enabled, False otherwise
        """
        return self.enabled

    def get_config(self) -> Dict[str, Any]:
        """
        Get current configuration.

        Returns:
            Configuration dictionary
        """
        return {
            'enabled': self.enabled,
            'max_searches': self.max_searches,
            'search_model': self.search_model,
            'conversation_model': self.model
        }


# Convenience functions for backward compatibility and ease of use

async def perform_context_research(
    ai_client,
    config: Dict[str, Any],
    user_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Convenience function to perform context research.

    Args:
        ai_client: AI API client instance
        config: Table maker configuration dict
        user_message: User's message
        conversation_history: Optional conversation history

    Returns:
        Dictionary with research results (see ContextResearcher.perform_context_research)
    """
    researcher = ContextResearcher(ai_client, config)
    return await researcher.perform_context_research(user_message, conversation_history)


def extract_domain_insights(
    search_response: str,
    user_message: str
) -> Dict[str, Any]:
    """
    Convenience function to extract domain insights from search results.

    Args:
        search_response: Web search response text
        user_message: User's original message

    Returns:
        Dictionary with extracted insights (see ContextResearcher.extract_domain_insights)
    """
    # Create a minimal researcher instance just for insights extraction
    researcher = ContextResearcher(None, {'features': {'enable_context_research': False}})
    return researcher.extract_domain_insights(search_response, user_message)
