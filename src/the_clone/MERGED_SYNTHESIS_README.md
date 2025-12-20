# Merged Synthesis Approach - EXPERIMENTAL

⚠️ **THIS CODE IS NOT IN PRODUCTION USE** ⚠️

**Status**: Experimental implementation - Fully tested and functional
**Decision**: Sticking with traditional approach for production
**Purpose**: Available for future use if API call reduction becomes priority

---

## What Is This?

An alternative synthesis approach that merges snippet extraction and synthesis into a single LLM call.

**Traditional** (Current Production):
```
Source 1 → Extract (LLM call) → Snippets
Source 2 → Extract (LLM call) → Snippets
Source N → Extract (LLM call) → Snippets
All snippets → Synthesize (LLM call) → Answer

Total: N+1 LLM calls
```

**Merged** (This Code):
```
All sources → Label → Single Synthesize (LLM call) → Answer

Total: 1 LLM call
```

---

## Files in This Implementation

### ⚠️ EXPERIMENTAL FILES (Not Used in Production)

**Core Implementation**:
- `merged_synthesizer.py` - Main synthesizer with code resolution
- `merged_synthesis_schemas.py` - Schemas for output format
- `prompts/merged_synthesis_code.md` - Synthesis prompt with citations

**Tests**:
- `tests/test_merged_synthesis.py` - Unit tests
- `tests/test_merged_vs_traditional.py` - Side-by-side comparison

**Documentation**:
- `MERGED_SYNTHESIS_EXPERIMENTAL.md` - Full technical documentation
- `test_results/COMPREHENSIVE_FINAL_REPORT.md` - Performance analysis

### ✅ PRODUCTION FILES (Active)

**Current System** (Traditional approach):
- `snippet_extractor_streamlined.py` - Per-source extraction
- `unified_synthesizer.py` - Synthesis from snippets
- `prompts/snippet_extraction_code_compressed.md` - Extraction prompt
- `prompts/snippet_synthesis.md` - Synthesis prompt

---

## Validated Performance

### ✅ Advantages

| Metric | Improvement |
|--------|-------------|
| LLM Calls | **-85.7%** (7 → 1) |
| Total Tokens | **-15-20%** |
| Code Resolution | **99-100%** |
| API Requests | **-85.7%** |

### ⚠️ Trade-offs

| Metric | Impact |
|--------|--------|
| Cost | **+10%** (output token heavy) |
| Time | **+50-90%** (slower) |
| Complexity | Higher post-processing |

---

## When to Consider Using This

### ✅ Good Fit:
- **Rate limits are strict** (need fewer API calls)
- **Cost per API call** (billed per request, not tokens)
- **Batch processing** (process many sources at once)
- **Token limits** (need to reduce total tokens)
- **Simpler deployment** (fewer integration points)

