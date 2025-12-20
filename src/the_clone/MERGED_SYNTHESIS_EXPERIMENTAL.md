# Merged Synthesis Approach (EXPERIMENTAL)

**Status**: Experimental - Not in production use
**Date**: December 19, 2025
**Code Location**: `merged_synthesizer.py`, `merged_synthesis_schemas.py`, `prompts/merged_synthesis_code.md`

---

## Overview

The merged synthesis approach combines snippet extraction and synthesis into a single LLM call, achieving 85.7% reduction in API requests while maintaining 99-100% citation quality.

**Current Status**: Fully functional and tested, but **NOT integrated into main clone**. Sticking with traditional approach for now.

---

## Architecture

### Traditional Approach (Current Production)
```
┌─────────────────────────────────────────────────┐
│ For each source:                                 │
│   1. Label text with codes (`S1:1.1, `S1:1.2)   │
│   2. LLM Call: Extract snippets using codes      │
│   3. Resolve codes to text                       │
│   4. Store snippets                              │
└─────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────┐
│ Synthesis:                                       │
│   1. LLM Call: Synthesize from all snippets      │
│   2. Reference snippet IDs [S1.1.0-p0.95]        │
│   3. Convert to citations [1][2]                 │
└─────────────────────────────────────────────────┘

Total: N+1 LLM calls (N sources + 1 synthesis)
```

### Merged Approach (Experimental)
```
┌─────────────────────────────────────────────────┐
│ Pre-processing:                                  │
│   1. Label ALL sources with codes                │
│   2. Add source prefixes (`S1:1.1, `S2:2.5)      │
│   3. Format with code count hints                │
└─────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────┐
│ Single LLM Call:                                 │
│   1. Synthesize from all labeled sources         │
│   2. Cite using codes {`S1:1.1, 0.95, P}         │
│   3. Include p-scores and reasons inline         │
└─────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────┐
│ Post-processing:                                 │
│   1. Extract code citations from answer          │
│   2. Resolve codes to actual text                │
│   3. Create citations [1][2]                     │
└─────────────────────────────────────────────────┘

Total: 1 LLM call (regardless of source count)
```

---

## Performance Metrics (Real Data)

### Test Results from Side-by-Side Comparison

| Metric | Traditional | Merged | Delta |
|--------|-------------|--------|-------|
| **Efficiency** | | | |
| LLM Calls | 7 | 1 | **-85.7%** ✅ |
| Total Tokens | 26,747 | 21,343 | **-20.2%** ✅ |
| API Requests | 7 | 1 | **-85.7%** ✅ |
| | | | |
| **Cost** | | | |
| Input Tokens | 23,943 | 15,953 | -33.4% ✅ |
| Output Tokens | 2,804 | 5,390 | +92.2% ⚠️ |
| Total Cost | $0.1139 | $0.1287 | **+13%** ⚠️ |
| | | | |
| **Time** | | | |
| Extraction | 7.4s | N/A | N/A |
| Synthesis | 42.3s | 96.3s | +127% ⚠️ |
| Total | 50.6s | 96.3s | **+90%** ⚠️ |
| | | | |
| **Quality** | | | |
| Citations | 5 | 5 | Same ✅ |
| Resolution | N/A | 100% | Target met ✅ |

### Why Higher Cost Despite Fewer Tokens?

**Token Distribution**:
- Traditional: 85% input / 15% output
- Merged: 75% input / 25% output

**Pricing Impact**:
- Input: $3 per million tokens
- Output: $15 per million tokens (5× more expensive)

**Result**: Merged has more expensive output tokens, offsetting total token savings.

---

## Citation Format

### Code Format in Labeled Sources
```
Source 1: https://example.com [2024-10-07, MEDIUM]
Available codes: `S1:1.0-1.15 (16 codes), `S1:2.0-2.8 (9 codes) - Total: 25 codes

## Heading `S1:1.0

First sentence. `S1:1.1
Second sentence. `S1:1.2
Third sentence. `S1:1.3
```

### Citation Format in Synthesis Output
```json
{
  "comparison": {
    "fact1": "Released October 2024 {`S1:1.1, 0.95, P}",
    "fact2": "Architecture uses {`S1:2.3-2.5, 0.85, D} with {`S2:3.1, 0.95, P}"
  }
}
```

### Resolved Citations
```
{`S1:1.1, 0.95, P} → [1] (resolved to actual text from Source 1)
{`S2:3.1, 0.95, P} → [2] (resolved to actual text from Source 2)
```

---

## Code Resolution

### Success Rate: 99-100%

**Test 1**: 106/106 codes resolved (100%)
**Test 2**: 185/187 codes resolved (98.9%)

### Failed Resolutions (Test 2)
```
1. Code: S3:7.5
   Reason: A (ATTRIBUTED)
   P-Score: 0.85
   Attempt: (empty result)
   Cause: Code doesn't exist in Source 3

