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
        clone_logger: Any = None,
        note_to_self: str = None
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
            note_to_self: Optional note from previous iteration

        Returns:
            Dict with:
                - can_answer: bool (only if not last iteration)
                - answer: dict (if can_answer=true or last iteration)
                - missing_aspects: list (if can_answer=false)
                - suggested_search_terms: list (if can_answer=false)
                - note_to_self: str (optional, from synthesis)
                - citations: list (final citations with snippet ID conversion)
        """
        logger.debug(f"[UNIFIED] Mode: {'Synthesis' if is_last_iteration else 'Evaluation+Synthesis'}")

        # Build prompt
        prompt = self._build_prompt(
            query=query,
            snippets=snippets,
            context=context,
            is_last_iteration=is_last_iteration,
            search_terms=search_terms,
            note_to_self=note_to_self
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

            # Call model with 64K max_tokens for long synthesis outputs
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=response_schema,
                model=model_chain,
                use_cache=False,
                max_web_searches=0,
                context=f"unified_iter{iteration}",
                soft_schema=soft_schema,
                max_tokens=64000
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
                # Synthesis mode - answer and potentially suggest new search
                answer_raw = data
                can_answer = True
                confidence = "high"
                missing = []
                suggested = data.get('suggested_search_terms', [])
                request_upgrade = data.get('request_capability_upgrade', False)
                new_note = data.get('note_to_self')
                self_assessment = data.get('self_assessment', 'A')  # Extract before transform loses it
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
                request_upgrade = False
                new_note = None
                self_assessment = 'A'  # Evaluation mode doesn't use self-assessment

            logger.debug(f"[UNIFIED] Can answer: {can_answer}, Confidence: {confidence}")
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
                            'suggested': suggested,
                            'request_upgrade': request_upgrade,
                            'note_to_self': new_note
                        }, f, indent=2)
                except:
                    pass

            # Convert snippet IDs to citations if answer provided
            if can_answer and answer_raw:
                answer_final, citations, snippets_used = await self._convert_snippet_ids_to_citations(
                    answer=answer_raw,
                    snippets=snippets,
                    schema=schema
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
                "request_capability_upgrade": request_upgrade,
                "note_to_self": new_note,
                "self_assessment": self_assessment,  # Preserve for iteration logic
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
        search_terms: List[str] = None,
        note_to_self: str = None
    ) -> str:
        """Build unified prompt."""
        from datetime import datetime

        guidance = get_synthesis_guidance(context)
        current_date = datetime.now().strftime('%Y-%m-%d')

        # Format snippets grouped by search term
        formatted_snippets = self._format_snippets_by_search_term(snippets, search_terms)

        if is_last_iteration:
            # Synthesis mode
            note_section = ""
            if note_to_self:
                note_section = f"""
## Note from Previous Attempt
The previous synthesis attempt was self-assessed as insufficient. Here is your note to yourself for this attempt:
"{note_to_self}"
"""

            prompt = f"""# Generate Answer from Quotes

Query: {query}

**Today's Date:** {current_date}
{note_section}
## Structure Legend

- **Q1.{'{n}'}:** Query number in iteration 1 (search term used)
- **Snippet ID Format:** S{'{iter}'}.{'{search}'}.{'{source}'}.{'{snippet}'}-p{'{score}'}
  - Example: S1.2.3.0-p0.85 = Iteration 1, Search 2, Source 3, Snippet 0, p-score 0.85
- **p (probability):** Source-level quality score (0.05-0.95) - judge tests all atomic claims, p = expected pass-rate
  - 0.85-0.95: High confidence (PRIMARY/DOCUMENTED/ATTRIBUTED) - prefer these
  - 0.50-0.65: Medium confidence (OK quality)
  - 0.05-0.30: Low confidence (UNSOURCED/STALE/PROMOTIONAL) - use cautiously
- **c (classification):** Source authority + quality codes (shown in snippet metadata)
  - H/P = High Authority + Primary
  - H/P/D/A = High + Primary + Documented + Attributed
  - M/O = Medium Authority + OK
  - L/U = Low Authority + Unsourced