### ❌ Not Good Fit:
- **Speed is critical** (real-time applications)
- **Cost minimization** (traditional is ~10% cheaper)
- **Parallel processing** (can't parallelize single call)
- **Proven stability needed** (traditional is battle-tested)

---

## How It Works

### 1. Source Labeling (Pre-processing)

Each source gets labeled with source-prefixed codes:

```
Source 1: https://example.com
Available codes: `S1:1.0-1.15 (16 codes), `S1:2.0-2.8 (9 codes) - Total: 25 codes

## Heading `S1:1.0

First sentence. `S1:1.1
Second sentence. `S1:1.2
Third sentence. `S1:1.3
```

### 2. Single Synthesis Call

Model synthesizes answer with inline code citations:

```json
{
  "comparison": {
    "feature_a": "Released October 2024 {`S1:1.1, 0.95, P}",
    "feature_b": "Architecture uses {`S1:2.3-2.5, 0.85, D} and {`S2:3.1, 0.95, P}"
  }
}
```

### 3. Code Resolution (Post-processing)

Citations are extracted and resolved:

```
{`S1:1.1, 0.95, P} → "Released October 2024" → [1]
{`S2:3.1, 0.95, P} → "Uses transformer architecture" → [2]
```

---

## Citation Format

### Code Format
```
{`S#:section.sentence, p_score, reason}

Examples:
- {`S1:1.1, 0.95, P} - Single sentence from source 1
- {`S2:2.3-2.5, 0.85, D} - Range from source 2
- {`S3:1.5 [of the system], 0.85, A} - With context annotation
```

### P-Scores (Validation Quality)
```
0.95 - PRIMARY (official docs)
0.85 - DOCUMENTED/ATTRIBUTED
0.65 - OK (no red flags)
0.50 - UNSOURCED
0.30 - PROMOTIONAL/STALE
0.05 - SLOP/CONTRADICTED
```

### Reason Codes
```
P  = PRIMARY (official source)
D  = DOCUMENTED (peer reviewed, methods shown)
A  = ATTRIBUTED (believable named source)
O  = OK (no red flags)
U  = UNSOURCED (just statements)
PR = PROMOTIONAL (bias)
S  = STALE (out of date)
SL = SLOP (AI-generated SEO)
C  = CONTRADICTED (known false)
```

---

## Integration (If Needed in Future)

### Step 1: Add Config Flag

In `config.json`:
```json
{
  "experimental_features": {
    "use_merged_synthesis": false
  }
}
```

### Step 2: Conditional Logic

In main clone:
```python
if config.get('experimental_features', {}).get('use_merged_synthesis', False):
    from the_clone.merged_synthesizer import MergedSynthesizer
    synthesizer = MergedSynthesizer(ai_client)
    result = await synthesizer.evaluate_and_synthesize(
        query=query,
        sources=sources,  # Pass sources, not snippets
        context=context,
        iteration=iteration,
        is_last_iteration=is_last_iteration
    )
else:
    # Traditional approach (current production)
    # ... existing code ...
```

### Step 3: Monitor Metrics

Track and log:
- Code resolution rate (should stay >95%)
- Failed resolutions (investigate if >5%)
- Cost comparison vs traditional
- Time comparison vs traditional

---

## Test Results

**Full metrics available in**:
- `test_results/COMPREHENSIVE_FINAL_REPORT.md`
- `test_results/comparison_*/comparison.json`

**Validated on**:
- Model comparisons (Claude vs GPT-4o)
- Feature queries (Python 3.13)
- Real Perplexity searches
- Multiple source counts (3-6 sources)

**Metrics tracked**:
- Time (extraction, synthesis, total)
- Cost (input/output tokens, total cost)
- Resolution rate (codes found/resolved/failed)
- Failed resolutions (with diagnostics)

---

## Known Issues & Limitations

### 1. Cross-Section Ranges Not Supported
```
Code: `S1:H7.4-H8.0
Error: CodeResolver doesn't support ranges across sections
Impact: ~1-2% of codes may fail
Solution: Enhance CodeResolver (future work)
```

### 2. Occasional Hallucinated Codes
```
Example: Model cites `S4:16.1 when only `S4:1.0-15.5 exist
Frequency: ~1-2% of codes
Mitigation: Code count hints reduce this significantly
```

### 3. Slower Processing
```
Reason: Single large synthesis call vs parallel extractions
Impact: 50-90% slower total time
When it matters: Real-time applications
```

---

## Maintenance Notes

**These files are isolated and do NOT affect production**:
- No imports in main clone
- No config references
- Completely separate code path
- Only used if explicitly imported

**To activate** (not recommended currently):
- Add config flag
- Import MergedSynthesizer
- Use conditional logic
- Monitor closely

**Why keeping it**: Valuable for future if:
- API rate limits become stricter
- Cost per API call model changes
- Token budgets become tighter
- Need simpler deployment architecture

---

**Remember**: This is EXPERIMENTAL code. Production uses traditional approach for speed and stability.
