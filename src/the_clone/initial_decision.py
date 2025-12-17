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
            # Load config for schema
            from the_clone.config_loader import load_config
            config = load_config()
            tier_names = list(config.get('model_tiers', {}).keys())
            context_names = list(config.get('contexts', {}).keys())

            schema_obj = get_initial_decision_schema(tier_names, context_names)

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
            confidence = data.get('confidence', 'low')
            answer_raw = data.get('answer', '')
            search_context = data.get('search_context', 'medium')
            synthesis_tier = data.get('synthesis_model_tier', 'strong')
            search_terms = data.get('search_terms', [])
            reasoning = data.get('reasoning', '')

            # Parse answer - if it's "Searching before answering", convert to empty dict
            if answer_raw == "Searching before answering":
                answer = {}
            elif isinstance(answer_raw, str) and answer_raw:
                # Try to parse as JSON
                try:
                    answer = json.loads(answer_raw)
                except:
                    answer = {"text": answer_raw}
            else:
                answer = answer_raw if isinstance(answer_raw, dict) else {}

            # Save response
            if debug_dir:
                try:
                    with open(os.path.join(debug_dir, '01_initial_decision_response.json'), 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                except:
                    pass

            logger.info(f"[INITIAL] Decision: {decision}, Confidence: {confidence}")

            if decision == "answer_directly":
                logger.info(f"[INITIAL] Answering from model knowledge")
            else:
                logger.info(f"[INITIAL] Need search - Context: {search_context}, Model tier: {synthesis_tier}")
                logger.info(f"[INITIAL] Generated {len(search_terms)} search terms")

            return {
                "decision": decision,
                "confidence": confidence,
                "answer": answer,
                "search_context": search_context,
                "synthesis_model_tier": synthesis_tier,
                "search_terms": search_terms,
                "reasoning": reasoning,
                "model_response": response
            }

        except Exception as e:
            logger.error(f"[INITIAL] Decision failed: {e}")
            # Default to search on error
            return {
                "decision": "need_search",
                "confidence": "low",
                "answer": {},
                "search_terms": [query],  # Fallback to query itself
                "reasoning": f"Error occurred: {e}",
                "error": str(e)
            }

    def _build_prompt(self, query: str) -> str:
        """Build initial decision prompt from template."""
        from the_clone.config_loader import load_config

        config = load_config()
        model_tiers = config.get('model_tiers', {})
        contexts = config.get('contexts', {})

        # Build tier list dynamically
        tier_names = list(model_tiers.keys())
        tier_list = ', '.join(tier_names)

        # Build context descriptions dynamically
        context_descriptions = []
        for ctx_name, ctx_config in sorted(contexts.items()):
            search_range = ctx_config.get('search_terms_range', [1, 3])
            results = ctx_config.get('max_results_per_search', 10)
            sources_range = ctx_config.get('sources_per_search_range', [1, 3])
            desc = ctx_config.get('description', '')

            context_descriptions.append(
                f"**{ctx_name.upper()} Context ({search_range[0]}-{search_range[1]} searches, "
                f"{results} results each, select {sources_range[0]}-{sources_range[1]}/search):**\n"
                f"- {desc}"
            )

        context_guidance = '\n\n'.join(context_descriptions)

        # Build tier descriptions dynamically
        tier_guidance = f"**Available tiers:** {tier_list}\n\nUse 'strong' as default for most queries."

        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__),
            'prompts',
            'initial_decision.md'
        )

        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # Fill template
        prompt = template.format(
            query=query,
            context_guidance=context_guidance,
            tier_guidance=tier_guidance
        )

        return prompt