2. Code: S4:16.1
   Reason: P (PRIMARY)
   P-Score: 0.95
   Attempt: (empty result)
   Cause: Code doesn't exist in Source 4
```

**Why failures occur**: Model occasionally cites beyond available sentences (e.g., `S4:16.1` when only `S4:1.0-15.5` exist)

---

## Implementation Files

### Core Components (Isolated - Not Used in Production)

1. **`merged_synthesizer.py`**
   - Main implementation
   - Labels sources with `S#:` prefixes
   - Extracts and resolves code citations
   - Tracks failed resolutions

2. **`merged_synthesis_schemas.py`**
   - Schema definitions for evaluation and synthesis modes
   - Supports custom answer schemas

3. **`prompts/merged_synthesis_code.md`**
   - Synthesis prompt with code citation format
   - Includes validation rules and examples
   - Shows available code counts

### Test Files

1. **`tests/test_merged_synthesis.py`**
   - Unit test with mock data
   - Validates basic functionality

2. **`tests/test_merged_vs_traditional.py`**
   - Side-by-side comparison
   - Full metrics: time, cost, tokens, resolutions
   - Real Perplexity searches

### Documentation

1. **`test_results/COMPREHENSIVE_FINAL_REPORT.md`**
   - Complete performance analysis
   - Trade-off analysis
   - Production recommendations

---

## When to Use Merged Synthesis

### ✅ Use Merged When:
- **Rate limits are tight** (85.7% fewer API calls)
- **Simplicity matters** (1 step vs 2)
- **Token limits are a concern** (15-20% fewer tokens)
- **Batch processing** (process all at once)
- **Cost per API call** (fewer requests = lower base costs)

### ❌ Use Traditional When:
- **Speed is critical** (50-90% faster)
- **Cost minimization** (~10% cheaper)
- **Parallel processing available** (can parallelize extractions)
- **Production stability** (proven, mature approach)
- **Real-time applications** (lower latency)

---

## Integration Guide (Future)

### If/When Integrating:

1. **Add Config Flag**:
   ```python
   config = {
       "use_merged_synthesis": False,  # Default to traditional
       "merged_synthesis_model": "claude-sonnet-4-5"
   }
   ```

2. **Conditional Logic in Main Clone**:
   ```python
   if config.get('use_merged_synthesis', False):
       synthesizer = MergedSynthesizer(ai_client)
       result = await synthesizer.evaluate_and_synthesize(...)
   else:
       # Traditional approach (current)
       extractor = SnippetExtractorStreamlined(ai_client)
       snippets = await extract_snippets(...)
       synthesizer = UnifiedSynthesizer(ai_client)
       result = await synthesizer.evaluate_and_synthesize(...)
   ```

3. **Monitor Resolution Rate**:
   - Log failed resolutions
   - Alert if resolution rate drops below 95%
   - Adjust prompt if needed

---

## Known Limitations

1. **Slower Processing** (50-90% slower total time)
   - Single large call can't be parallelized
   - More context = longer processing

2. **Slightly Higher Cost** (~10% more expensive)
   - More output tokens (detailed synthesis)
   - Output tokens are 5× more expensive

3. **Occasional Resolution Failures** (~1-2%)
   - Model may cite non-existent codes
   - Usually minor impact (98.9%+ resolution rate)

4. **Cross-Section Ranges Not Supported** (yet)
   - Codes like `S1:H7.4-H8.0` don't resolve
   - Would require CodeResolver enhancement

---

## Future Enhancements

### To Reach 100% Resolution Always:

1. **Pre-validation**: Count available codes before synthesis
2. **Two-pass validation**: Validate cited codes, re-query if needed
3. **Cross-section range support**: Update CodeResolver
4. **Stricter prompting**: Show exact available codes in prompt

### To Improve Speed:

1. **Optimize labeling**: Cache labeled sources
2. **Stream synthesis**: Use streaming API
3. **Parallel post-processing**: Resolve codes in parallel

---

## Conclusion

The merged synthesis approach is **fully functional and production-ready** with:
- ✅ 99-100% code resolution
- ✅ 85.7% fewer LLM calls
- ✅ 15-20% fewer total tokens
- ✅ Complete tracking and diagnostics

**Current decision**: Stick with traditional approach for production stability and speed.

**Future option**: Available as experimental mode when API call reduction is priority.

---

## Files Created (All Isolated)

**Production Code** (not used):
- `merged_synthesizer.py`
- `merged_synthesis_schemas.py`
- `prompts/merged_synthesis_code.md`

**Tests** (for validation):
- `tests/test_merged_synthesis.py`
- `tests/test_merged_vs_traditional.py`

**Documentation**:
- `test_results/COMPREHENSIVE_FINAL_REPORT.md`
- This file: `MERGED_SYNTHESIS_EXPERIMENTAL.md`

**All code is isolated and doesn't affect current production clone behavior.**
