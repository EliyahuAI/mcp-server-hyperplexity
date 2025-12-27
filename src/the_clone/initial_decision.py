#!/usr/bin/env python3
"""
Initial Decision Layer for Clone 2.
First call using Sonnet 4.5: Answer directly OR Search.
"""

import sys
import os
import json
import logging
from typing import Dict, Any

# Add parent directories
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.ai_api_client import AIAPIClient
from shared.ai_client.utils import extract_structured_response
from the_clone.initial_decision_schemas import get_initial_decision_schema
from the_clone.strategy_loader import get_model_with_backups

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class InitialDecision:
    """
    Smart routing: Answer from knowledge OR Search.
    Uses Sonnet 4.5 for high-quality decisions.
    """

    def __init__(self, ai_client: AIAPIClient = None):
        """Initialize initial decision layer."""
        self.ai_client = ai_client or AIAPIClient()

    async def make_decision(
        self,
        query: str,
        model: str = "claude-sonnet-4-5",
        soft_schema: bool = False,
        debug_dir: str = None,
        custom_schema: Dict = None,
        clone_logger: Any = None,
        log_prompt_collapsed: bool = False
    ) -> Dict[str, Any]:
        """
        Decide: Answer directly or Search? If search, determine context and model tier.

        Args:
            query: User's query
            model: Model to use (default: Sonnet 4.5)

        Returns:
            Dict with:
                - decision: "answer_directly" or "need_search"
                - answer: dict (if answer_directly)
                - search_context: low/medium/high (if need_search)
                - synthesis_model_tier: fast/strong/deep_thinking (if need_search)
                - search_terms: list (if need_search)
                - confidence: high/medium/low
                - reasoning: explanation
        """
        logger.info(f"[INITIAL] Making decision: Answer directly or Search?")

        prompt = self._build_prompt(query)

        if clone_logger:
            clone_logger.log_section("Initial Decision Prompt", prompt, level=3, collapse=log_prompt_collapsed)

        # Save debug info
        if debug_dir:
            try:
                with open(os.path.join(debug_dir, '01_initial_decision_prompt.md'), 'w', encoding='utf-8') as f:
                    f.write(prompt)
            except:
                pass

        try:
            schema_obj = get_initial_decision_schema(answer_schema=custom_schema)

            # Save schema
            if debug_dir:
                with open(os.path.join(debug_dir, '01_initial_decision_schema.json'), 'w', encoding='utf-8') as f:
                    json.dump(schema_obj, f, indent=2)

            # Get model with backups to override ai_client defaults
            model_chain = get_model_with_backups(model)

            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema_obj,
                model=model_chain,
                use_cache=False,
                max_web_searches=0,
                context="initial_decision",
                soft_schema=soft_schema
            )

            # Log model attempts if backups were used
            if clone_logger and response.get('attempted_models'):
                clone_logger.log_model_attempts(response['attempted_models'], "Initial Decision")

            # Extract decision using centralized parsing
            actual_response = response.get('response', response)
            data = extract_structured_response(actual_response)

            if clone_logger:
                clone_logger.log_section("Initial Decision Response", data, level=3, collapse=True)

            decision = data.get('decision', 'need_search')
            breadth = data.get('breadth', 'narrow')
            depth = data.get('depth', 'shallow')
            search_terms = data.get('search_terms', [])
            synthesis_tier = data.get('synthesis_tier', 'default')

            # Extract answer if answering directly (ignore null/empty from routing responses)
            direct_answer = None
            if decision == "answer_directly":
                # Extract custom schema fields
                if custom_schema:
                    direct_answer = {}
                    for prop_name in custom_schema.get('properties', {}).keys():
                        if prop_name in data:
                            value = data[prop_name]
                            # Filter out explicit null markers (None, null, empty arrays/objects/strings)
                            if value and value not in [None, 'null', '', [], {}]:
                                direct_answer[prop_name] = value

            # Save response
            if debug_dir:
                try:
                    with open(os.path.join(debug_dir, '01_initial_decision_response.json'), 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                except:
                    pass

            logger.info(f"[INITIAL] Decision: {decision}")

            # Extract keywords
            positive_keywords = data.get('positive_keywords', [])
            negative_keywords = data.get('negative_keywords', [])

            if decision == "answer_directly":
                logger.info(f"[INITIAL] Answering from model knowledge")
            else:
                logger.info(f"[INITIAL] Need search - Breadth: {breadth}, Depth: {depth}")
                logger.info(f"[INITIAL] Generated {len(search_terms)} search terms")
                logger.info(f"[INITIAL] Keywords: {len(positive_keywords)} positive, {len(negative_keywords)} negative")
                if positive_keywords:
                    logger.info(f"[INITIAL] Positive keywords: {positive_keywords}")
                if negative_keywords:
                    logger.info(f"[INITIAL] Negative keywords: {negative_keywords}")

            return {
                "decision": decision,
                "breadth": breadth,
                "depth": depth,
                "search_terms": search_terms,
                "positive_keywords": positive_keywords,
                "negative_keywords": negative_keywords,
                "synthesis_tier": synthesis_tier,
                "direct_answer": direct_answer,  # Include direct answer if provided
                "model_response": response
            }

        except Exception as e:
            logger.error(f"[INITIAL] Decision failed: {e}")
            # Default to search on error
            return {
                "decision": "need_search",
                "breadth": "narrow",
                "depth": "shallow",
                "search_terms": [query],  # Fallback to query itself
                "synthesis_tier": "default",
                "error": str(e)
            }

    def _build_prompt(self, query: str) -> str:
        """Build initial decision prompt from template."""
        template_path = os.path.join(
            os.path.dirname(__file__),
            'prompts',
            'initial_decision.md'
        )

        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        return template.format(query=query)
