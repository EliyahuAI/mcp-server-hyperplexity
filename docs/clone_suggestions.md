# The-Clone: Improvement Suggestions & QC Configuration Guidance

Findings from the comprehensive benchmark run (112 runs × 8 tests, 2026-02-27).

---

## 1. Search Instigation — Default to Retrieval

**Problem:** The clone currently makes a per-cell decision about whether to retrieve or answer from parametric memory. For well-known values it believes it already knows, it skips search entirely and labels the result `[KNOWLEDGE]`. This is unauditable: the citation looks specific (`RRUFF R040024`, `Faivre-Finn et al. JTO 2021:16(5):860-867`) but has no web evidence trail behind it.

**Recommendation:** The initial decision to answer without search should be reserved for genuinely trivial common knowledge only — on the order of "how many states does the US have." Any domain-specific numeric value, citation-backed claim, or precision measurement should always trigger search, regardless of model confidence. The bar for skipping retrieval should be extremely high.

**Why:** The benchmark showed that the cells most likely to be subtly wrong (4th decimal place crystallographic parameters, subgroup vs. ITT trial values, isotope abundances) are exactly the ones the model is most confident it knows. Parametric confidence is anti-correlated with the need for auditing.

---

## 2. Snippet Resolution — Three Improvements

### 2a. Partial resolution: return all snippets from the source

When the source (URL + title) can be resolved but the specific snippet text cannot be matched back, return **all available snippets from that source** rather than dropping the citation. A source without a pinpointed snippet is still far more useful than no citation — it gives the reviewer a document to check.

### 2b. Single unresolvable snippet: use an LLM to resolve

If there is a single snippet supporting a claim that cannot be resolved through direct matching, pass it to a small LLM with the available candidate sources and ask it to identify which source the snippet most plausibly came from. This is cheap and recovers a large fraction of otherwise-lost citations.

### 2c. Log all resolution failures

Any response containing unresolved snippets — regardless of whether they were recovered by 2a or 2b — should be fully logged to:

```
debug/snippet_resolution_failures/{session_id}/{run_key}/{row_key}_{column}.json
```

Include: the raw retrieved content, the inline reference markers used, the attempted resolution steps, and the final fallback outcome. This is the data needed to diagnose and fix resolver failures systematically.

### 2d. Two-letter snippet IDs as a third anchor

Add a short two-letter ID (e.g. `XD`, `JR`, `MB`) to each snippet at retrieval time, used as a stable third anchor alongside URL and title. During the resolution phase, the model can reference snippets by this ID even if URL normalization or title matching fails. The ID travels with the snippet through the full pipeline and is included in the stored sources array.

This turns a two-point match (URL + title, both of which can degrade through encoding, redirects, or paraphrase) into a three-point match where at least one anchor is guaranteed stable.

---

## 3. QC Configuration — When to Use It

### Model selection guidance

| Use case | Recommended model | QC |
|---|---|---|
| General lookup, imprecise values, broad context | `sonar-pro` | Optional — only if errors are costly |
| Precision numeric values, specific measurements | `the-clone-flash` | Not needed (see below) |
| High-stakes precision with tolerance for cost/latency | `the-clone-claude` | Not needed |

**sonar-pro** is a strong default for most validation tasks. It always retrieves real web sources, provides broad citation coverage, and its errors tend to be visible in the citation texture — making them easier to catch in review. It works well without QC for cases where values don't need to be exact to the 4th decimal place.

**the-clone-flash** is the right choice when precision is the priority — specific numeric constants, crystallographic parameters, clinical trial endpoints. Its targeted single-source citations are highly readable when correct.

### When to add a QC layer

QC should be understood as a **model quality elevator** — it catches errors the search model made and corrects them before the result is returned. This is only valuable when the search model's raw error rate is high enough to justify the added cost and latency.

**Use QC for sonar-pro:** sonar-pro is imprecise enough that QC meaningfully improves output quality. The benchmark showed sonar-pro needed QC correction on 2/8 tests (25%) in the hardest tier. The sonar-pro + gemini combo achieved 100% on the benchmark at 1.71¢/cell — the best cost-accuracy point in the entire matrix.

**Do not use QC on top of the-clone for single-group configurations:** When there is only one search group, adding a gemini QC layer over the-clone-flash provides no meaningful accuracy benefit (benchmark delta: −0.6% after correcting the `=`-prefix scoring artifact). The clone's errors are not the kind that QC reliably catches — they are confident wrong answers that look like right answers. QC is most effective when the base model's errors are uncertain or internally inconsistent; the clone's errors have HIGH confidence and coherent-looking citations, so QC passes them through. The cost and latency of the QC layer are not justified.

**Use QC on the-clone for multi-group configurations:** When a table has two or more search groups — each running the-clone-flash independently against different column sets — a QC layer becomes valuable for a different reason: **coherence**. Each group resolves its columns in isolation and may make slightly different assumptions about the entity, time period, or population being measured. QC sees all groups' outputs together and can catch cross-group inconsistencies (e.g. an OS benefit that doesn't arithmetically follow from the two OS rates in a separate group, or a Tc that contradicts the synthesis year). This cross-group consistency check is something the search model cannot do by construction, and it's where the QC layer earns its cost.

### Summary rule

> Add QC when you need to elevate sonar-class model quality, or when the-clone is used across two or more search groups and cross-group coherence matters. Skip QC when the-clone is the search model and there is a single search group — it adds cost without reliability gain.
