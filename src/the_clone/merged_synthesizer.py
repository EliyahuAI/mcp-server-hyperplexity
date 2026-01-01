#!/usr/bin/env python3
"""
Merged Synthesizer for Clone 2.
Combines snippet extraction and synthesis into a single call.
Uses code-based citations: ["§1.1", 0.95, "P"] that get resolved after synthesis.
"""

import sys
import os
import json
import re
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime

# Add parent directories
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.ai_api_client import AIAPIClient
from shared.ai_client.utils import extract_structured_response
from the_clone.merged_synthesis_schemas import get_merged_evaluation_synthesis_schema, get_merged_synthesis_only_schema
from the_clone.config import get_synthesis_guidance
from the_clone.text_labeler import TextLabeler
from the_clone.code_resolver import CodeResolver

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MergedSynthesizer:
    """
    Merged synthesizer that combines extraction and synthesis.
    Sources are provided as labeled text, synthesis cites using codes,
    codes are resolved to text after synthesis.
    """

    def __init__(self, ai_client: AIAPIClient = None):
        """Initialize merged synthesizer."""
        self.ai_client = ai_client or AIAPIClient()
        self.text_labeler = TextLabeler()

    async def evaluate_and_synthesize(
        self,
        query: str,
        sources: List[Dict],
        context: str,
        iteration: int,
        is_last_iteration: bool,
        schema: Dict = None,
        model: str = "claude-sonnet-4-5",
        search_terms: List[str] = None,
        debug_dir: str = None,
        soft_schema: bool = False
    ) -> Dict[str, Any]:
        """
        Merged evaluation + synthesis with code-based citations.

        Instead of pre-extracted snippets, receives raw sources with labeled text.
        Synthesis cites using codes like ["§1.1", 0.95, "P"].
        Post-processing resolves codes to actual text.

        Args:
            query: User's query
            sources: List of search results (with 'snippet' text)
            context: Context level
            iteration: Current iteration
            is_last_iteration: If true, skip evaluation (just synthesize)
            schema: Optional custom schema for answer structure
            model: Model to use (default: Sonnet 4.5)
            search_terms: List of search terms used
            debug_dir: Directory for debug files
            soft_schema: Use soft schema mode

        Returns:
            Dict with:
                - can_answer: bool (only if not last iteration)
                - answer: dict (if can_answer=true or last iteration)
                - missing_aspects: list (if can_answer=false)
                - suggested_search_terms: list (if can_answer=false)
                - citations: list (final citations with resolved text)
        """
        logger.debug(f"[MERGED] Mode: {'Synthesis' if is_last_iteration else 'Evaluation+Synthesis'}")
        logger.debug(f"[MERGED] Processing {len(sources)} sources")

        # Label all sources and organize by search term
        labeled_sources = self._label_and_organize_sources(sources, search_terms)

        # Build prompt
        prompt = self._build_prompt(
            query=query,
            labeled_sources=labeled_sources,
            context=context,
            is_last_iteration=is_last_iteration
        )

        # Select schema
        if is_last_iteration:
            response_schema = get_merged_synthesis_only_schema(answer_schema=schema)
        else:
            response_schema = get_merged_evaluation_synthesis_schema(answer_schema=schema)

        # Save debug info
        if debug_dir:
            try:
                with open(os.path.join(debug_dir, f'04_merged_synthesis_iter{iteration}_prompt.md'), 'w', encoding='utf-8') as f:
                    f.write(prompt)
                with open(os.path.join(debug_dir, f'04_merged_synthesis_iter{iteration}_schema.json'), 'w', encoding='utf-8') as f:
                    json.dump(response_schema, f, indent=2)
                with open(os.path.join(debug_dir, f'04_merged_synthesis_iter{iteration}_labeled_sources.json'), 'w', encoding='utf-8') as f:
                    json.dump(labeled_sources, f, indent=2)
            except Exception as e:
                logger.warning(f"[MERGED] Failed to save debug files: {e}")

        try:
            # Call model
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=response_schema,
                model=model,
                use_cache=False,
                max_web_searches=0,
                context=f"merged_iter{iteration}",
                soft_schema=soft_schema
            )

            # Extract response
            actual_response = response.get('response', response)
            data = extract_structured_response(actual_response)

            # Parse response based on mode
            logger.debug(f"[MERGED DEBUG] data keys: {list(data.keys())}")
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
                answer_raw = data.get('answer_raw', {})
                if not answer_raw or answer_raw == {}:
                    answer_raw = {}
                    can_answer = False
                missing = data.get('missing_aspects', [])
                suggested = data.get('suggested_search_terms', [])

            logger.debug(f"[MERGED] Can answer: {can_answer}, Confidence: {confidence}")

            # Save raw response
            if debug_dir:
                try:
                    with open(os.path.join(debug_dir, f'04_merged_synthesis_iter{iteration}_response_raw.json'), 'w', encoding='utf-8') as f:
                        json.dump({
                            'can_answer': can_answer,
                            'confidence': confidence,
                            'answer_raw': answer_raw,
                            'missing': missing,
                            'suggested': suggested
                        }, f, indent=2)
                except:
                    pass

            # Convert code citations to text if answer provided
            if can_answer and answer_raw:
                answer_final, citations, codes_used, failed_resolutions = self._resolve_code_citations(
                    answer=answer_raw,
                    labeled_sources=labeled_sources
                )
            else:
                answer_final = {}
                citations = []
                codes_used = []
                failed_resolutions = []

            # Save final response
            if debug_dir:
                try:
                    with open(os.path.join(debug_dir, f'04_merged_synthesis_iter{iteration}_response_final.json'), 'w', encoding='utf-8') as f:
                        json.dump({
                            'can_answer': can_answer,
                            'confidence': confidence,
                            'answer': answer_final,
                            'citations': citations,
                            'codes_used': codes_used
                        }, f, indent=2)
                except:
                    pass

            return {
                "can_answer": can_answer,
                "confidence": confidence,
                "answer": answer_final,
                "citations": citations,
                "codes_used": codes_used,
                "failed_resolutions": failed_resolutions,
                "missing_aspects": missing,
                "suggested_search_terms": suggested,
                "synthesis_prompt": prompt,
                "model_response": response
            }

        except Exception as e:
            logger.error(f"[MERGED] Error: {e}")
            raise

    def _label_and_organize_sources(
        self,
        sources: List[Dict],
        search_terms: List[str] = None
    ) -> List[Dict]:
        """
        Label all sources with codes and organize by search term.

        Returns:
            List of labeled source dicts with structure info
        """
        labeled_sources = []

        for i, source in enumerate(sources):
            source_text = source.get('snippet', '')
            source_url = source.get('url', 'Unknown URL')
            source_title = source.get('title', 'Unknown')
            source_date = source.get('date') or source.get('last_updated', '')
            source_reliability = source.get('reliability', 'MEDIUM')
            search_ref = source.get('_search_ref', 1)
            search_term = source.get('_search_term', '')

            # Label the text
            labeled_text, text_structure = self.text_labeler.label_text(source_text)

            # Add source prefix to all codes (e.g., §1.1 -> §S1:1.1)
            source_prefix = f"S{i + 1}:"
            labeled_text = re.sub(r'§(\d+\.\d+)', f'§{source_prefix}\\1', labeled_text)

            labeled_sources.append({
                'source_id': i + 1,
                'url': source_url,
                'title': source_title,
                'date': source_date,
                'reliability': source_reliability,
                'search_ref': search_ref,
                'search_term': search_term,
                'original_text': source_text,
                'labeled_text': labeled_text,
                'structure': text_structure,
                'resolver': CodeResolver(text_structure, labeled_text, source_text)
            })

        return labeled_sources

    def _build_prompt(
        self,
        query: str,
        labeled_sources: List[Dict],
        context: str,
        is_last_iteration: bool
    ) -> str:
        """Build merged synthesis prompt."""
        guidance = get_synthesis_guidance(context)
        current_date = datetime.now().strftime('%Y-%m-%d')

        # Format labeled sources grouped by search term
        formatted_sources = self._format_labeled_sources(labeled_sources)

        # Load template
        template_path = os.path.join(
            os.path.dirname(__file__),
            'prompts',
            'merged_synthesis_code.md'
        )

        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # Determine output format guidance based on mode
        if is_last_iteration:
            output_format_guidance = """Return JSON with 'comparison' (your structured answer) and 'self_assessment' (A+ to C-) fields."""
            assessment_field = ',\n  "self_assessment": "A"'
        else:
            output_format_guidance = """Return JSON with:
- 'can_answer' (boolean)
- 'confidence' ("high"/"medium"/"low")
- 'answer_raw' (structured answer if can_answer=true, empty {} if false)
- 'missing_aspects' (array, only if can_answer=false)
- 'suggested_search_terms' (array, only if can_answer=false)"""
            assessment_field = ''

        prompt = template.format(
            query=query,
            current_date=current_date,
            synthesis_guidance=guidance,
            formatted_sources=formatted_sources,
            output_format_guidance=output_format_guidance,
            assessment_field=assessment_field
        )

        return prompt

    def _format_labeled_sources(self, labeled_sources: List[Dict]) -> str:
        """
        Format labeled sources grouped by search term.

        Format:
        Q1.1: "search term"
          Source 1: URL [DATE, RELIABILITY]
          Available codes: §S1:1.0-1.25 (26 codes), §S1:2.0-2.8 (9 codes) - Total: 35 codes
          <labeled text>

          Source 2: URL [DATE, RELIABILITY]
          Available codes: §S2:1.0-1.15 (16 codes) - Total: 16 codes
          <labeled text>
        """
        if not labeled_sources:
            return "(No sources)"

        # Group by search term
        by_search = {}
        for src in labeled_sources:
            search_ref = src.get('search_ref', 1)
            if search_ref not in by_search:
                by_search[search_ref] = []
            by_search[search_ref].append(src)

        # Format
        formatted = []
        for search_num in sorted(by_search.keys()):
            sources = by_search[search_num]
            # Get search term from first source
            search_term = sources[0].get('search_term', f'Search {search_num}')
            formatted.append(f"\nQ1.{search_num}: \"{search_term}\"")

            for src in sources:
                source_id = src['source_id']

                # Extract available codes from labeled text
                code_ranges = self._extract_code_ranges(src['labeled_text'], source_id)

                # Source header with code availability
                source_line = f"  Source {source_id}: {src['url']}"
                if src['date'] or src['reliability']:
                    meta = []
                    if src['date']:
                        meta.append(src['date'])
                    meta.append(src['reliability'])
                    source_line += f" [{', '.join(meta)}]"
                formatted.append(source_line)

                # Show available codes
                if code_ranges:
                    formatted.append(f"  Available codes: {code_ranges}")

                # Labeled text (indented)
                labeled_lines = src['labeled_text'].split('\n')
                for line in labeled_lines:
                    if line.strip():  # Skip empty lines
                        formatted.append(f"    {line}")
                formatted.append("")  # Blank line between sources

        return '\n'.join(formatted)

    def _extract_code_ranges(self, labeled_text: str, source_id: int) -> str:
        """Extract and format available code ranges from labeled text."""
        # Find all codes in format §S#:section.sentence
        codes = re.findall(r'§S\d+:(\d+)\.(\d+)', labeled_text)

        if not codes:
            return "No codes found"

        # Group by section
        by_section = {}
        for section, sentence in codes:
            section = int(section)
            sentence = int(sentence)
            if section not in by_section:
                by_section[section] = []
            by_section[section].append(sentence)

        # Format ranges
        ranges = []
        total_codes = 0
        for section in sorted(by_section.keys()):
            sentences = sorted(by_section[section])
            min_sent = min(sentences)
            max_sent = max(sentences)
            count = len(sentences)
            total_codes += count

            if min_sent == max_sent:
                ranges.append(f"§S{source_id}:{section}.{min_sent} (1 code)")
            else:
                ranges.append(f"§S{source_id}:{section}.{min_sent}-{section}.{max_sent} ({count} codes)")

        return f"{', '.join(ranges)} - Total: {total_codes} codes"

    def _resolve_code_citations(
        self,
        answer: Dict[str, Any],
        labeled_sources: List[Dict]
    ) -> Tuple[Dict[str, Any], List[Dict], List[str]]:
        """
        Extract code citations from answer and resolve to text.

        Looks for patterns like: ["§1.1", 0.95, "P"]
        Resolves codes to actual text and creates citations.

        Returns:
            (answer_with_numeric_citations, citations_list, codes_used, failed_resolutions)
        """
        answer_str = json.dumps(answer)

        # Debug: Show sample of answer_str to understand format
        sample = answer_str[:500] if len(answer_str) > 500 else answer_str
        logger.debug(f"[MERGED] answer_str sample: {sample}")

        # Pattern to match code citations: {§code, p, c:classification}
        # In JSON, this becomes: {§S1:1.1, 0.95, c:H/P}
        # Handles source-prefixed codes with optional context: {§S1:1.1 [context], 0.95, c:H/P}
        citation_pattern = r'\{§(S\d+:[\d.]+(?:-[\d.]+)?(?:\s*\[[^\]]+\])*),\s*([0-9.]+),\s*c:([^}]+)\}'

        # Find all code citations
        matches = re.findall(citation_pattern, answer_str)
        logger.debug(f"[MERGED] Found {len(matches)} code citations in answer")

        if matches:
            logger.debug(f"[MERGED] Sample matches: {matches[:3]}")

        # Extract unique citations with their metadata
        citations_metadata = []
        seen_codes = set()

        for match in matches:
            code = match[0]
            p_str = match[1]
            c_classification = match[2]

            # Clean up escaped characters
            code_clean = code.replace('\\', '')
            c_clean = c_classification.strip()

            if code_clean not in seen_codes:
                citations_metadata.append({
                    'code': code_clean,
                    'p': float(p_str),
                    'c': c_clean
                })
                seen_codes.add(code_clean)

        # Build source ID to source mapping
        source_map = {src['source_id']: src for src in labeled_sources}

        # Resolve codes to text and create citations
        citations = []
        code_to_citation_idx = {}
        url_to_citation_idx = {}  # Track citations by URL to deduplicate
        failed_resolutions = []  # Track codes that couldn't be resolved

        for cite_meta in citations_metadata:
            code = cite_meta['code']
            p_score = cite_meta['p']
            c_classification = cite_meta['c']

            # Parse source ID from code (e.g., S1:1.1 -> source 1, code 1.1)
            # Extract source ID and code part
            if ':' in code:
                source_part, code_part = code.split(':', 1)
                source_num = int(source_part.replace('S', ''))
            else:
                # Fallback: no source prefix, try all sources
                source_num = None
                code_part = code

            resolved_text = None
            source_info = None

            # Try to resolve from specific source if source ID is present
            resolution_attempt = None
            if source_num:
                # Find the specific source
                matching_sources = [src for src in labeled_sources if src['source_id'] == source_num]
                if matching_sources:
                    src = matching_sources[0]
                    resolver = src['resolver']
                    try:
                        text = resolver.resolve(code_part)
                        resolution_attempt = text if text else "(empty result)"
                        if text and text.strip():
                            resolved_text = text
                            source_info = src
                            logger.debug(f"[MERGED] Resolved code '{code}' from source {source_num}: {text[:50]}...")
                    except Exception as e:
                        resolution_attempt = f"Error: {str(e)}"
                        logger.debug(f"[MERGED] Failed to resolve '{code}' from source {source_num}: {e}")
                else:
                    resolution_attempt = f"Source S{source_num} not found"
                    logger.warning(f"[MERGED] Source {source_num} not found for code '{code}'")
            else:
                # No source prefix - try all sources (backward compat)
                for src in labeled_sources:
                    resolver = src['resolver']
                    try:
                        text = resolver.resolve(code_part)
                        if text and text.strip():
                            resolved_text = text
                            source_info = src
                            logger.debug(f"[MERGED] Resolved code '{code}' from source {src['source_id']}: {text[:50]}...")
                            break
                    except Exception as e:
                        logger.debug(f"[MERGED] Failed to resolve '{code}' from source {src['source_id']}: {e}")
                        continue

            if not resolved_text:
                logger.warning(f"[MERGED] Could not resolve code '{code}', skipping")
                failed_resolutions.append({
                    'code': code,
                    'p_score': p_score,
                    'c': c_classification,
                    'resolution_attempt': resolution_attempt if resolution_attempt else 'No attempt made',
                    'error': 'Code not found or resolution failed'
                })
                continue

            # Check if we already have a citation for this URL
            source_url = source_info['url']
            if source_url in url_to_citation_idx:
                # Append to existing citation
                citation_idx = url_to_citation_idx[source_url]
                citation = citations[citation_idx - 1]
                # Add snippet text if not already present
                if resolved_text not in citation['snippets']:
                    citation['snippets'].append(resolved_text)
                    citation['cited_text'] += '\n' + resolved_text
                code_to_citation_idx[code] = citation_idx
            else:
                # Create new citation
                citation_index = len(citations) + 1
                url_to_citation_idx[source_url] = citation_index
                code_to_citation_idx[code] = citation_index

                citations.append({
                    'url': source_url,
                    'title': source_info['title'],
                    'cited_text': resolved_text,
                    'date': source_info['date'],
                    'last_updated': source_info['date'],
                    'index': citation_index,
                    'reliability': source_info['reliability'],
                    'snippets': [resolved_text],
                    'p': p_score,
                    'c': c_classification
                })

        # Replace code citations with numeric citations
        # Pattern: ["§code", p_score, "reason"] or [[\"§code\", p_score, \"reason\"]] -> [citation_num]
        def replace_citation(match):
            code = match.group(1)
            # Remove escape characters if present
            code_clean = code.replace('\\', '')
            if code_clean in code_to_citation_idx:
                return f'[{code_to_citation_idx[code_clean]}]'
            else:
                logger.warning(f"[MERGED] Code '{code_clean}' not in citation map, keeping original")
                return match.group(0)  # Keep original if not resolved

        answer_str = re.sub(citation_pattern, replace_citation, answer_str)

        # Remove duplicate consecutive citations
        answer_str = re.sub(r'\[(\d+)\](?:\[\1\])+', r'[\1]', answer_str)

        answer_final = json.loads(answer_str)

        logger.debug(f"[MERGED] Resolved {len(citations_metadata)} code citations to {len(citations)} unique citations")
        if failed_resolutions:
            logger.warning(f"[MERGED] Failed to resolve {len(failed_resolutions)} codes")

        return answer_final, citations, list(seen_codes), failed_resolutions
