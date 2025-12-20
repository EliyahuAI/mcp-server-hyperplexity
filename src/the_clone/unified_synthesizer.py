#!/usr/bin/env python3
"""
Unified Synthesizer for Clone 2.
Combines evaluation and synthesis into single calls using Claude Sonnet 4.5.

Mode 1 (Evaluation): Can we answer? If yes, provides answer immediately
Mode 2 (Synthesis): Generate answer (last iteration, no evaluation)
"""

import sys
import os
import json
import re
import logging
from typing import Dict, Any, List

# Add parent directories
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.ai_api_client import AIAPIClient
from shared.ai_client.utils import extract_structured_response
from the_clone.unified_schemas import get_unified_evaluation_synthesis_schema, get_synthesis_only_schema
from the_clone.config import get_synthesis_guidance
from the_clone.strategy_loader import get_model_with_backups

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UnifiedSynthesizer:
    """
    Unified component that handles both evaluation and synthesis.
    Uses Claude Sonnet 4.5 for better quality decisions.
    """

    def __init__(self, ai_client: AIAPIClient = None):
        """Initialize unified synthesizer."""
        self.ai_client = ai_client or AIAPIClient()

    async def evaluate_and_synthesize(
        self,
        query: str,
        snippets: List[Dict],
        context: str,
        iteration: int,
        is_last_iteration: bool,
        schema: Dict = None,
        model: str = "claude-sonnet-4-5",
        search_terms: List[str] = None,
        debug_dir: str = None,
        soft_schema: bool = False,
        clone_logger: Any = None
    ) -> Dict[str, Any]:
        """
        Unified evaluation + synthesis call.

        Mode 1 (not last iteration): Evaluate if can answer, provide answer if yes
        Mode 2 (last iteration): Just generate answer

        Args:
            query: User's query
            snippets: Accumulated snippets
            context: Context level
            iteration: Current iteration
            is_last_iteration: If true, skip evaluation (just synthesize)
            schema: Optional custom schema
            model: Model to use (default: Sonnet 4.5)

        Returns:
            Dict with:
                - can_answer: bool (only if not last iteration)
                - answer: dict (if can_answer=true or last iteration)
                - missing_aspects: list (if can_answer=false)
                - suggested_search_terms: list (if can_answer=false)
                - citations: list (final citations with snippet ID conversion)
        """
        logger.info(f"[UNIFIED] Mode: {'Synthesis' if is_last_iteration else 'Evaluation+Synthesis'}")

        # Build prompt
        prompt = self._build_prompt(
            query=query,
            snippets=snippets,
            context=context,
            is_last_iteration=is_last_iteration,
            search_terms=search_terms
        )

        if clone_logger:
            clone_logger.log_section(f"Synthesis Prompt (Iter {iteration})", prompt, level=3, collapse=True)

        # Select schema - if custom schema provided, merge it
        if is_last_iteration:
            response_schema = get_synthesis_only_schema(answer_schema=schema)
        else:
            response_schema = get_unified_evaluation_synthesis_schema(answer_schema=schema)

        # Save debug info
        if debug_dir:
            try:
                with open(os.path.join(debug_dir, f'04_synthesis_iter{iteration}_prompt.md'), 'w', encoding='utf-8') as f:
                    f.write(prompt)
                with open(os.path.join(debug_dir, f'04_synthesis_iter{iteration}_schema.json'), 'w', encoding='utf-8') as f:
                    json.dump(response_schema, f, indent=2)
            except:
                pass

        try:
            # Get model with backups to override ai_client defaults
            model_chain = get_model_with_backups(model)

            # Call model
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=response_schema,
                model=model_chain,
                use_cache=False,
                max_web_searches=0,
                context=f"unified_iter{iteration}",
                soft_schema=soft_schema
            )

            # Log model attempts if backups were used
            if clone_logger and response.get('attempted_models'):
                clone_logger.log_model_attempts(response['attempted_models'], f"Synthesis Iteration {iteration}")

            # Extract response using centralized parsing
            actual_response = response.get('response', response)
            data = extract_structured_response(actual_response)

            if clone_logger:
                clone_logger.log_section(f"Synthesis Result (Iter {iteration})", data, level=3, collapse=True)

            # Parse response based on mode
            logger.debug(f"[UNIFIED] data keys: {list(data.keys())}")
            if is_last_iteration:
                # Synthesis mode - just answer
                answer_raw = data
                can_answer = True
                confidence = "high"
                missing = []
                suggested = []
            else:
                # Evaluation mode - may have answer
                can_answer = data.get('can_answer', False)
                confidence = data.get('confidence', 'low')
                answer_raw = data.get('answer_raw', {})  # Extract from answer_raw field
                # If answer is empty object, treat as no answer
                if not answer_raw or answer_raw == {}:
                    answer_raw = {}
                    can_answer = False
                missing = data.get('missing_aspects', [])
                suggested = data.get('suggested_search_terms', [])

            logger.info(f"[UNIFIED] Can answer: {can_answer}, Confidence: {confidence}")
            logger.debug(f"[UNIFIED] answer_raw type: {type(answer_raw)}, content: {str(answer_raw)[:200]}")

            # Save response
            if debug_dir:
                try:
                    with open(os.path.join(debug_dir, f'04_synthesis_iter{iteration}_response.json'), 'w', encoding='utf-8') as f:
                        json.dump({
                            'can_answer': can_answer,
                            'confidence': confidence,
                            'answer_raw': answer_raw,
                            'missing': missing,
                            'suggested': suggested
                        }, f, indent=2)
                except:
                    pass

            # Convert snippet IDs to citations if answer provided
            if can_answer and answer_raw:
                answer_final, citations, snippets_used = self._convert_snippet_ids_to_citations(
                    answer=answer_raw,
                    snippets=snippets
                )

                # Post-process for validation format if custom schema is validation_results
                if schema and self._is_validation_schema(schema):
                    answer_final = self._transform_to_validation_format(answer_final, citations, schema)
            else:
                answer_final = {}
                citations = []
                snippets_used = []

            return {
                "can_answer": can_answer,
                "confidence": confidence,
                "answer": answer_final,
                "citations": citations,
                "snippets_used": snippets_used,
                "missing_aspects": missing,
                "suggested_search_terms": suggested,
                "synthesis_prompt": prompt,  # Return actual prompt sent to model
                "model_response": response
            }

        except Exception as e:
            logger.error(f"[UNIFIED] Error: {e}")
            raise

    def _build_prompt(
        self,
        query: str,
        snippets: List[Dict],
        context: str,
        is_last_iteration: bool,
        search_terms: List[str] = None
    ) -> str:
        """Build unified prompt."""
        from datetime import datetime

        guidance = get_synthesis_guidance(context)
        current_date = datetime.now().strftime('%Y-%m-%d')

        # Format snippets grouped by search term
        formatted_snippets = self._format_snippets_by_search_term(snippets, search_terms)

        if is_last_iteration:
            # Synthesis mode
            prompt = f"""# Generate Answer from Quotes

Query: {query}

**Today's Date:** {current_date}

## Structure Legend

- **Q1.{'{n}'}:** Query number in iteration 1 (search term used)
- **Snippet ID Format:** S{'{iter}'}.{'{search}'}.{'{source}'}.{'{snippet}'}-{'{rel}'}
  - Example: S1.2.3.0-M = Iteration 1, Search 2, Source 3, Snippet 0, MEDIUM reliability
- **Reliability:** H=HIGH (authoritative sources), M=MEDIUM (reliable), L=LOW (less reliable)
- **Date:** Publication or last updated date from source

## Quotes Organized by Search Term

{formatted_snippets}

## Synthesis Instructions

{guidance}

## Your Task

Generate a structured comparison answering the query, then self-assess.

**Citation Format:** Use [S1.2.3.0-H] style snippet IDs to reference quotes.
**Output Structure:** Use nested objects to avoid repetition.

Example structure:
```json
{{
  "comparison": {{
    "claude_opus_4": {{
      "architecture": "... [S1.1.0.0-H]",
      "performance": "... [S1.1.0.1-H]"
    }},
    "gpt_4_5": {{
      "architecture": "... [S1.2.0.0-M]"
    }}
  }},
  "self_assessment": "A"
}}
```

## Self-Assessment

Grade your synthesis (A+ to C-):
- **A+/A**: Handled complexity well OR info not available in sources
- **B**: Struggled with complexity, conflicting sources need deeper reasoning
- **C**: Insufficient capability for this complexity

Return JSON with 'comparison' and 'self_assessment' fields."""

        else:
            # Evaluation + synthesis mode
            prompt = f"""# Evaluate Sufficiency and Provide Answer if Possible

Query: {query}

**Today's Date:** {current_date}

## Structure Legend

- **Q1.{'{n}'}:** Query number in iteration 1 (search term used)
- **Snippet ID Format:** S{'{iter}'}.{'{search}'}.{'{source}'}.{'{snippet}'}-{'{rel}'}
  - Example: S1.2.3.0-M = Iteration 1, Search 2, Source 3, Snippet 0, MEDIUM reliability
- **Reliability:** H=HIGH (authoritative sources), M=MEDIUM (reliable), L=LOW (less reliable)
- **Date:** Publication or last updated date from source

## Quotes Organized by Search Term

{formatted_snippets}

## Synthesis Instructions

{guidance}

## Your Task

1. **Evaluate:** Can we comprehensively answer the query with these quotes?

2. **If YES (can_answer: true):**
   - Set confidence (high/medium/low)
   - Provide complete answer in the 'answer_raw' field as an object

3. **If NO (can_answer: false):**
   - Set response to empty object {{}}
   - List missing_aspects
   - Suggest search_terms to fill gaps

**Citation Format:** Use [S1.2.3.0-H] style snippet IDs.

**Output Structure Example:**
```json
{{
  "can_answer": true,
  "confidence": "high",
  "answer_raw": {{
    "comparison": {{
      "model_a": {{"aspect1": "...", "aspect2": "..."}},
      "model_b": {{"aspect1": "...", "aspect2": "..."}}
    }}
  }}
}}
```"""

        return prompt

    def _format_snippets_by_search_term(self, snippets: List[Dict], search_terms: List[str] = None) -> str:
        """
        Format snippets in nested structure:
        Q1.1: "search query"
          URL [RELIABILITY, DATE]
            - [S1.1.0.0] "snippet"
        """
        if not snippets:
            return "(No quotes)"

        # Group by search_ref
        by_search = {}
        search_queries = {}  # Map search_ref to query text

        for snippet in snippets:
            search_ref = snippet.get('search_ref', 1)
            if search_ref not in by_search:
                by_search[search_ref] = []
                # Get search query from provided search_terms array (index is search_ref - 1)
                if search_terms and len(search_terms) >= search_ref:
                    search_queries[search_ref] = search_terms[search_ref - 1]
                else:
                    search_queries[search_ref] = snippet.get('_search_term', f'Search {search_ref}')
            by_search[search_ref].append(snippet)

        # Format
        formatted = []
        for search_num in sorted(by_search.keys()):
            # Query header: Q1.1: "query text"
            query_text = search_queries.get(search_num, f'Search {search_num}')
            formatted.append(f"\nQ1.{search_num}: \"{query_text}\"")

            # Group by source URL within search
            by_url = {}
            for snippet in by_search[search_num]:
                url = snippet.get('_source_url', 'Unknown URL')

                if url not in by_url:
                    by_url[url] = {
                        'url': url,
                        'date': snippet.get('_source_date', ''),
                        'snippets': []
                    }

                by_url[url]['snippets'].append({
                    'id': snippet.get('id', ''),
                    'text': snippet.get('text', ''),
                    'p': snippet.get('p', 0.50),
                    'reason': snippet.get('validation_reason', 'OK')
                })

            # Format sources under this query
            for url, data in by_url.items():
                # Get source ID prefix from first snippet (e.g., S1.1.0 from S1.1.0.0-M)
                first_snippet_id = data['snippets'][0]['id'] if data['snippets'] else ''
                source_prefix = '.'.join(first_snippet_id.split('.')[:3]) if first_snippet_id else ''

                # Source header: [S1.1.0] URL [DATE]
                source_line = f"  [{source_prefix}] {data['url']}" if source_prefix else f"  {data['url']}"
                if data['date']:
                    source_line += f" [{data['date']}]"
                formatted.append(source_line)

                # Snippets under this source (p-score already in ID)
                for snip in data['snippets']:
                    reason = snip.get('reason', 'OK')

                    # Show reason for non-OK snippets (attribution is in quote text)
                    if reason != 'OK':
                        formatted.append(f"    - [{snip['id']}] ({reason}) \"{snip['text']}\"")
                    else:
                        formatted.append(f"    - [{snip['id']}] \"{snip['text']}\"")

        return '\n'.join(formatted)

    def _convert_snippet_ids_to_citations(
        self,
        answer: Dict[str, Any],
        snippets: List[Dict]
    ) -> tuple:
        """Convert snippet IDs to citation numbers."""
        answer_str = json.dumps(answer)

        # Find all snippet ID patterns - both old (-H/-M/-L) and new (-pX.XX) formats
        # Pattern 1: New format like [S1.1.0.0-p0.85]
        # Pattern 2: Old format like [S1.1.4.2-M] (backward compatibility)
        # Pattern 3: Lists like [S1.1.0-p0.95, S1.2.0-p0.85]
        new_individual_pattern = r'\[S\d+(?:\.\d+)*-p\d+\.\d+\]'
        old_individual_pattern = r'\[S\d+(?:\.\d+)*-[HML]\]'
        new_list_pattern = r'\[S\d+(?:\.\d+)*-p\d+\.\d+(?:,\s*S\d+(?:\.\d+)*-p\d+\.\d+)+\]'
        old_list_pattern = r'\[S\d+(?:\.\d+)*-[HML](?:,\s*S\d+(?:\.\d+)*-[HML])+\]'

        # Find all matches (new format first, then old for backward compatibility)
        individual_matches = re.findall(new_individual_pattern, answer_str) + re.findall(old_individual_pattern, answer_str)
        list_matches = re.findall(new_list_pattern, answer_str) + re.findall(old_list_pattern, answer_str)

        # Extract all unique snippet IDs
        snippet_ids = []
        seen = set()

        # From individual matches
        for match in individual_matches:
            sid = match[1:-1]  # Remove brackets
            if sid not in seen:
                snippet_ids.append(sid)
                seen.add(sid)

        # From list matches
        for match in list_matches:
            # Extract IDs from comma-separated list (both formats)
            ids_in_match = re.findall(r'S\d+(?:\.\d+)*-(?:p\d+\.\d+|[HML])', match)
            for sid in ids_in_match:
                if sid not in seen:
                    snippet_ids.append(sid)
                    seen.add(sid)

        # Build snippet map
        snippet_map = {s.get('id'): s for s in snippets}

        # Build citations (deduplicate by URL, aggregate all snippets per URL)
        citations = []
        snippet_to_citation = {}
        url_to_citation_idx = {}  # Map URL to citation index
        url_to_snippets = {}  # Collect all snippets per URL

        # First pass: group snippets by URL
        for snippet_id in snippet_ids:
            snippet = snippet_map.get(snippet_id)
            if not snippet:
                continue

            source_url = snippet.get('_source_url', '')
            if source_url not in url_to_snippets:
                url_to_snippets[source_url] = []
            url_to_snippets[source_url].append(snippet)
            snippet_to_citation[snippet_id] = None  # Will be set in second pass

        # Second pass: create citations with all snippets per URL
        for source_url, url_snippets in url_to_snippets.items():
            citation_index = len(citations) + 1
            url_to_citation_idx[source_url] = citation_index

            # Get metadata from first snippet
            first_snippet = url_snippets[0]

            # Aggregate all unique snippet texts
            snippet_texts = []
            seen_texts = set()
            for snip in url_snippets:
                text = snip.get('text', '')
                if text and text not in seen_texts:
                    snippet_texts.append(text)
                    seen_texts.add(text)

            # Combine all snippets into single cited_text (Sonar-compatible, newline-joined)
            cited_text = '\n'.join(snippet_texts) if snippet_texts else ''

            # Sonar-compatible format with additional Clone-specific fields
            citations.append({
                'url': source_url,
                'title': first_snippet.get('_source_title', 'Unknown'),
                'cited_text': cited_text,
                'date': first_snippet.get('_source_date', ''),
                'last_updated': first_snippet.get('_source_date', ''),
                'index': citation_index,
                'reliability': first_snippet.get('_source_reliability', 'MEDIUM'),
                'snippets': snippet_texts
            })

        # Map snippet IDs to citation indices
        for snippet_id in snippet_ids:
            snippet = snippet_map.get(snippet_id)
            if snippet:
                source_url = snippet.get('_source_url', '')
                snippet_to_citation[snippet_id] = url_to_citation_idx.get(source_url)

        # Replace individual IDs first
        for snippet_id, citation_idx in snippet_to_citation.items():
            answer_str = answer_str.replace(f'[{snippet_id}]', f'[{citation_idx}]')

        # Replace comma-separated lists with consecutive bracket notation
        # e.g., [S1.1.0-p0.95, S1.2.0-p0.85] -> [1][2]
        def replace_list(match):
            # Match both new and old format IDs
            ids_in_match = re.findall(r'S\d+(?:\.\d+)*-(?:p\d+\.\d+|[HML])', match.group(0))
            citation_nums = []
            for sid in ids_in_match:
                if sid in snippet_to_citation:
                    citation_nums.append(str(snippet_to_citation[sid]))
            return ''.join(f'[{num}]' for num in citation_nums)

        # Apply to both old and new list patterns
        answer_str = re.sub(new_list_pattern, replace_list, answer_str)
        answer_str = re.sub(old_list_pattern, replace_list, answer_str)

        # Remove duplicate consecutive citations
        answer_str = re.sub(r'\[(\d+)\](?:\[\1\])+', r'[\1]', answer_str)

        answer_final = json.loads(answer_str)

        logger.info(f"[UNIFIED] Converted {len(snippet_ids)} snippet IDs to {len(citations)} citations")

        return answer_final, citations, list(snippet_ids)

    def _is_validation_schema(self, schema: Dict) -> bool:
        """Check if a custom schema was provided (not Clone's default synthesis schema)."""
        return schema is not None

    def _transform_to_validation_format(self, answer: Dict, citations: List[Dict], schema: Dict) -> Dict:
        """
        General transformation to extract custom schema fields from Clone's synthesis wrapper.

        The Clone wraps all custom schema data in:
            {"comparison": {<custom_fields>}, "self_assessment": "A"}

        This unwraps and extracts the custom fields:
            {<custom_fields>} - whatever was in the custom schema

        Works for any custom schema, not just validation_results.
        """
        if not isinstance(answer, dict):
            return answer

        # Get the custom schema properties to know what to extract
        schema_properties = schema.get('properties', {}) if schema else {}
        if not schema_properties:
            logger.warning("[SCHEMA_TRANSFORM] No schema properties to extract")
            return answer

        # Check if answer already has the expected top-level structure
        has_schema_fields = any(prop in answer for prop in schema_properties.keys())
        if has_schema_fields:
            logger.info("[SCHEMA_TRANSFORM] Answer already in expected format")
            return answer

        # Extract from comparison wrapper
        comparison = answer.get('comparison', {})
        if not comparison:
            logger.warning("[SCHEMA_TRANSFORM] No comparison wrapper found")
            return answer

        # Extract custom schema fields from comparison
        extracted = {}
        for prop_name in schema_properties.keys():
            if prop_name in comparison:
                extracted[prop_name] = comparison[prop_name]
                logger.info(f"[SCHEMA_TRANSFORM] Extracted '{prop_name}' from comparison")

        if extracted:
            logger.info(f"[SCHEMA_TRANSFORM] Extracted {len(extracted)} custom schema fields")

            # If schema has single array property, return unwrapped to match Sonar format
            # Sonar returns [{"column": ...}] not {"validation_results": [...]}
            if len(extracted) == 1:
                prop_name = list(extracted.keys())[0]
                prop_value = extracted[prop_name]
                prop_schema = schema_properties.get(prop_name, {})

                if prop_schema.get('type') == 'array' and isinstance(prop_value, list):
                    logger.info(f"[SCHEMA_TRANSFORM] Unwrapping single array property '{prop_name}' to match Sonar format")
                    return prop_value

            return extracted

        # If no exact match, the LLM might have used different field names (soft schema)
        # Wrap the entire comparison in the first schema property (usually validation_results)
        if len(schema_properties) == 1:
            prop_name = list(schema_properties.keys())[0]
            prop_schema = schema_properties[prop_name]

            # If the property is an array, wrap comparison data as array
            if prop_schema.get('type') == 'array':
                logger.info(f"[SCHEMA_TRANSFORM] Wrapping comparison data into '{prop_name}' array")
                wrapped_data = [comparison] if not isinstance(comparison, list) else comparison
                # Return unwrapped to match Sonar format
                logger.info(f"[SCHEMA_TRANSFORM] Unwrapping to match Sonar format (single array)")
                return wrapped_data
            else:
                logger.info(f"[SCHEMA_TRANSFORM] Wrapping comparison data into '{prop_name}' object")
                return {prop_name: comparison}

        logger.warning(f"[SCHEMA_TRANSFORM] No custom schema fields found in comparison. Expected: {list(schema_properties.keys())}, Found: {list(comparison.keys())}")
        return answer