- **Date:** Publication or last updated date from source

## Quotes Organized by Search Term

{formatted_snippets}

## Synthesis Instructions

{guidance}

## Your Task

Generate a structured comparison answering the query, then self-assess.

**Citation Format:** Use [verbal_handle, snippet_id] format for all citations.

**CRITICAL - COPY EXACT handles and IDs from snippets above:**
- Format: `[handle, S1.1.5.6-p0.95]` - FULL 4-part ID
- **DO NOT create your own handles** - COPY from snippet listings
- **DO NOT shorten IDs** - Use full 4-part format
- Example from listings: `[intermittent_fasting_weight_2, S1.1.1.0-p0.95]`
  - ❌ WRONG: `[if_weight, S1.1.1-p0.95]` - made up handle, shortened ID
  - ✅ CORRECT: `[intermittent_fasting_weight_2, S1.1.1.0-p0.95]` - exact copy
- **Look up the snippet in listings above, copy its [handle, ID] exactly**
- **REQUIRED:** Every factual claim must have citations

**Output Structure:** Use nested objects to avoid repetition.

**CRITICAL - Citation Placement:**
- **INLINE ONLY**: Citations must be embedded DIRECTLY in the text
- **NO separate citation fields**: Do NOT create fields like "citations": [...]
- **Format**: Include [handle, ID] at the END of each claim within the text itself

Example structure:
```json
{{
  "comparison": {{
    "current_value": "6.21% [mortgage_rate_dec2025, S1.1.1.0-p0.95]",
    "trend": "decreased from prior week [rate_change, S1.1.2.1-p0.85]"
  }},
  "self_assessment": "A"
}}
```

❌ WRONG - Separate citation fields:
```json
{{
  "feature": {{
    "description": "Feature description here",
    "citations": [["handle1, S1.1.1.0-p0.95"]]
  }}
}}
```

✅ CORRECT - Inline citations:
```json
{{
  "feature": "Feature description here [handle1, S1.1.1.0-p0.95]"
}}
```

Note: Use FULL 4-part IDs exactly as shown in snippets above.

## Self-Assessment

Grade your synthesis (A+ to C-):
- **A+/A**: Provided EXACT and SUFFICIENT answer to the query with high-quality sources
- **B**: Partial answer provided, or struggled with complexity/conflicting sources
  - **Required:** Provide a best-effort answer satisfying the schema.
  - **Optional:** If additional search would help, provide `suggested_search_terms`.
  - **Optional:** If reasoning complexity requires a smarter model, set `request_capability_upgrade=true`.
  - **Optional:** If needed for next attempt, provide `note_to_self`.
- **C**: Cannot provide sufficient answer, info not available, or insufficient capability
  - **Required:** Provide a best-effort answer satisfying the schema.
  - **Optional:** If additional search would help, provide `suggested_search_terms`.
  - **Optional:** If reasoning complexity requires a smarter model, set `request_capability_upgrade=true`.
  - **Optional:** If needed for next attempt, provide `note_to_self`.

**CRITICAL:**
- You MUST always provide an answer that satisfies the schema structure, even if incomplete.
- If you grade B or C, we will only re-run if you provide `suggested_search_terms` OR set `request_capability_upgrade=true`.
- Be specific with search terms if you need more info.

Return JSON with 'comparison', 'self_assessment', and optional 'suggested_search_terms', 'request_capability_upgrade', and 'note_to_self' fields."""

        else:
            # Evaluation + synthesis mode
            prompt = f"""# Evaluate Sufficiency and Provide Answer if Possible

Query: {query}

**Today's Date:** {current_date}

## Structure Legend

- **Q1.{'{n}'}:** Query number in iteration 1 (search term used)
- **Snippet ID Format:** S{'{iter}'}.{'{search}'}.{'{source}'}.{'{snippet}'}-p{'{score}'}
  - Example: S1.2.3.0-p0.85 = Iteration 1, Search 2, Source 3, Snippet 0, p-score 0.85
