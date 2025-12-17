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
        debug_dir: str = None
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

        # Save debug info
        if debug_dir:
            try:
                with open(os.path.join(debug_dir, '01_initial_decision_prompt.md'), 'w', encoding='utf-8') as f:
                    f.write(prompt)
            except:
                pass

        try:
            schema_obj = get_initial_decision_schema()

            # Save schema
            if debug_dir:
                with open(os.path.join(debug_dir, '01_initial_decision_schema.json'), 'w', encoding='utf-8') as f:
                    json.dump(schema_obj, f, indent=2)

            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema_obj,
                model=model,
                use_cache=False,
                max_web_searches=0,
                context="initial_decision",
                soft_schema=soft_schema
            )

            # Extract decision using centralized parsing
            actual_response = response.get('response', response)
            data = extract_structured_response(actual_response)

            decision = data.get('decision', 'need_search')
            breadth = data.get('breadth', 'narrow')
            depth = data.get('depth', 'shallow')
            search_terms = data.get('search_terms', [])
            reasoning = data.get('reasoning', '')

            # No answer parsing needed for new schema

            # Save response
            if debug_dir:
                try:
                    with open(os.path.join(debug_dir, '01_initial_decision_response.json'), 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                except:
                    pass

            logger.info(f"[INITIAL] Decision: {decision}")

            if decision == "answer_directly":
                logger.info(f"[INITIAL] Answering from model knowledge")
            else:
                logger.info(f"[INITIAL] Need search - Breadth: {breadth}, Depth: {depth}")
                logger.info(f"[INITIAL] Generated {len(search_terms)} search terms")

            return {
                "decision": decision,
                "breadth": breadth,
                "depth": depth,
                "search_terms": search_terms,
                "reasoning": reasoning,
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
                "reasoning": f"Error occurred: {e}",
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
