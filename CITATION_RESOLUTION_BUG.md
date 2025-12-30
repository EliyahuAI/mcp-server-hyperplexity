# Citation Resolution Bug - Multi-Iteration Synthesis

## Problem

When the_clone runs improvement iterations (self-assessment B/C), snippet codes from later iterations are not being resolved to numbered citations in the final answer.

## Example

**Final answer contains unresolved codes:**
```json
{
  "buffer_protocol": "The buffer protocol now has a Python-level API [flyaps_buffer-protocol_python-api, S2.19.1-p0.65].",
  "per_interpreter_gil": "PEP 684 introduces per-interpreter GIL [compare_per-interpreter-gil_cpu-cores, S2.14.3-p0.65]."
}
```

**Should be:**
```json
{
  "buffer_protocol": "The buffer protocol now has a Python-level API [5].",
  "per_interpreter_gil": "PEP 684 introduces per-interpreter GIL [8]."
}
```

## When It Happens

**Conditions:**
1. Query requires breadth=broad or depth=deep
2. First synthesis gets self-assessment **B or C** (not A/A+)
3. Clone searches for more sources (improvement iteration)
4. New snippets extracted from improvement sources
5. Re-synthesis includes both original + improvement snippets
6. **New snippet codes fail to resolve**

## Code Locations

**Snippet codes created in:**
- `src/the_clone/snippet_extractor_streamlined.py` - Creates codes like `S4.19.1-p0.65`
- Improvement iteration uses `snippet_id_prefix="S"` (was "S_fix", fixed in commit 1b75eaec)

**Citation resolution in:**
- `src/the_clone/unified_synthesizer.py:754` - `_convert_snippet_ids_to_citations()`
- Warning: `[CITATIONS] Could not match 15 items`

## Code Format

**Snippet codes:**
- Format: `S{iteration}.{source}.{section}-p{probability}`
- Example: `S2.19.1-p0.65` = Iteration 2, Source 19, Section 1, Probability 0.65
- Also includes: `[domain_keywords_topic, S2.19.1-p0.65]`

**Expected citations:**
- Format: `[1]`, `[2]`, `[3]`, etc.
- Should have matching entry in citations array

## Reproduction Steps

1. **Run the_clone with broad/deep query:**
   ```python
   from the_clone.the_clone import TheClone2Refined

   clone = TheClone2Refined()
   result = await clone.query(
       prompt="Explain Python 3.12 improvements",  # Broad/deep query
       provider="deepseek",
       debug_dir="debug/citation_bug"
   )
   ```

2. **Check self-assessment:**
   - Look for: `[CLONE] Self-assessment: B`
   - If B/C, improvement iteration will trigger

3. **Check synthesis logs:**
   ```
   [CLONE] Model suggested search terms: ['...', '...']
   [SEARCH_MANAGER] Executing 2 searches
   [BATCH EXTRACTOR] S4 (domain): 3 quotes extracted...
   [BATCH EXTRACTOR] S5 (domain): 3 quotes extracted...
   ```

4. **Check final answer for unresolved codes:**
   - Search result for: `S2.`, `S3.`, `S4.`
   - These should be `[1]`, `[2]`, etc.

5. **Check logs for matching warnings:**
   ```
   WARNING: [CITATIONS] Could not match 15 items
   ```

## Hypothesis

**Possible causes:**
1. Citation matcher regex doesn't handle multi-iteration codes correctly
2. Snippet ID format changes between iterations (unlikely - we fixed S_fix)
3. Citation array doesn't include improvement iteration sources
4. Regex pattern expects specific format that improvement snippets don't match

## Files to Investigate

1. **`src/the_clone/unified_synthesizer.py`**
   - Method: `_convert_snippet_ids_to_citations()` (line 754)
   - Check regex pattern for snippet code matching
   - Check how citations array is built

2. **`src/the_clone/snippet_extractor_streamlined.py`**
   - Verify snippet code format consistency
   - Check if improvement iteration codes match expected pattern

3. **`src/the_clone/the_clone.py`**
   - Line 1030: Improvement iteration extraction
   - Verify snippet_id_prefix is correct ("S" not "S_fix" - fixed)
   - Check if improvement snippets are added to citations array

## Test Files

**Test results with this bug:**
- `src/the_clone/test_results/query_2/result.json`
- `src/the_clone/test_results/query_3/result.json`
- Both show unresolved codes in final answer

**Debug logs:**
- `src/the_clone/test_results/query_2/FULL_LOG.md`
- `src/the_clone/test_results/query_3/FULL_LOG.md`

## Expected Behavior

**All snippet codes should be resolved:**
- Original iteration: `S1.5.2-p0.95` → `[3]`
- Improvement iteration: `S4.19.1-p0.65` → `[12]`
- Final answer should have ONLY numbered citations
- Citations array should include ALL sources (original + improvement)

## Notes

- This bug is **unrelated to the memory system** (happens with or without memory)
- Fixed `S_fix` prefix issue (commit 1b75eaec), but codes still not resolving
- Affects queries with breadth=broad or depth=deep (triggers improvement)
- DeepSeek synthesis has more citation matching issues than Claude
