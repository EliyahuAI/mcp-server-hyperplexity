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
        realness_threshold: float = 0.6,  # kept for backward compat, no longer used for filtering
        existing_rows: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Generate candidate rows using multiple AI models in parallel.

        Returns:
            {
                "keep_candidates": [...],     # K-disposition rows — include directly
                "validate_candidates": [...], # V-disposition rows — need validation
                "candidates_markdown": "...",
                "stats": {
                    "total_generated": 30,
                    "post_dedup_count": 25,
                    "keep_count": 10,
                    "validate_count": 12,
                    "reject_count": 3,
                    "models_used": [...],
                    "generation_time_seconds": 2.5
                }
            }
        """
        import time
        start_time = time.time()

        # Resolve default model via ModelConfig
        if models is None:
            try:
                from model_config_loader import ModelConfig
                model_name = ModelConfig.get('rumor_generation')
                if not model_name:
                    raise ValueError("Empty model name")
                models = [model_name]
                logger.info(f"[RUMOR] Using model from ModelConfig: {model_name}")
            except Exception as e:
                logger.warning(f"[RUMOR] ModelConfig unavailable ({e}), falling back to claude-opus-4-6")
                models = ["claude-opus-4-6"]

        logger.info(f"[RUMOR] Starting rumor generation with {len(models)} models, {per_model_count} candidates each")

        # Extract ID columns only
        id_columns = [col for col in columns if col.get('importance', '').upper() == 'ID']
        if not id_columns:
            logger.warning("[RUMOR] No ID columns found, using all columns")
            id_columns = columns

        # Extract hard requirements for column generation
        requirements = search_strategy.get('requirements', [])
        hard_requirements = [r for r in requirements if r.get('type', '').lower() == 'hard']

        # Execute parallel generation across models
        all_candidates = []
        generation_tasks = []

        for model in models:
            task = self._generate_with_model(
                model=model,
                search_strategy=search_strategy,
                id_columns=id_columns,
                target_count=per_model_count,
                existing_rows=existing_rows or [],
                hard_requirements=hard_requirements
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

        # Split by disposition: K / V / R
        keep_candidates = []
        validate_candidates = []
        reject_count = 0

        for candidate in deduplicated:
            disposition = candidate.get('disposition', 'V').upper()
            # Map realness_score → match_score for consolidation compatibility
            candidate['match_score'] = candidate.get('realness_score', 0.7)

            if disposition == 'K':
                keep_candidates.append(candidate)
            elif disposition == 'R':
                reject_count += 1
            else:
                # V or anything else → validate
                validate_candidates.append(candidate)

        logger.info(
            f"[RUMOR] Disposition split: K={len(keep_candidates)}, "
            f"V={len(validate_candidates)}, R={reject_count}"
        )

        # Format as markdown table (all non-rejected)
        all_non_rejected = keep_candidates + validate_candidates
        markdown_table = self._format_markdown_table(all_non_rejected, id_columns, hard_requirements)

        generation_time = time.time() - start_time

        return {
            'keep_candidates': keep_candidates,
            'validate_candidates': validate_candidates,
            # Legacy key for backward compat
            'candidates': all_non_rejected,
            'candidates_markdown': markdown_table,
            'stats': {
                'total_generated': len(all_candidates),
                'post_dedup_count': len(deduplicated),
                'keep_count': len(keep_candidates),
                'validate_count': len(validate_candidates),
                'reject_count': reject_count,
                'models_used': models,
                'generation_time_seconds': round(generation_time, 2)
            }
        }

    async def _generate_with_model(
        self,
        model: str,
        search_strategy: Dict[str, Any],
        id_columns: List[Dict[str, Any]],
        target_count: int,
        existing_rows: Optional[List[Dict]] = None,
        hard_requirements: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Generate candidates using a single AI model."""
        if hard_requirements is None:
            hard_requirements = []

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

        # Build existing rows exclusion section
        existing_rows_section = ""
        if existing_rows:
            id_col_names = [col.get('name', '') for col in id_columns]
            existing_values = []
            for row in existing_rows:
                id_vals = row.get('id_values', {})
                label = ', '.join(str(id_vals.get(c, '')) for c in id_col_names if id_vals.get(c))
                if label:
                    existing_values.append(f"- {label}")
            if existing_values:
                existing_rows_section = (
                    "\n## Already Found — Do Not Repeat\n\n"
                    "The following entities have already been identified. Do not include them or close variants:\n\n"
                    + '\n'.join(existing_values[:50])  # cap at 50 to avoid prompt bloat
                )

        # Build output format example with real column names
        # Columns: ID cols + Disposition + one [HARD] col per hard requirement
        hard_col_names = [f"[HARD] {r.get('requirement', '')[:40]}" for r in hard_requirements]
        col_headers = id_column_names + ['Disposition'] + hard_col_names
        header_row = '| ' + ' | '.join(col_headers) + ' |'
        sep_row = '| ' + ' | '.join('-' * max(len(c), 3) for c in col_headers) + ' |'
        # Example data row
        example_values = ['...' for _ in id_column_names] + ['V'] + ['?' for _ in hard_col_names]
        example_row = '| ' + ' | '.join(example_values) + ' |'
        output_format_example = '\n'.join([header_row, sep_row, example_row])

        # Fill prompt template
        filled_prompt = prompt_template.replace('{{SEARCH_STRATEGY}}', strategy_desc)
        filled_prompt = filled_prompt.replace('{{ID_COLUMNS}}', id_columns_str)
        filled_prompt = filled_prompt.replace('{{TARGET_COUNT}}', str(target_count))
        filled_prompt = filled_prompt.replace('{{EXAMPLES_SECTION}}', examples_section)
        filled_prompt = filled_prompt.replace('{{EXISTING_ROWS_SECTION}}', existing_rows_section)
        filled_prompt = filled_prompt.replace('{{OUTPUT_FORMAT_EXAMPLE}}', output_format_example)

        # Load schema
        schema = self.schema_validator.load_schema('rumor_candidate')

        # Call AI model with structured output
        try:
            response = await self.ai_client.call_structured_api(
                prompt=filled_prompt,
                schema=schema,
                model=model,
                context="rumor_generation",
                max_web_searches=0
            )

            raw_response = response.get('response', {}) if response else {}
            choices = raw_response.get('choices', []) if raw_response else []
            if not choices:
                logger.warning(f"[RUMOR] Model {model} returned no structured output")
                return {'candidates': []}

            content = choices[0]['message']['content']
            structured_output = json.loads(content) if isinstance(content, str) else content
            candidates_markdown = structured_output.get('candidates_markdown', '')

            # Parse markdown table to extract candidates
            candidates = self._parse_markdown_to_rows(
                candidates_markdown, id_column_names, hard_requirements
            )

            logger.info(f"[RUMOR] Model {model} parsed {len(candidates)} candidates from markdown")

            return {'candidates': candidates}

        except Exception as e:
            logger.error(f"[RUMOR] Error generating with model {model}: {e}")
            return {'candidates': []}

    def _parse_markdown_to_rows(
        self,
        markdown_str: str,
        id_column_names: List[str],
        hard_requirements: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Parse markdown table to extract id_values + disposition + hard_req_prereqs.

        Expected format:
        | Company Name | Website | Disposition | [HARD] Revenue > $10M |
        |---|---|---|---|
        | Anthropic | anthropic.com | K | T |
        """
        if not markdown_str or not isinstance(markdown_str, str):
            return []

        if hard_requirements is None:
            hard_requirements = []

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

        # Find disposition column index
        disposition_idx = None
        for i, h in enumerate(headers):
            if h.lower() == 'disposition':
                disposition_idx = i
                break

        # Find [HARD] column indices
        hard_col_indices = {}  # header_text → column_index
        for i, h in enumerate(headers):
            if h.startswith('[HARD]') or h.startswith('[hard]'):
                hard_col_indices[h] = i

        # Also support legacy "Confidence Score" / "Realness Score" for backward compat
        legacy_score_idx = None
        if disposition_idx is None:
            for i, h in enumerate(headers):
                if h.lower() in ['realness score', 'realness', 'confidence score', 'confidence', 'score']:
                    legacy_score_idx = i
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
            disposition = 'V'  # Default
            realness_score = 0.7  # Default (used for legacy compat)
            hard_req_prereqs = {}  # {req_text: T/F/?}

            for col_idx, header in enumerate(headers):
                if col_idx >= len(values):
                    continue

                cell_value = values[col_idx]

                # Disposition column
                if col_idx == disposition_idx:
                    disp = cell_value.strip().upper()
                    if disp in ('K', 'R', 'V'):
                        disposition = disp
                    else:
                        disposition = 'V'  # Invalid → validate
                    continue

                # Legacy score column
                if col_idx == legacy_score_idx:
                    try:
                        score = float(cell_value)
                        realness_score = score
                        # Map legacy score to disposition
                        if score >= 0.85:
                            disposition = 'K'
                        elif score < 0.5:
                            disposition = 'R'
                        else:
                            disposition = 'V'
                    except ValueError:
                        disposition = 'V'
                    continue

                # [HARD] column
                if header in hard_col_indices:
                    val = cell_value.strip().upper()
                    if val not in ('T', 'F', '?'):
                        val = '?'
                    # Extract short requirement text from header
                    req_short = header.replace('[HARD]', '').replace('[hard]', '').strip()
                    hard_req_prereqs[req_short] = val
                    continue

                # ID column (case-insensitive match)
                matched = False
                for id_col_name in id_column_names:
                    if header.lower() == id_col_name.lower():
                        id_values[id_col_name] = cell_value
                        matched = True
                        break

                if not matched:
                    # Include unknown columns in id_values anyway
                    id_values[header] = cell_value

            # Only add if we have at least one ID value
            if id_values:
                # If any [HARD] is F, override disposition toward R
                if any(v == 'F' for v in hard_req_prereqs.values()):
                    if disposition == 'K':
                        disposition = 'R'  # K with a failing HARD is a contradiction → reject

                candidates.append({
                    'id_values': id_values,
                    'disposition': disposition,
                    'realness_score': realness_score,
                    'hard_req_prereqs': hard_req_prereqs
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
        - Keep higher disposition priority (K > V > R) and higher realness_score
        """
        if not candidates:
            return []

        _DISPOSITION_PRIORITY = {'K': 2, 'V': 1, 'R': 0}

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

                similarity = SequenceMatcher(None, composite_key, existing_composite_key).ratio()

                if similarity >= similarity_threshold:
                    # Found duplicate — merge source_models
                    existing_models = set(existing.get('source_models', []))
                    candidate_models = set(candidate.get('source_models', []))
                    existing['source_models'] = list(existing_models | candidate_models)

                    # Keep higher disposition (K > V > R)
                    existing_disp = existing.get('disposition', 'V')
                    candidate_disp = candidate.get('disposition', 'V')
                    if _DISPOSITION_PRIORITY.get(candidate_disp, 1) > _DISPOSITION_PRIORITY.get(existing_disp, 1):
                        existing['disposition'] = candidate_disp

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
        id_columns: List[Dict[str, Any]],
        hard_requirements: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Format candidates as markdown table with Disposition + T/F/? columns."""
        if not candidates:
            return ""

        if hard_requirements is None:
            hard_requirements = []

        id_column_names = [col.get('name', '') for col in id_columns]
        hard_col_names = [f"[HARD] {r.get('requirement', '')[:40]}" for r in hard_requirements]

        # Build header
        headers = id_column_names + ['Disposition'] + hard_col_names + ['Source Models']
        header_line = '| ' + ' | '.join(headers) + ' |'
        separator_line = '|' + '|'.join(['---' for _ in headers]) + '|'

        # Build data rows
        rows = []
        for candidate in candidates:
            id_values = candidate.get('id_values', {})
            disposition = candidate.get('disposition', 'V')
            hard_prereqs = candidate.get('hard_req_prereqs', {})
            models = ', '.join(candidate.get('source_models', []))

            row_values = []
            for col_name in id_column_names:
                row_values.append(str(id_values.get(col_name, '')))

            row_values.append(disposition)

            for hard_req in hard_requirements:
                req_short = hard_req.get('requirement', '')[:40]
                row_values.append(hard_prereqs.get(req_short, '?'))

            row_values.append(models)

            row_line = '| ' + ' | '.join(row_values) + ' |'
            rows.append(row_line)

        markdown_lines = [header_line, separator_line] + rows
        return '\n'.join(markdown_lines)
