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

_SHORT_ID_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def _make_short_id(index: int) -> str:
    """Generate a two-letter snippet anchor (AA, AB, ..., ZZ) from a zero-based index."""
    a = (index // 26) % 26
    b = index % 26
    return _SHORT_ID_ALPHABET[a] + _SHORT_ID_ALPHABET[b]


def _query_slug(query: str, max_len: int = 40) -> str:
    """Convert a query string to a safe filename slug."""
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', (query or 'unknown')[:max_len])
    return slug.strip('_') or 'unknown'


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
        model: str = "claude-sonnet-4-6",
        search_terms: List[str] = None,
        debug_dir: str = None,
        soft_schema: bool = False,
        clone_logger: Any = None,
        note_to_self: str = None,
        initial_decision: str = None,
        sources_examined: List[Dict] = None,
        previous_iteration_data: Dict = None
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
            previous_iteration_data: Optional dict with previous iteration's response, grade, etc.

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

        # 2d: Assign stable two-letter short_ids to all snippets for this synthesis call.
        # These are assigned here (not at extraction time) so they're always unique within
        # the full set of snippets passed to this synthesizer invocation.
        for i, snippet in enumerate(snippets):
            if 'short_id' not in snippet:
                snippet['short_id'] = _make_short_id(i)

        # Build prompt
        prompt = self._build_prompt(
            query=query,
            snippets=snippets,
            context=context,
            is_last_iteration=is_last_iteration,
            iteration=iteration,
            search_terms=search_terms,
            note_to_self=note_to_self,
            initial_decision=initial_decision,
            sources_examined=sources_examined or [],
            previous_iteration_data=previous_iteration_data
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

            # Detect if this is a refinement scenario (iteration > 1 with previous data)
            is_refinement = previous_iteration_data is not None and previous_iteration_data.get('response')

            # Prepare refinement mode parameters
            refinement_kwargs = {}
            if is_refinement:
                # Extract previous answer as original_data to refine
                previous_response = previous_iteration_data.get('response', {})

                # Unwrap the schema wrapper to get the actual data
                # Previous iterations may have used different wrappers (answer_raw, comparison)
                # We need the core data that matches the custom schema
                if 'answer_raw' in previous_response:
                    # From evaluation mode (iteration 1)
                    previous_answer = previous_response['answer_raw']
                elif 'comparison' in previous_response:
                    # From synthesis mode (iteration 2+)
                    previous_answer = previous_response['comparison']
                else:
                    # Direct data or unknown structure - use as-is
                    previous_answer = previous_response

                # Build refinement context with iteration metadata
                refinement_context = {}
                prev_grade = previous_iteration_data.get('grade', 'Unknown')
                prev_iteration = previous_iteration_data.get('iteration', 1)
                prev_note = previous_iteration_data.get('note_to_self', '')
                prev_search_terms = previous_iteration_data.get('search_terms', [])

                refinement_context['Previous Iteration'] = f"Iteration {prev_iteration}, Grade: {prev_grade}"
                if prev_note:
                    refinement_context['Self-Assessment Note'] = prev_note
                if prev_search_terms:
                    refinement_context['Search Terms Used'] = ', '.join(f'"{t}"' for t in prev_search_terms)

                # Set refinement parameters
                refinement_kwargs['original_data'] = previous_answer
                refinement_kwargs['refinement_context'] = refinement_context
                refinement_kwargs['try_patches_first'] = True  # Enable Tier 1 patches

                logger.debug(f"[UNIFIED] 🎯 REFINEMENT MODE: Iteration {iteration}, refining previous answer from iteration {prev_iteration}")
                if clone_logger:
                    clone_logger.log_section(f"Refinement Mode Activated (Iter {iteration})", {
                        "Refining": f"Iteration {prev_iteration} answer (Grade: {prev_grade})",
                        "Strategy": "3-tier cost-optimized refinement",
                        "Tier 1": "Patches (fast, cheap)",
                        "Tier 2": "Cheap model full implementation",
                        "Tier 3": "Primary model full generation (fallback)"
                    }, level=3, collapse=True)

            # Call model with 64K max_tokens for long synthesis outputs
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=response_schema,
                model=model_chain,
                use_cache=False,
                max_web_searches=0,
                context=f"unified_iter{iteration}",
                soft_schema=soft_schema,
                max_tokens=64000,
                **refinement_kwargs  # Add refinement params if iteration > 1
            )

            # Log refinement results if applicable
            if is_refinement and response.get('refinement_tier'):
                tier = response.get('refinement_tier')
                total_cost = response.get('total_refinement_cost', 0.0)
                method = response.get('method', 'unknown')
                tier_costs = response.get('tier_costs', [])

                tier_names = {1: "Patches", 2: "Cheap Model", 3: "Full Generation"}
                tier_name = tier_names.get(tier, f"Tier {tier}")

                logger.info(f"[UNIFIED] ✅ Refinement Tier {tier} SUCCESS: {method} (${total_cost:.4f})")

                if clone_logger:
                    clone_logger.log_section(f"Refinement Success (Tier {tier})", {
                        "Method": f"{tier_name} ({method})",
                        "Cost": f"${total_cost:.4f}",
                        "Tier Breakdown": {f"Tier {i+1}": f"${cost:.4f}" for i, cost in enumerate(tier_costs)},
                        "Patches Applied": len(response.get('patches', [])) if tier == 1 else "N/A"
                    }, level=3, collapse=False)

            # Log model attempts if backups were used
            if clone_logger and response.get('attempted_models'):
                clone_logger.log_model_attempts(response['attempted_models'], f"Synthesis Iteration {iteration}")

            # Extract response using centralized parsing
            # In refinement mode, use refined_data if available
            used_refinement_data = False
            if is_refinement and response.get('refined_data'):
                data = response.get('refined_data')
                used_refinement_data = True
                logger.debug(f"[UNIFIED] Using refined_data from refinement mode")
            else:
                actual_response = response.get('response', response)
                data = extract_structured_response(actual_response)

            if clone_logger:
                clone_logger.log_section(f"Synthesis Result (Iter {iteration})", data, level=3, collapse=True)

            # Parse response based on mode
            # Note: data can be a list (from array responses) or dict (from object responses)
            if isinstance(data, dict):
                logger.debug(f"[UNIFIED] data keys: {list(data.keys())}")
            else:
                logger.debug(f"[UNIFIED] data type: {type(data).__name__} (length: {len(data) if hasattr(data, '__len__') else 'N/A'})")
            if is_last_iteration:
                # Synthesis mode - answer and potentially suggest new search
                answer_raw = data
                can_answer = True
                confidence = "high"
                missing = []
                # Handle both dict (normal synthesis) and list (refinement mode with array responses)
                if isinstance(data, dict):
                    suggested = data.get('suggested_search_terms', [])
                    new_note = data.get('note_to_self')
                    # Parse pipe-separated grade+signals: "B|T|S" → grade="B", T/E flags
                    grade_raw = data.get('self_assessment', 'A')
                    grade_parts = [p.strip() for p in grade_raw.split('|')]
                    self_assessment = grade_parts[0] if grade_parts else 'A'
                    signal_flags = set(grade_parts[1:])
                    needs_thinking = 'T' in signal_flags
                    needs_expert   = 'E' in signal_flags
                    needs_search   = 'S' in signal_flags
                else:
                    # List response (from refinement mode) - no metadata fields
                    suggested = []
                    needs_thinking = False
                    needs_expert   = False
                    needs_search   = False
                    new_note = None
                    self_assessment = 'A'
            else:
                # Evaluation mode - may have answer
                # Handle both dict (normal) and list (edge case)
                if isinstance(data, dict):
                    can_answer = data.get('can_answer', False)
                    confidence = data.get('confidence', 'low')
                    answer_raw = data.get('answer_raw', {})  # Extract from answer_raw field
                    # If answer is empty object, treat as no answer
                    if not answer_raw or answer_raw == {}:
                        answer_raw = {}
                        can_answer = False
                    missing = data.get('missing_aspects', [])
                    suggested = data.get('suggested_search_terms', [])
                else:
                    # List response (edge case) - treat as answer with no metadata
                    can_answer = True
                    confidence = 'medium'
                    answer_raw = data
                    missing = []
                    suggested = []
                needs_thinking = False
                needs_expert   = False
                needs_search   = False
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
                            'needs_thinking': needs_thinking,
                            'needs_expert': needs_expert,
                            'needs_search': needs_search,
                            'note_to_self': new_note
                        }, f, indent=2)
                except:
                    pass

            # Convert snippet IDs to citations if answer provided
            # Skip conversion for intermediate refinement iterations (preserves snippet IDs for AI context)
            # Always convert on FINAL iteration to get numeric citations for user output
            # IMPORTANT: Always preserve answer_raw (pre-conversion, with full snippet IDs) separately.
            # This is critical for self-correction: the next iteration's patches must receive full
            # snippet IDs, not numbered [1][2] citations which the patch system cannot re-expand.
            if can_answer and answer_raw:
                if used_refinement_data and not is_last_iteration:
                    # Intermediate refinement - keep snippet IDs so AI knows exact snippets for next iteration
                    answer_final = answer_raw
                    citations = []  # Citations will be generated on final iteration
                    snippets_used = []
                    logger.debug(f"[UNIFIED] Preserving snippet IDs for intermediate refinement (iteration {iteration})")
                else:
                    # Final iteration OR normal mode - convert snippet IDs to numeric citations
                    answer_final, citations, snippets_used = await self._convert_snippet_ids_to_citations(
                        answer=answer_raw,
                        snippets=snippets,
                        schema=schema,
                        debug_dir=debug_dir,
                        query=query
                    )
                    logger.debug(f"[UNIFIED] Converting snippet IDs to citations (final={is_last_iteration})")

                    # Post-process for validation format if custom schema is validation_results
                    if schema and self._is_validation_schema(schema):
                        answer_final = self._transform_to_validation_format(answer_final, citations, schema)
            else:
                answer_final = {}
                citations = []
                snippets_used = []

            # Extract refinement info if available
            refinement_info = {}
            if is_refinement and response.get('refinement_tier'):
                refinement_info = {
                    "refinement_tier": response.get('refinement_tier'),
                    "refinement_method": response.get('method'),
                    "refinement_cost": response.get('total_refinement_cost', 0.0),
                    "tier_costs": response.get('tier_costs', [])
                }

            return {
                "can_answer": can_answer,
                "confidence": confidence,
                "answer": answer_final,
                # answer_pre_conversion: the raw LLM output with full [handle, SID] citations intact.
                # Used by the self-correction loop so patches operate on real snippet IDs, not [1][2].
                "answer_pre_conversion": answer_raw if answer_raw else {},
                "citations": citations,
                "snippets_used": snippets_used,
                "missing_aspects": missing,
                "suggested_search_terms": suggested,
                "needs_thinking": needs_thinking,
                "needs_expert": needs_expert,
                "needs_search": needs_search,
                "note_to_self": new_note,
                "self_assessment": self_assessment,  # Preserve for iteration logic
                "iteration": iteration,  # Track iteration number for next refinement
                "synthesis_prompt": prompt,  # Return actual prompt sent to model
                "model_response": response,
                **refinement_info  # Include refinement metrics at top level for tracking
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
        iteration: int = 1,
        search_terms: List[str] = None,
        note_to_self: str = None,
        initial_decision: str = None,
        sources_examined: List[Dict] = None,
        previous_iteration_data: Dict = None
    ) -> str:
        """Build unified prompt."""
        from datetime import datetime

        guidance = get_synthesis_guidance(context)
        current_date = datetime.now().strftime('%Y-%m-%d')

        # Format snippets grouped by search term, passing current iteration for NEW/PREV labels
        formatted_snippets = self._format_snippets_by_search_term(snippets, search_terms, current_iteration=iteration)

        # Check for source mismatch: initial decision expected sources but we have none
        source_mismatch_warning = ""
        if initial_decision == "need_search" and len(snippets) == 0:
            # Format sources that were examined but produced no snippets
            examined_list = ""
            if sources_examined and len(sources_examined) > 0:
                examined_list = "\n**Sources Examined (but no relevant snippets extracted):**\n\n"
                for i, src in enumerate(sources_examined[:10], 1):  # Show max 10
                    title = src.get('title', 'No title')[:80]
                    url = src.get('url', 'No URL')
                    from_memory = " [FROM MEMORY]" if src.get('_from_memory') else ""
                    original_query = src.get('_original_query', src.get('_search_term', ''))
                    examined_list += f"{i}. {title}{from_memory}\n"
                    examined_list += f"   URL: {url}\n"
                    if original_query:
                        examined_list += f"   Found via: \"{original_query}\"\n"
                    examined_list += "\n"
                if len(sources_examined) > 10:
                    examined_list += f"   ... and {len(sources_examined) - 10} more sources\n"

            source_mismatch_warning = f"""
**⚠️ WARNING: NO SNIPPETS EXTRACTED**

The initial decision determined that web search was needed to answer this query.
However, extraction found NO relevant facts in the sources provided.

{examined_list}
**Extraction returned 0 snippets** - the sources above were examined but contained no
specific facts relevant to the query (they may be topically related but lack the
specific entities, dates, or details needed).

**You have two options:**
1. **Grade yourself "B"** and provide `suggested_search_terms` to trigger a fresh search
   - Recommend more specific search terms that target the exact entities/facts needed
2. **Answer from context** if the query provides sufficient information in the prompt itself

If you choose option 2, be transparent in your `note_to_self` that you answered without
source citations (used prompt context only).

"""

        if is_last_iteration:
            # Synthesis mode
            previous_iteration_section = ""
            if previous_iteration_data:
                prev_iteration = previous_iteration_data.get('iteration', 1)
                prev_grade = previous_iteration_data.get('grade', 'Unknown')
                prev_response = previous_iteration_data.get('response') or {}
                prev_note = previous_iteration_data.get('note_to_self') or ''
                prev_search_terms = previous_iteration_data.get('search_terms') or []

                # Format search terms used in previous iteration
                search_terms_str = ""
                if prev_search_terms:
                    search_terms_str = "\n**Search Terms Used:** " + ", ".join(f'"{t}"' for t in prev_search_terms)

                # Format the previous response as JSON
                try:
                    prev_response_str = json.dumps(prev_response, indent=2) if prev_response else "(No response generated)"
                    # Escape any triple backticks in the JSON to prevent markdown breakage
                    prev_response_str = prev_response_str.replace('```', '` ` `')
                except:
                    prev_response_str = str(prev_response).replace('```', '` ` `')

                previous_iteration_section = f"""
## Your Previous Response (Iteration {prev_iteration}), Grade: {prev_grade}
{search_terms_str}

```json
{prev_response_str}
```

**Grade: {prev_grade}**"""

                if prev_note:
                    previous_iteration_section += f"""
**Your Comment to Self:** "{prev_note}"
"""

                previous_iteration_section += """

---
**IMPORTANT:** You are now receiving additional search results based on your self-correction request.
Use your previous response as a foundation and improve upon it with the new information.
"""
            elif note_to_self:
                # Fallback to old behavior if only note_to_self is provided
                previous_iteration_section = f"""
## Note from Previous Attempt
The previous synthesis attempt was self-assessed as insufficient. Here is your note to yourself for this attempt:
"{note_to_self}"
"""

            prompt = f"""# Generate Answer from Quotes

Query: {query}

**Today's Date:** {current_date}
{previous_iteration_section}
## Structure Legend

- **Q{'{iter}'}.{'{n}'}:** Query from iteration {'{iter}'}, search {'{n}'} (search term used). [★ NEW] = added this pass; [◎ PREV] = from earlier pass.
- **Snippet ID Format:** S{'{iter}'}.{'{search}'}.{'{source}'}.{'{snippet}'}-p{'{score}'}
  - Example: S1.2.3.0-p0.85 = Iteration 1, Search 2, Source 3, Snippet 0, p-score 0.85
- **2-letter anchor (AA, AB…):** Short stable alias shown after the citation ref as (AA). You may cite using the 2-letter anchor alone: `[AA]` — it resolves to the full snippet. Use `[handle, snippet_id]` for clarity, `[AA]` as fallback if exact ID is hard to recall.
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
{source_mismatch_warning}
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

Imagine a client paid an expert researcher for this answer. Would they be satisfied?

**Expert answers have:**
- Direct response to what was asked (no tangents, no gaps)
- Specific facts (numbers, dates, names - not vague generalities)
- Claims backed by authoritative sources with citations
- Complete coverage (nothing important missing that's findable online)
- Clear and well-organized presentation

**Grade your synthesis using format: GRADE[|T][|S][|E]**
- **A+/A**: Expert-quality — client would be satisfied, nothing important missing
- **A-/B**: Acceptable but incomplete — missing information likely findable online
- **C**: Insufficient — cannot meaningfully answer, or information not available

**Optional signals (append to grade with `|`, only effective when grade is below A):**
- **|T**: More thinking depth needed — bumps thinking budget or escalates to a stronger model
  (use when the *reasoning challenge* requires deeper analysis, not just more data)
- **|S**: More/better search would help — also provide `suggested_search_terms`
- **|E**: Escalate to an expert model — PhD-level reasoning required beyond current capability

**Examples:** `"A"`, `"B|S"`, `"C|T|S"`, `"A+|T"`, `"B|E"`, `"C|T|S|E"`

**CRITICAL for suggested_search_terms (when using |S):**
- ONLY suggest search terms when you have HIGH CONFIDENCE they will find new, useful information
- Do NOT suggest speculative or exploratory searches ("maybe there's more about X")
- Each term should target a SPECIFIC gap you identified (e.g., "Company Y Phase 3 trial results 2024")
- If you're unsure whether more searches would help, do NOT use |S — just give your best answer
- Empty `suggested_search_terms` is preferable to low-confidence guesses

**CRITICAL:**
- You MUST always provide an answer that satisfies the schema structure, even if incomplete.
- Signals are only acted on when grade is below A.

Return JSON with 'comparison', 'self_assessment', and optional 'suggested_search_terms' and 'note_to_self' fields.

**⚠️ RESPONSE LENGTH LIMIT: Keep your total response under 24000 words.{' Be terse - validation will expand details later.' if context == 'findall' else ''}**"""

        else:
            # Evaluation + synthesis mode
            prompt = f"""# Evaluate Sufficiency and Provide Answer if Possible

Query: {query}

**Today's Date:** {current_date}

## Structure Legend

- **Q{'{iter}'}.{'{n}'}:** Query from iteration {'{iter}'}, search {'{n}'}. [★ NEW] = added this pass; [◎ PREV] = from earlier pass.
- **Snippet ID Format:** S{'{iter}'}.{'{search}'}.{'{source}'}.{'{snippet}'}-p{'{score}'}
  - Example: S1.2.3.0-p0.85 = Iteration 1, Search 2, Source 3, Snippet 0, p-score 0.85
- **2-letter anchor (AA, AB…):** Short alias after citation ref as (AA). Cite using `[handle, snippet_id]` or bare `[AA]` if needed.
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
{source_mismatch_warning}
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

**⚠️ RESPONSE LENGTH LIMIT: Keep your total response under 24000 words.{' Be terse - validation will expand details later.' if context == 'findall' else ''}**

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

    def _format_snippets_by_search_term(self, snippets: List[Dict], search_terms: List[str] = None, current_iteration: int = 1) -> str:
        """
        Format snippets in nested structure:
        Q{iter}.{search}: "query text"  [★ NEW] or [◎ PREV]
          [S1.1.0] URL | Page Title [DATE]
            - [handle, S1.1.0.0-p0.95] (AA) (p=0.95, c=H/P) "text"

        Groups by (iteration, search) extracted from snippet ID so Q-labels always reflect
        the iteration in which each search was executed (Q1.x = first pass, Q2.x = second).
        """
        if not snippets:
            return "(No quotes)"

        def _iter_search_from_id(sid: str):
            """Extract (iter_num, search_num) from snippet ID like S1.2.3.0-p0.95."""
            m = re.match(r'S(\d+)\.(\d+)\.', sid or '')
            if m:
                return int(m.group(1)), int(m.group(2))
            return None, None

        # Group by (iter_num, search_num) extracted from snippet ID
        by_iter_search = {}
        query_for_key = {}

        for snippet in snippets:
            sid = snippet.get('id', '')
            iter_num, search_num = _iter_search_from_id(sid)
            if iter_num is None:
                # Fallback: non-standard IDs (memory snippets SM.x, etc.)
                iter_num = 1
                search_num = snippet.get('search_ref', 1)

            key = (iter_num, search_num)
            if key not in by_iter_search:
                by_iter_search[key] = []
                # Best source for query text: _search_term on the snippet itself
                query_for_key[key] = snippet.get('_search_term', '')

            by_iter_search[key].append(snippet)

        # Format
        formatted = []
        for (iter_num, search_num) in sorted(by_iter_search.keys()):
            query_text = query_for_key.get((iter_num, search_num), f'Search {search_num}')

            # Mark new vs. previously seen snippets
            if current_iteration > 1:
                if iter_num == current_iteration:
                    label_suffix = " [★ NEW]"
                else:
                    label_suffix = " [◎ PREV]"
            else:
                label_suffix = ""

            formatted.append(f"\nQ{iter_num}.{search_num}:{label_suffix} \"{query_text}\"")

            # Group by source URL within this (iter, search)
            by_url = {}
            for snippet in by_iter_search[(iter_num, search_num)]:
                url = snippet.get('_source_url', 'Unknown URL')
                if url not in by_url:
                    by_url[url] = {
                        'url': url,
                        'title': snippet.get('_source_title', ''),
                        'date': snippet.get('_source_date', ''),
                        'snippets': []
                    }
                by_url[url]['snippets'].append({
                    'id': snippet.get('id', ''),
                    'short_id': snippet.get('short_id', ''),
                    'verbal_handle': snippet.get('verbal_handle', ''),
                    'text': snippet.get('text', ''),
                    'p': snippet.get('p', 0.50),
                    'c': snippet.get('c', 'M/O'),
                    '_is_lower_quality': snippet.get('_is_lower_quality', False)
                })

            # Format sources under this query
            for url, data in by_url.items():
                first_snippet_id = data['snippets'][0]['id'] if data['snippets'] else ''
                source_prefix = '.'.join(first_snippet_id.split('.')[:3]) if first_snippet_id else ''

                is_lower_quality = any(s.get('_is_lower_quality', False) for s in data['snippets'])

                # Source header: [S1.1.0] URL | Title [DATE]
                source_line = f"  [{source_prefix}] {data['url']}" if source_prefix else f"  {data['url']}"
                if data.get('title'):
                    source_line += f" | {data['title'][:80]}"
                if data['date']:
                    source_line += f" [{data['date']}]"
                if is_lower_quality:
                    p_score = data['snippets'][0].get('p', 0.50)
                    source_line += f" [WARNING: Lower Quality Source (p={p_score})]"

                formatted.append(source_line)

                # Snippets under this source: include 2-letter short_id anchor for reliable citation
                for snip in data['snippets']:
                    handle = snip.get('verbal_handle', '')
                    snippet_id = snip['id']
                    short_id = snip.get('short_id', '')
                    p_score = snip.get('p', 0.50)
                    c_class = snip.get('c', 'M/O')

                    # Format: [handle, S1.1.0.0-p0.95] (AA) (p=0.95, c=H/P) "text"
                    if handle:
                        citation_ref = f"[{handle}, {snippet_id}]"
                    else:
                        citation_ref = f"[{snippet_id}]"

                    anchor_str = f" ({short_id})" if short_id else ""
                    metadata = f"(p={p_score}, c={c_class})"
                    formatted.append(f"    - {citation_ref}{anchor_str} {metadata} \"{snip['text']}\"")

        return '\n'.join(formatted)

    async def _llm_resolve_snippet(self, reference: str, snippet_map: dict, query: str = None) -> str | None:
        """Use a small LLM to identify which snippet best matches an unresolvable reference.

        Called as a last-resort fallback (Suggestion 2b) when exact/fuzzy/handle/sibling
        matching all fail for a single-occurrence citation reference.

        Returns snippet_id string if a match is found, None otherwise.
        """
        candidates = sorted(snippet_map.values(), key=lambda s: s.get('p', 0), reverse=True)[:10]
        if not candidates:
            return None

        candidate_lines = []
        for s in candidates:
            sid = s.get('id', '?')
            handle = s.get('verbal_handle', '?')
            preview = (s.get('text') or '')[:120].replace('\n', ' ')
            candidate_lines.append(f"- {sid}  [{handle}]  {preview}")

        prompt = (
            f'Which snippet best matches this unresolved citation reference: "{reference}"?\n'
            + (f'Query context: {(query or "")[:100]}\n\n' if query else '\n')
            + 'Available snippets:\n'
            + '\n'.join(candidate_lines)
            + '\n\nReturn ONLY the snippet id (e.g. S1.2.3.0-p0.95) of the best match, '
            + 'or exactly the word "none" if no snippet matches.'
        )
        try:
            resp = await self.ai_client.query_async(
                prompt=prompt,
                model='gemini-3-flash-preview-low',
                context='snippet_llm_resolve',
                max_tokens=60
            )
            result = (resp.get('text') or '').strip().split('\n')[0].strip()
            if result and result != 'none' and result in snippet_map:
                return result
        except Exception as e:
            logger.debug(f"[CITATIONS] LLM snippet resolve error: {e}")
        return None

    async def _convert_snippet_ids_to_citations(
        self,
        answer: Dict[str, Any],
        snippets: List[Dict],
        schema: Dict = None,
        debug_dir: str = None,
        query: str = None
    ) -> tuple:
        """Convert snippet IDs to citation numbers."""
        answer_str = json.dumps(answer)

        # Build snippet maps FIRST - needed for handle lookup
        snippet_map = {s.get('id'): s for s in snippets}
        handle_to_id = {s.get('verbal_handle'): s.get('id') for s in snippets if s.get('verbal_handle')}
        # 2d: two-letter short_id map (stable anchor; assigned in evaluate_and_synthesize)
        short_id_map = {s.get('short_id'): s.get('id') for s in snippets if s.get('short_id')}

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

            # Strategy 0 (2d): Two-letter short_id anchor (AA, AB, ..., ZZ)
            # Checked first because it's unambiguous when present.
            if not matched and re.match(r'^[A-Z]{2}$', item):
                sid = short_id_map.get(item)
                if sid:
                    matched = True
                    if sid not in seen:
                        snippet_ids.append(sid)
                        seen.add(sid)
                        logger.debug(f"[CITATIONS] Short-ID match: [{item}] → {sid}")

            # Strategy 1: Contains comma - try [handle, ID] format
            if ',' in item:
                parts = item.split(',', 1)
                handle = parts[0].strip()
                id_part = parts[1].strip()

                # Extract snippet ID from second part
                # Pattern matches both search (S1.x.x.x) and memory (SM.x.x.x) snippet IDs
                sid_match = re.search(r'S(?:M|C|\d+)(?:\.\d+)+(?:-p\d+\.\d+)?', id_part)
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

            # Strategy 2: Starts with S - try as snippet ID (or if Strategy 1 extracted an ID but didn't match)
            # Matches search (S1.x), memory (SM.x), and citation recall (SC.x) formats with or without -p suffix
            if not matched and (extracted_sid or item.startswith('S')):
                sid = extracted_sid if extracted_sid else item
                # Pattern matches both search (S1.x.x.x) and memory (SM.x.x.x) snippet IDs, with optional -p suffix
                sid_match = re.search(r'S(?:M|C|\d+)(?:\.\d+)+(?:-p\d+\.\d+)?', sid)
                if sid_match:
                    sid = sid_match.group(0)
                    # Try exact match first
                    if sid in snippet_map:
                        matched = True  # Set even if already in seen
                        if sid not in seen:
                            snippet_ids.append(sid)
                            seen.add(sid)
                    # Prefix match for shortened IDs (e.g., S1.1.3 -> S1.1.3.X-p0.95, or S1.1.3-p0.95 -> S1.1.3.X-p0.95)
                    elif not matched:
                        # Get the base ID without p-score (if present)
                        sid_prefix = sid.rsplit('-p', 1)[0] if '-p' in sid else sid
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

            # Strategy 4 (2a): Sibling fallback — find any snippet from the same source.
            # When the specific snippet ID is unavailable (e.g., dropped during extraction),
            # use another snippet from the same source URL as a citation anchor.
            if not matched:
                sid_to_try = extracted_sid or (item if re.match(r'S(?:M|C|\d+)(?:\.\d+)', item) else None)
                if sid_to_try:
                    # Source prefix: S{search_ref}.{source_num}  (first two numeric segments)
                    src_prefix_match = re.match(r'(S(?:M|C|\d+)\.\d+)\.', sid_to_try)
                    if src_prefix_match:
                        src_prefix = src_prefix_match.group(1) + '.'
                        for full_id in snippet_map:
                            if full_id.startswith(src_prefix) and full_id not in seen:
                                snippet_ids.append(full_id)
                                seen.add(full_id)
                                matched = True
                                logger.debug(f"[CITATIONS] Sibling fallback: [{item}] → {full_id}")
                                break

            # Strategy 5 (2b): LLM fallback — for single-occurrence unresolvable references,
            # ask a small model which available snippet best matches the verbal handle.
            if not matched and snippet_map:
                ref_count = answer_str.count(item)
                if ref_count <= 2:  # Single or double occurrence — worth the small LLM call
                    resolved = await self._llm_resolve_snippet(item, snippet_map, query=query)
                    if resolved and resolved not in seen:
                        snippet_ids.append(resolved)
                        seen.add(resolved)
                        matched = True
                        logger.debug(f"[CITATIONS] LLM fallback resolved: [{item}] → {resolved}")

            # Track failures for logging
            if not matched:
                failed_items.append(item)

        if failed_items:
            logger.warning(f"[CITATIONS] Could not match {len(failed_items)} items: {failed_items}")

            # 2c: Log structured resolution failure record for systematic diagnosis.
            try:
                failure_record = {
                    "query": (query or '')[:200],
                    "failed_references": failed_items,
                    "available_snippet_ids": list(snippet_map.keys()),
                    "available_handles": {h: sid for h, sid in handle_to_id.items()},
                    "available_short_ids": {k: v for k, v in short_id_map.items()},
                    "snippet_count": len(snippets),
                    "resolution_strategies_tried": ["short_id", "direct_id", "fuzzy_handle", "super_fuzzy", "snippet_id", "prefix_id", "verbal_handle", "sibling", "llm"],
                }
                failure_json = json.dumps(failure_record, indent=2)

                # Prefer the caller-supplied debug_dir; fall back to /tmp or local test_results
                _debug_base = debug_dir
                if not _debug_base:
                    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
                        _debug_base = '/tmp'
                    else:
                        _debug_base = os.path.join(os.path.dirname(__file__), 'test_results')

                failure_dir = os.path.join(_debug_base, 'snippet_resolution_failures')
                os.makedirs(failure_dir, exist_ok=True)
                slug = _query_slug(query)
                failure_file = os.path.join(failure_dir, f'{slug}.json')
                with open(failure_file, 'w', encoding='utf-8') as f:
                    f.write(failure_json)
                logger.debug(f"[CITATIONS] Resolution failure log saved to {failure_file}")
            except Exception as e:
                logger.debug(f"[CITATIONS] Could not save resolution failure log: {e}")

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

            # Debug: Log if _code is missing (fallback to snippet ID order works fine)
            missing_code = sum(1 for s in url_snippets if not s.get('_code'))
            if missing_code > 0:
                logger.debug(f"[CITATIONS] {missing_code}/{len(url_snippets)} snippets missing _code field, using snippet ID order")

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

            # Check if ANY snippet from this URL is from memory/cache/live-fetch
            # (in case of mixed sources for same URL)
            any_from_memory = any(s.get('_from_memory') for s in url_snippets)
            any_from_citation_recall = any(s.get('_from_citation_recall') for s in url_snippets)
            any_from_live_fetch = any(s.get('_from_live_fetch') for s in url_snippets)

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
                'c': first_snippet.get('c', 'M/O'),  # Source-level classification
                # Preserve memory/cache tracking flags for analytics (any snippet match)
                '_from_memory': any_from_memory,
                '_from_citation_recall': any_from_citation_recall,
                '_from_live_fetch': any_from_live_fetch
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

        # Sort and deduplicate consecutive citation groups (e.g., [3][1][2] -> [1][2][3])
        def sort_and_dedupe_citations(match):
            group = match.group(0)
            numbers = re.findall(r'\[(\d+)\]', group)
            unique_sorted = sorted(set(int(n) for n in numbers))
            return ''.join(f'[{n}]' for n in unique_sorted)

        # Match groups of consecutive citations with optional whitespace between them
        answer_str = re.sub(r'\[\d+\](?:\s*\[\d+\])+', sort_and_dedupe_citations, answer_str)

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