- **p (probability):** Source-level quality score (0.05-0.95) - judge tests all atomic claims, p = expected pass-rate
  - 0.85-0.95: High confidence (PRIMARY/DOCUMENTED/ATTRIBUTED) - prefer these
  - 0.50-0.65: Medium confidence (OK quality)
  - 0.05-0.30: Low confidence (UNSOURCED/STALE/PROMOTIONAL) - use cautiously
- **c (classification):** Source authority + quality codes (shown in snippet metadata)
  - H/P = High Authority + Primary
  - H/P/D/A = High + Primary + Documented + Attributed
  - M/O = Medium Authority + OK
  - L/U = Low Authority + Unsourced
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

**Citation Format:** Use [verbal_handle, snippet_id] format for all citations.

**CRITICAL - Use EXACT IDs from snippets above:**
- Format: `[handle, S1.1.5.6-p0.95]` - FULL 4-part ID
- ❌ WRONG: `[handle, S1.1.5-p0.95]` - shortened ID
- ✅ CORRECT: Copy exact IDs and handles from snippet listings
- **REQUIRED:** Always include citations when providing answers

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
                    'verbal_handle': snippet.get('verbal_handle', ''),
                    'text': snippet.get('text', ''),
                    'p': snippet.get('p', 0.50),
                    'c': snippet.get('c', 'M/O'),  # Classification (H/M/L + quality codes)
                    'reason': snippet.get('validation_reason', 'OK'),
                    '_is_lower_quality': snippet.get('_is_lower_quality', False)
                })

            # Format sources under this query
            for url, data in by_url.items():
                # Get source ID prefix from first snippet (e.g., S1.1.0 from S1.1.0.0-M)
                first_snippet_id = data['snippets'][0]['id'] if data['snippets'] else ''
                source_prefix = '.'.join(first_snippet_id.split('.')[:3]) if first_snippet_id else ''
                
                # Check for lower quality flag
                is_lower_quality = any(s.get('_is_lower_quality', False) for s in data['snippets'])

                # Source header: [S1.1.0] URL [DATE]
                source_line = f"  [{source_prefix}] {data['url']}" if source_prefix else f"  {data['url']}"
                if data['date']:
                    source_line += f" [{data['date']}]"
                
                if is_lower_quality:
                    # Get p score from the first snippet
                    p_score = data['snippets'][0].get('p', 0.50) if data['snippets'] else 0.50
                    source_line += f" [WARNING: Lower Quality Source (p={p_score})]"
                
                formatted.append(source_line)

                # Snippets under this source (with verbal handle, p-score, and classification)
                for snip in data['snippets']:
                    handle = snip.get('verbal_handle', '')
                    snippet_id = snip['id']
                    p_score = snip.get('p', 0.50)
                    c_class = snip.get('c', 'M/O')

                    # Format: [handle, S1.1.0-p0.95] (p=0.95, c=H/P) "text"
                    if handle:
                        citation_ref = f"[{handle}, {snippet_id}]"
                    else:
                        citation_ref = f"[{snippet_id}]"

                    # Show p and c metadata
                    metadata = f"(p={p_score}, c={c_class})"
                    formatted.append(f"    - {citation_ref} {metadata} \"{snip['text']}\"")

        return '\n'.join(formatted)

    async def _convert_snippet_ids_to_citations(
        self,
        answer: Dict[str, Any],
        snippets: List[Dict],
        schema: Dict = None
    ) -> tuple:
        """Convert snippet IDs to citation numbers."""
        answer_str = json.dumps(answer)

        # Build snippet maps FIRST - needed for handle lookup
        snippet_map = {s.get('id'): s for s in snippets}
        handle_to_id = {s.get('verbal_handle'): s.get('id') for s in snippets if s.get('verbal_handle')}

        # Pull ALL bracketed items and try strategies on each
        all_brackets = re.findall(r'\[([^\]]+)\]', answer_str)

        snippet_ids = []
        seen = set()
        matched_count = 0
        failed_items = []

        for item in all_brackets:
            item = item.strip()

            # Skip if already a citation number
            if item.isdigit():
                continue

            matched = False
            extracted_sid = None

            # Strategy 1: Contains comma - try [handle, ID] format
            if ',' in item:
                parts = item.split(',', 1)
                handle = parts[0].strip()
                id_part = parts[1].strip()

                # Extract snippet ID from second part
                sid_match = re.search(r'S\d+(?:\.\d+)*-p\d+\.\d+', id_part)
                if sid_match:
                    extracted_sid = sid_match.group(0)

                    # Try direct ID match
                    if extracted_sid in snippet_map:
                        matched = True  # Set matched=True even if already in seen
                        if extracted_sid not in seen:
                            snippet_ids.append(extracted_sid)
                            seen.add(extracted_sid)
                            logger.debug(f"[CITATIONS] Direct match: [{handle}, {extracted_sid}]")
                    # Fuzzy match via exact handle
                    elif handle in handle_to_id:
                        correct_sid = handle_to_id[handle]
                        matched = True  # Set matched=True even if already in seen
                        if correct_sid not in seen:
                            snippet_ids.append(correct_sid)
                            seen.add(correct_sid)
                    # Super fuzzy: partial string match on handles
                    elif len(handle) >= 15:
                        for existing_handle, existing_id in handle_to_id.items():
                            if len(existing_handle) >= 15 and (handle in existing_handle or existing_handle in handle):
                                matched = True  # Set even if already in seen
                                if existing_id not in seen:
                                    snippet_ids.append(existing_id)
                                    seen.add(existing_id)
                                break

            # Strategy 2: Starts with S and has -p - try as snippet ID (or if Strategy 1 extracted an ID but didn't match)
            if not matched and (extracted_sid or (item.startswith('S') and '-p' in item)):
                sid = extracted_sid if extracted_sid else item
                sid_match = re.search(r'S\d+(?:\.\d+)*-p\d+\.\d+', sid)
                if sid_match:
                    sid = sid_match.group(0)
                    # Try exact match first
                    if sid in snippet_map:
                        matched = True  # Set even if already in seen
                        if sid not in seen:
                            snippet_ids.append(sid)
                            seen.add(sid)
                    # Prefix match for shortened IDs (e.g., S1.1.3-p0.95 -> S1.1.3.X-p0.95)
                    elif not matched:
                        sid_prefix = sid.rsplit('-p', 1)[0]  # Get part before p-score
                        p_score = sid.split('-p')[1] if '-p' in sid else None
                        for full_id in snippet_map.keys():
                            full_prefix = full_id.rsplit('-p', 1)[0]
                            if full_prefix.startswith(sid_prefix):
                                # Check p-score matches if provided
                                if not p_score or f'-p{p_score}' in full_id:
                                    if full_id not in seen:
                                        snippet_ids.append(full_id)
                                        seen.add(full_id)
                                        matched = True
                                        break

            # Strategy 3: Try as verbal handle
            if not matched and item in handle_to_id:
                sid = handle_to_id[item]
                matched = True  # Set even if already in seen
                if sid not in seen:
                    snippet_ids.append(sid)
                    seen.add(sid)

            # Track failures for logging
            if not matched:
                failed_items.append(item)

        if failed_items:
            logger.warning(f"[CITATIONS] Could not match {len(failed_items)} items")

            # Save debug file with missing items and available pairs
            debug_output = []
            debug_output.append("=== MISSING CITATIONS ===\n")
            for item in failed_items:
                debug_output.append(f"[{item}]\n")

            debug_output.append("\n=== AVAILABLE [handle, ID] PAIRS ===\n")
            for handle, sid in sorted(handle_to_id.items()):
                snippet = snippet_map.get(sid)
                if snippet:
                    p_score = snippet.get('p', 0)
                    debug_output.append(f"[{handle}, {sid}]\n")

            # Write to file in test results directory
            try:
                import os
                debug_dir = os.path.join(os.path.dirname(__file__), 'test_results')
                os.makedirs(debug_dir, exist_ok=True)
                debug_file = os.path.join(debug_dir, 'citation_debug.txt')
                with open(debug_file, 'w') as f:
                    f.writelines(debug_output)
                logger.warning(f"[CITATIONS] Debug info saved to {debug_file}")
            except Exception as e:
                logger.warning(f"[CITATIONS] Could not save debug file: {e}")

        logger.debug(f"[CITATIONS] Matched {len(snippet_ids)} snippet references from {len(all_brackets)} bracketed items ({len(failed_items)} unmatched)")

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

            # Sort snippets by code (extract section.sentence from ID or _code field)
            def extract_sort_key(snip):
                """Extract numeric sort key from snippet code."""
                code = snip.get('_code', '')
                # If no _code, try extracting from snippet ID
                if not code:
                    snippet_id = snip.get('id', '')
                    # ID format: S1.1.1.0-p0.95 - try to use snippet number as rough ordering
                    import re
                    id_match = re.search(r'S\d+\.\d+\.\d+\.(\d+)-p', snippet_id)
                    if id_match:
                        snippet_num = int(id_match.group(1))
                        # Return snippet number as sort key (not true sequentiality, just order)
                        return (0, snippet_num)

                # Extract section.sentence from code like §S1:2.5 or §2.5
                import re
                match = re.search(r'(\d+)\.(\d+)', code)
                if match:
                    section = int(match.group(1))
                    sentence = int(match.group(2))
                    return (section, sentence)
                return (999, 999)  # Put unsortable at end

            sorted_snippets = sorted(url_snippets, key=extract_sort_key)

            # Debug: Log if _code is missing
            missing_code = sum(1 for s in url_snippets if not s.get('_code'))
            if missing_code > 0:
                logger.warning(f"[CITATIONS] {missing_code}/{len(url_snippets)} snippets missing _code field, using snippet ID order")

            # Get metadata from first snippet
            first_snippet = sorted_snippets[0]

            # Aggregate unique snippet texts, checking for sequentiality
            snippet_parts = []
            seen_texts = set()
            prev_key = None

            for snip in sorted_snippets:
                text = snip.get('text', '')
                if not text or text in seen_texts:
                    continue

                current_key = extract_sort_key(snip)

                # Add separator if this is not the first snippet
                if snippet_parts and prev_key:
                    # Check if sequential: same section, consecutive sentence numbers
                    is_sequential = (current_key[0] == prev_key[0] and
                                   current_key[1] == prev_key[1] + 1)
                    if is_sequential:
                        # Sequential, add space
                        snippet_parts.append(' ')
                    else:
                        # Non-sequential, add inline ellipsis
                        snippet_parts.append(' ... ')

                snippet_parts.append(text)
                seen_texts.add(text)
                prev_key = current_key

            # Combine all snippets into single cited_text
            cited_text = ''.join(snippet_parts) if snippet_parts else ''

            # Sonar-compatible format with additional Clone-specific fields
            citations.append({
                'url': source_url,
                'title': first_snippet.get('_source_title', 'Unknown'),
                'cited_text': cited_text,
                'date': first_snippet.get('_source_date', ''),
                'last_updated': first_snippet.get('_source_date', ''),
                'index': citation_index,
                'reliability': first_snippet.get('_source_reliability', 'MEDIUM'),
                'snippets': [cited_text],  # Single combined text
                'p': first_snippet.get('p', 0.50),  # Source-level probability
                'c': first_snippet.get('c', 'M/O')  # Source-level classification
            })

        # Map snippet IDs to citation indices
        handle_to_citation = {}
        for snippet_id in snippet_ids:
            snippet = snippet_map.get(snippet_id)
            if snippet:
                source_url = snippet.get('_source_url', '')
                citation_idx = url_to_citation_idx.get(source_url)
                snippet_to_citation[snippet_id] = citation_idx

                # Also map handle to citation
                handle = snippet.get('verbal_handle')
                if handle:
                    handle_to_citation[handle] = citation_idx

        # Replace all matched snippet IDs with citation numbers
        # We've already identified all valid snippet IDs above, now replace any occurrence
        for snippet_id, citation_idx in snippet_to_citation.items():
            # Replace [handle, snippet_id] format (raw JSON arrays)
            answer_str = re.sub(rf'\[[^,\]]+,\s*{re.escape(snippet_id)}\]', f'[{citation_idx}]', answer_str)
            # Replace "handle, snippet_id" format (strings in JSON arrays)
            # Keep as string to maintain valid JSON structure
            answer_str = re.sub(rf'"[^"]*,\s*{re.escape(snippet_id)}"', f'"{citation_idx}"', answer_str)
            # Replace [snippet_id] format
            answer_str = answer_str.replace(f'[{snippet_id}]', f'[{citation_idx}]')
            # Replace "snippet_id" format (strings) - keep as string
            answer_str = answer_str.replace(f'"{snippet_id}"', f'"{citation_idx}"')

        # Replace handle-only citations
        for handle, citation_idx in handle_to_citation.items():
            answer_str = re.sub(rf'\[{re.escape(handle)}\]', f'[{citation_idx}]', answer_str)
            # Keep handle-only string citations as strings
            answer_str = re.sub(rf'"{re.escape(handle)}"', f'"{citation_idx}"', answer_str)

        # Remove duplicate consecutive citations
        answer_str = re.sub(r'\[(\d+)\](?:\[\1\])+', r'[\1]', answer_str)

        # Parse JSON with repair fallback
        try:
            answer_final = json.loads(answer_str)
        except json.JSONDecodeError as e:
            logger.error(f"[UNIFIED] JSON parse error at char {e.pos}: {e.msg}")
            logger.error(f"[UNIFIED] Malformed JSON snippet: ...{answer_str[max(0, e.pos-100):e.pos+100]}...")

            # Try Gemini repair
            try:
                from shared.ai_client.utils import repair_json_with_haiku
                logger.warning(f"[UNIFIED] Attempting Gemini repair for malformed synthesis JSON")
                answer_final, repair_result, repair_explanation = await repair_json_with_haiku(
                    answer_str, schema or {}, self.ai_client
                )
                if answer_final:
                    logger.debug(f"[UNIFIED] Gemini repair succeeded: {repair_explanation}")
                else:
                    raise Exception("Gemini repair failed")
            except Exception as repair_error:
                logger.error(f"[UNIFIED] Repair failed: {repair_error}")
                raise e  # Re-raise original parse error

        logger.debug(f"[UNIFIED] Converted {len(snippet_ids)} snippet IDs to {len(citations)} citations")

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
            logger.debug("[SCHEMA_TRANSFORM] Answer already in expected format")
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
                logger.debug(f"[SCHEMA_TRANSFORM] Extracted '{prop_name}' from comparison")

        if extracted:
            logger.debug(f"[SCHEMA_TRANSFORM] Extracted {len(extracted)} custom schema fields")

            # If schema has single array property, return unwrapped to match Sonar format
            # Sonar returns [{"column": ...}] not {"validation_results": [...]}
            if len(extracted) == 1:
                prop_name = list(extracted.keys())[0]
                prop_value = extracted[prop_name]
                prop_schema = schema_properties.get(prop_name, {})

                if prop_schema.get('type') == 'array' and isinstance(prop_value, list):
                    logger.debug(f"[SCHEMA_TRANSFORM] Unwrapping single array property '{prop_name}' to match Sonar format")
                    return prop_value

            return extracted

        # If no exact match, the LLM might have used different field names (soft schema)
        # Wrap the entire comparison in the first schema property (usually validation_results)
        if len(schema_properties) == 1:
            prop_name = list(schema_properties.keys())[0]
            prop_schema = schema_properties[prop_name]

            # If the property is an array, wrap comparison data as array
            if prop_schema.get('type') == 'array':
                logger.debug(f"[SCHEMA_TRANSFORM] Wrapping comparison data into '{prop_name}' array")
                wrapped_data = [comparison] if not isinstance(comparison, list) else comparison
                # Return unwrapped to match Sonar format
                logger.debug(f"[SCHEMA_TRANSFORM] Unwrapping to match Sonar format (single array)")
                return wrapped_data
            else:
                logger.debug(f"[SCHEMA_TRANSFORM] Wrapping comparison data into '{prop_name}' object")
                return {prop_name: comparison}

        logger.warning(f"[SCHEMA_TRANSFORM] No custom schema fields found in comparison. Expected: {list(schema_properties.keys())}, Found: {list(comparison.keys())}")
        return answer
