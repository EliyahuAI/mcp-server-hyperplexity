#!/usr/bin/env python3
"""
Rumor Generator for table_maker row discovery.

Generates candidate rows using multiple AI models in parallel to discover
plausible entities that might exist beyond obvious web search results.
"""

import asyncio
import json
import logging
import re
import hashlib
from typing import Dict, Any, List, Optional
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class RumorGenerator:
    """Generate candidate rows using multiple AI models in parallel."""

    def __init__(self, ai_client, prompt_loader, schema_validator):
        """
        Initialize rumor generator.

        Args:
            ai_client: AI client for making structured API calls
            prompt_loader: Prompt loader for loading templates
            schema_validator: Schema validator for structured outputs
        """
        self.ai_client = ai_client
        self.prompt_loader = prompt_loader
        self.schema_validator = schema_validator

    async def generate_candidates(
        self,
        search_strategy: Dict[str, Any],
        columns: List[Dict[str, Any]],
        target_candidate_count: int = 30,
        models: Optional[List[str]] = None,
        per_model_count: int = 10,
        realness_threshold: float = 0.6
    ) -> Dict[str, Any]:
        """
        Generate candidate rows using multiple AI models in parallel.

        Args:
            search_strategy: Search strategy from column_definition (description, requirements, etc.)
            columns: Column definitions (ID columns only - importance='ID')
            target_candidate_count: Target number of candidates to generate
            models: List of model names to use (default: haiku, gemini, deepseek)
            per_model_count: Number of candidates per model
            realness_threshold: Minimum realness score to include candidate

        Returns:
            {
                "candidates": [
                    {
                        "id_values": {"Company Name": "Anthropic", "Website": "anthropic.com"},
                        "realness_score": 0.95,
                        "source_models": ["haiku", "gemini"],
                        "match_score": 0.95  # Mapped from realness_score for consolidation
                    }
                ],
                "candidates_markdown": "| Company Name | Website | Realness Score | ...",
                "stats": {
                    "total_generated": 30,
                    "post_dedup_count": 25,
                    "models_used": ["haiku", "gemini", "deepseek"],
                    "generation_time_seconds": 2.5
                }
            }
        """
        import time
        start_time = time.time()

        # Default model (Opus for broad entity knowledge)
        if models is None:
            models = ["claude-opus-4-6"]

        logger.info(f"[RUMOR] Starting rumor generation with {len(models)} models, {per_model_count} candidates each")

        # Extract ID columns only
        id_columns = [col for col in columns if col.get('importance', '').upper() == 'ID']
        if not id_columns:
            logger.warning("[RUMOR] No ID columns found, using all columns")
            id_columns = columns

        # Execute parallel generation across models
        all_candidates = []
        generation_tasks = []

        for model in models:
            task = self._generate_with_model(
                model=model,
                search_strategy=search_strategy,
                id_columns=id_columns,
                target_count=per_model_count
            )
            generation_tasks.append(task)

        # Wait for all models to complete
        model_results = await asyncio.gather(*generation_tasks, return_exceptions=True)

        # Process results from each model
        for i, result in enumerate(model_results):
            model_name = models[i]

            if isinstance(result, Exception):
                logger.error(f"[RUMOR] Model {model_name} failed: {result}")
                continue

            if result and isinstance(result, dict):
                candidates = result.get('candidates', [])
                logger.info(f"[RUMOR] Model {model_name} generated {len(candidates)} candidates")

                # Tag candidates with source model
                for candidate in candidates:
                    candidate['source_models'] = [model_name]

                all_candidates.extend(candidates)

        # Deduplicate candidates (merge duplicates from different models)
        deduplicated = self._deduplicate_candidates(all_candidates, id_columns)
        logger.info(f"[RUMOR] Deduplication: {len(all_candidates)} → {len(deduplicated)} candidates")

        # Filter by realness threshold
        filtered = [c for c in deduplicated if c.get('realness_score', 0) >= realness_threshold]
        logger.info(f"[RUMOR] Filtered by realness ≥ {realness_threshold}: {len(deduplicated)} → {len(filtered)} candidates")

        # Map realness_score to match_score for consolidation compatibility
        for candidate in filtered:
            candidate['match_score'] = candidate.get('realness_score', 0.7)

        # Format as markdown table
        markdown_table = self._format_markdown_table(filtered, id_columns)

        generation_time = time.time() - start_time

        return {
            'candidates': filtered,
            'candidates_markdown': markdown_table,
            'stats': {
                'total_generated': len(all_candidates),
                'post_dedup_count': len(deduplicated),
                'post_filter_count': len(filtered),
                'models_used': models,
                'generation_time_seconds': round(generation_time, 2)
            }
        }

    async def _generate_with_model(
        self,
        model: str,
        search_strategy: Dict[str, Any],
        id_columns: List[Dict[str, Any]],
        target_count: int
    ) -> Dict[str, Any]:
        """
        Generate candidates using a single AI model.

        Args:
            model: Model name (e.g., "claude-haiku-4-5")
            search_strategy: Search strategy with description, requirements
            id_columns: ID column definitions
            target_count: Number of candidates to generate

        Returns:
            {
                "candidates": [
                    {
                        "id_values": {"Company Name": "Anthropic"},
                        "realness_score": 0.95
                    }
                ]
            }
        """
        # Load prompt template
        prompt_template = self.prompt_loader.load_prompt('rumor_generation')

        # Build ID columns list for prompt
        id_column_names = [col.get('name', '') for col in id_columns]
        id_columns_str = '\n'.join([f"- **{name}**" for name in id_column_names])

        # Build search strategy description
        strategy_desc = search_strategy.get('description', 'No description provided')

        # Add requirements if present
        requirements = search_strategy.get('requirements', [])
        if requirements:
            strategy_desc += "\n\n**Requirements:**\n"
            for req in requirements:
                req_type = req.get('type', 'unknown')
                req_text = req.get('requirement', '')
                strategy_desc += f"- [{req_type.upper()}] {req_text}\n"

        # Build examples section if subdomains available
        examples_section = ""
        subdomains = search_strategy.get('subdomains', [])
        if subdomains:
            examples_section = "\n## Example Subcategories\n\n"
            examples_section += "Consider entities from these subcategories:\n"
            for subdomain in subdomains[:5]:  # Limit to 5 examples
                examples_section += f"- {subdomain.get('subdomain', '')}: {subdomain.get('description', '')}\n"

        # Fill prompt template
        filled_prompt = prompt_template.replace('{{SEARCH_STRATEGY}}', strategy_desc)
        filled_prompt = filled_prompt.replace('{{ID_COLUMNS}}', id_columns_str)
        filled_prompt = filled_prompt.replace('{{TARGET_COUNT}}', str(target_count))
        filled_prompt = filled_prompt.replace('{{EXAMPLES_SECTION}}', examples_section)

        # Load schema
        schema = self.schema_validator.load_schema('rumor_candidate')

        # Call AI model with structured output
        try:
            response = await self.ai_client.call_structured_api(
                prompt=filled_prompt,
                schema=schema,
                model=model,
                context="rumor_generation"
            )

            if not response or 'structured_output' not in response:
                logger.warning(f"[RUMOR] Model {model} returned no structured output")
                return {'candidates': []}

            structured_output = response['structured_output']
            candidates_markdown = structured_output.get('candidates_markdown', '')

            # Parse markdown table to extract candidates
            candidates = self._parse_markdown_to_rows(candidates_markdown, id_column_names)

            logger.info(f"[RUMOR] Model {model} parsed {len(candidates)} candidates from markdown")

            return {'candidates': candidates}

        except Exception as e:
            logger.error(f"[RUMOR] Error generating with model {model}: {e}")
            return {'candidates': []}

    def _parse_markdown_to_rows(
        self,
        markdown_str: str,
        id_column_names: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Parse markdown table to extract id_values + realness_score.

        Expected format:
        | Company Name | Website | Realness Score |
        |--------------|---------|----------------|
        | Anthropic | anthropic.com | 0.95 |

        Args:
            markdown_str: Markdown table string
            id_column_names: Expected ID column names

        Returns:
            List of candidates with id_values and realness_score
        """
        if not markdown_str or not isinstance(markdown_str, str):
            return []

        candidates = []
        lines = markdown_str.strip().split('\n')

        # Find header line
        header_line = None
        header_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('|') and '---' not in line:
                header_line = line
                header_idx = i
                break

        if not header_line:
            logger.warning("[RUMOR] No header line found in markdown")
            return []

        # Parse headers
        headers = [h.strip() for h in header_line.split('|') if h.strip()]

        # Find Realness Score column index
        realness_idx = None
        for i, h in enumerate(headers):
            if h.lower() in ['realness score', 'realness', 'score']:
                realness_idx = i
                break

        # Parse data rows
        for line in lines[header_idx + 1:]:
            stripped = line.strip()
            if not stripped or not stripped.startswith('|'):
                continue

            # Skip separator lines
            cleaned = re.sub(r'[\|\-\:\s]', '', stripped)
            if len(cleaned) == 0 and '---' in stripped:
                continue

            # Parse row values
            raw_parts = stripped.split('|')
            values = [v.strip() for v in raw_parts[1:-1]]

            if len(values) < len(headers):
                logger.warning(f"[RUMOR] Row has fewer values than headers: {len(values)} < {len(headers)}")
                continue

            # Extract ID values
            id_values = {}
            realness_score = 0.7  # Default

            for col_idx, header in enumerate(headers):
                if col_idx >= len(values):
                    continue

                cell_value = values[col_idx]

                # Check if this is the Realness Score column
                if col_idx == realness_idx:
                    try:
                        realness_score = float(cell_value)
                    except ValueError:
                        logger.warning(f"[RUMOR] Invalid realness score: {cell_value}")
                        realness_score = 0.7
                    continue

                # Check if this is an ID column (case-insensitive match)
                matched = False
                for id_col_name in id_column_names:
                    if header.lower() == id_col_name.lower():
                        id_values[id_col_name] = cell_value
                        matched = True
                        break

                if not matched:
                    # If not found in expected ID columns, still include it
                    id_values[header] = cell_value

            # Only add if we have at least one ID value
            if id_values:
                candidates.append({
                    'id_values': id_values,
                    'realness_score': realness_score
                })

        return candidates

    def _deduplicate_candidates(
        self,
        candidates: List[Dict[str, Any]],
        id_columns: List[Dict[str, Any]],
        similarity_threshold: float = 0.85
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate candidates using fuzzy matching on ID columns.

        Reuses RowConsolidator logic:
        - Fuzzy match on ID column values
        - Merge source_models from duplicates
        - Keep highest realness_score

        Args:
            candidates: List of candidates to deduplicate
            id_columns: ID column definitions
            similarity_threshold: Fuzzy matching threshold (default 0.85)

        Returns:
            Deduplicated list of candidates
        """
        if not candidates:
            return []

        # Track unique candidates by composite key
        unique_candidates = []
        id_column_names = [col.get('name', '') for col in id_columns]

        for candidate in candidates:
            id_values = candidate.get('id_values', {})

            # Create composite key for fuzzy matching
            composite_key = ' '.join([
                str(id_values.get(col_name, '')).lower().strip()
                for col_name in id_column_names
                if id_values.get(col_name)
            ])

            if not composite_key:
                continue

            # Check if similar candidate already exists
            found_match = False
            for existing in unique_candidates:
                existing_id_values = existing.get('id_values', {})
                existing_composite_key = ' '.join([
                    str(existing_id_values.get(col_name, '')).lower().strip()
                    for col_name in id_column_names
                    if existing_id_values.get(col_name)
                ])

                # Fuzzy match using SequenceMatcher
                similarity = SequenceMatcher(None, composite_key, existing_composite_key).ratio()

                if similarity >= similarity_threshold:
                    # Found duplicate - merge source_models and keep higher realness_score
                    existing_models = set(existing.get('source_models', []))
                    candidate_models = set(candidate.get('source_models', []))
                    existing['source_models'] = list(existing_models | candidate_models)

                    # Keep higher realness_score
                    if candidate.get('realness_score', 0) > existing.get('realness_score', 0):
                        existing['realness_score'] = candidate.get('realness_score', 0)

                    found_match = True
                    break

            if not found_match:
                unique_candidates.append(candidate)

        return unique_candidates

    def _format_markdown_table(
        self,
        candidates: List[Dict[str, Any]],
        id_columns: List[Dict[str, Any]]
    ) -> str:
        """
        Format candidates as markdown table.

        Args:
            candidates: List of candidates
            id_columns: ID column definitions

        Returns:
            Markdown table string
        """
        if not candidates:
            return ""

        id_column_names = [col.get('name', '') for col in id_columns]

        # Build header
        headers = id_column_names + ['Realness Score', 'Source Models']
        header_line = '| ' + ' | '.join(headers) + ' |'
        separator_line = '|' + '|'.join(['---' for _ in headers]) + '|'

        # Build data rows
        rows = []
        for candidate in candidates:
            id_values = candidate.get('id_values', {})
            realness = candidate.get('realness_score', 0.7)
            models = ', '.join(candidate.get('source_models', []))

            row_values = []
            for col_name in id_column_names:
                row_values.append(str(id_values.get(col_name, '')))

            row_values.append(f"{realness:.2f}")
            row_values.append(models)

            row_line = '| ' + ' | '.join(row_values) + ' |'
            rows.append(row_line)

        # Combine all lines
        markdown_lines = [header_line, separator_line] + rows
        return '\n'.join(markdown_lines)
