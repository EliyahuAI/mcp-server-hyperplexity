# Gemini 3 Flash Preview Upgrade Plan

**Goal:** Add `gemini-3-flash-preview` (AI Studio direct) and `openrouter/gemini-*` models to the system, upgrade all `gemini-2.5-flash` call sites to Gemini 3, and add configurable thinking levels via model name suffixes.

---

## New Models Being Added

| Model ID (in code) | Routes to | Pricing (in/out per M tokens) | Context / Output |
|---|---|---|---|
| `gemini-3-flash-preview` | Google AI Studio direct | ~$0.50 / $3.00 (estimate) | 1M ctx / 65K out |
| `gemini-3-flash-preview-low` | Same, budget=1024 | same | same |
| `gemini-3-flash-preview-high` | Same, budget=24576 | same | same |
| `openrouter/gemini-3-flash-preview` | OpenRouter `google/gemini-3-flash-preview` | $0.50 / $3.00 | 1M ctx / 65K out |
| `openrouter/gemini-3-flash-preview-high` | OpenRouter, budget=24576 | same | same |
| `openrouter/gemini-2.5-flash` | OpenRouter `google/gemini-2.5-flash` | $0.30 / $2.50 | 1M ctx / 65K out |
| `openrouter/gemini-2.5-flash-lite` | OpenRouter `google/gemini-2.5-flash-lite` | $0.10 / $0.40 | 1M ctx / 65K out |

**Thinking level suffix scheme** (applied to any `gemini-3-flash-preview*` model):
- `-min` → `thinkingBudget = 0` (thinking disabled)
- `-low` → `thinkingBudget = 1024`
- *(bare, no suffix)* → `thinkingBudget = 8192` (medium, default)
- `-high` → `thinkingBudget = 24576`

---

## Change A — `utils.py`

**File:** `src/shared/ai_client/utils.py`

### A1. Expand `normalize_openrouter_model()` to handle `openrouter/gemini-*`

Current implementation (after prior session):
```python
def normalize_openrouter_model(model: str) -> str:
    return _OPENROUTER_SHORTFORMS.get(model, model)
```

**Replace with:**
```python
def normalize_openrouter_model(model: str) -> str:
    """Map shortforms and openrouter/ prefixed Gemini models to their API model IDs."""
    # Resolve shortforms first (e.g., 'kimi-k2.5' → 'moonshotai/kimi-k2.5')
    model = _OPENROUTER_SHORTFORMS.get(model, model)
    # Map openrouter/gemini-X → google/gemini-X (OpenRouter's Gemini model path)
    if model.startswith('openrouter/gemini-'):
        return 'google/' + model[len('openrouter/'):]
    return model
```

### A2. Add `parse_gemini_thinking_suffix()` utility

Add this new function immediately after `normalize_openrouter_model`:
```python
# Thinking budget by suffix keyword
_GEMINI_THINKING_BUDGETS = {
    'min': 0,
    'low': 1024,
    'high': 24576,
}
_GEMINI_THINKING_DEFAULT = 8192  # bare model name = medium

def parse_gemini_thinking_suffix(model: str):
    """
    Parse thinking-level suffix from a Gemini model name.

    Suffixes: -min (0 tokens), -low (1024), bare/default (8192), -high (24576)
    Works on model names with or without a vendor prefix (e.g. 'openrouter/gemini-X').

    Returns:
        (base_model: str, thinking_budget: int | None)
        thinking_budget is None if the model is not a Gemini 3 Flash Preview model
        (no thinking config should be sent for other Gemini models).
    """
    # Only apply thinking suffix logic to gemini-3-flash-preview models
    # (other Gemini models don't support configurable thinking budget)
    is_preview = 'gemini-3-flash-preview' in model

    if not is_preview:
        return model, None

    for suffix, budget in _GEMINI_THINKING_BUDGETS.items():
        if model.endswith(f'-{suffix}'):
            base = model[:-(len(suffix) + 1)]  # strip '-{suffix}'
            return base, budget

    # No suffix → default (medium)
    return model, _GEMINI_THINKING_DEFAULT
```

---

## Change B — `providers/gemini.py`

**File:** `src/shared/ai_client/providers/gemini.py`

### B1. Import the new utility
At top of file, update the utils import line (currently imports `extract_json_from_text, validate_and_normalize_soft_schema, repair_json_with_haiku`):
```python
from ..utils import extract_json_from_text, validate_and_normalize_soft_schema, repair_json_with_haiku, parse_gemini_thinking_suffix
```

### B2. Strip suffix + inject thinking config in API call construction

Find the section in `make_single_call()` (or equivalent) where `model` is used to construct the request body. **Before** building `request_data`, add:

```python
# Parse thinking suffix and get effective model name + budget
effective_model, thinking_budget = parse_gemini_thinking_suffix(model)
# Use effective_model for the API call (suffix stripped)
```

Then when constructing `request_data` / `generation_config`:
```python
# In generationConfig section:
if thinking_budget is not None:
    generation_config['thinkingConfig'] = {'thinkingBudget': thinking_budget}
```

And use `effective_model` (not `model`) when building the API URL / request.

**Important:** The Vertex AI endpoint URL for Gemini includes the model name (e.g., `models/gemini-3-flash-preview:generateContent`). Make sure to use `effective_model` in that URL construction.

---

## Change C — `providers/openrouter.py`

**File:** `src/shared/ai_client/providers/openrouter.py`

### C1. Import the new utility
```python
from ..utils import extract_json_from_text, validate_and_normalize_soft_schema, repair_json_with_haiku, normalize_openrouter_model, parse_gemini_thinking_suffix
```

### C2. Resolve thinking suffix before API call

In `make_structured_call()`, **before** calling `normalize_openrouter_model(model)`, add:

```python
# For openrouter/gemini-3-flash-preview-* models, parse thinking suffix
effective_model, thinking_budget = parse_gemini_thinking_suffix(model)
# Now normalize (strips openrouter/ prefix → google/ for API)
api_model = normalize_openrouter_model(effective_model)
```

Use `api_model` (not `model`) as the `"model"` field in the OpenRouter API request body.

### C3. Inject thinking config for Gemini Preview models via OpenRouter

In the request body construction, add:
```python
# Pass thinking config for Gemini 3 Flash Preview models
if thinking_budget is not None:
    # OpenRouter passes thinking config via extra_body or directly in the request
    # Verify exact field name with OpenRouter docs — likely one of:
    # Option A (Google-native style):
    payload['generationConfig'] = {'thinkingConfig': {'thinkingBudget': thinking_budget}}
    # Option B (OpenRouter-specific):
    # payload['extra_body'] = {'thinking': {'type': 'enabled', 'budget_tokens': thinking_budget}}
```

**⚠️ Verify OpenRouter's exact thinking config API field name before deploying.** Test with a manual curl first:
```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemini-3-flash-preview",
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "response_format": {"type": "json_object"},
    "generationConfig": {"thinkingConfig": {"thinkingBudget": 1024}}
  }'
```

---

## Change D — `config.py`

**File:** `src/shared/ai_client/config.py`

### D1. Add timeouts for new models

In `MODEL_TIMEOUTS`, add after the `gemini-2.5-flash` entry:
```python
    # Gemini 3 Flash Preview (thinking model — needs extra time)
    'gemini-3-flash-preview': TIMEOUT_SLOW,
    'gemini-3-flash-preview-low': TIMEOUT_SLOW,
    'gemini-3-flash-preview-high': TIMEOUT_SLOW,
```

### D2. Update MODEL_HIERARCHY

Add `gemini-3-flash-preview` near the top (above deepseek, below clone variants):
```python
MODEL_HIERARCHY = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "gemini-3-flash-preview",          # NEW
    "the-clone-baseten",
    "the-clone-claude",
    "the-clone",
    "deepseek-v3.2-baseten",
    "deepseek-v3.2",
    "sonar-pro",
    "gemini-2.5-flash-lite",
    "claude-haiku-4-5",
    "sonar"
]
```

---

## Change E — `strategy_loader.py`

**File:** `src/the_clone/strategy_loader.py`

### E1. Change routing_model (initial decision model)

In `get_models_for_tier()`, line ~100:
```python
# OLD:
routing_model = 'gemini-2.5-flash-lite'
# NEW:
routing_model = 'gemini-3-flash-preview'
```

### E2. Update `get_model_with_backups()` — extraction chain

Find the `gemini-2.5-flash-lite` block (currently returns bare chain):
```python
# OLD:
if model == 'gemini-2.5-flash-lite':
    if provider == 'baseten':
        return ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'deepseek-v3.2-baseten', 'claude-haiku-4-5']
    else:
        return ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'deepseek-v3.2', 'claude-haiku-4-5']

# NEW:
if model == 'gemini-2.5-flash-lite':
    if provider == 'baseten':
        return ['gemini-2.5-flash-lite', 'openrouter/gemini-2.5-flash-lite', 'minimax/minimax-m2.5', 'claude-haiku-4-5']
    else:
        return ['gemini-2.5-flash-lite', 'openrouter/gemini-2.5-flash-lite', 'minimax/minimax-m2.5', 'claude-haiku-4-5']
```
(Both baseten and non-baseten use the same chain since OpenRouter is provider-agnostic.)

### E3. Update `get_model_with_backups()` — gemini-2.5-flash redirect

The `gemini-2.5-flash` backup chain redirects to Gemini 3:
```python
# OLD:
if model == 'gemini-2.5-flash':
    if provider == 'baseten':
        return ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'deepseek-v3.2-baseten', 'claude-sonnet-4-6']
    else:
        return ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'deepseek-v3.2', 'claude-sonnet-4-6']

# NEW (redirect — gemini-2.5-flash is superseded by gemini-3-flash-preview):
if model == 'gemini-2.5-flash':
    return ['gemini-3-flash-preview', 'openrouter/gemini-3-flash-preview']
```

### E4. Add new chain — gemini-3-flash-preview (medium thinking, initial decision)

Add after the `gemini-2.5-flash` block:
```python
# Gemini 3 Flash Preview (medium thinking) → OpenRouter fallback → Kimi K2.5
if model == 'gemini-3-flash-preview':
    return ['gemini-3-flash-preview', 'openrouter/gemini-3-flash-preview', 'moonshotai/kimi-k2.5']
```

### E5. Add new chain — gemini-3-flash-preview-high (high thinking, conversation/config/table-maker)

Add after the `gemini-3-flash-preview` block:
```python
# Gemini 3 Flash Preview HIGH thinking → OpenRouter fallback → Kimi K2.5
if model == 'gemini-3-flash-preview-high':
    return ['gemini-3-flash-preview-high', 'openrouter/gemini-3-flash-preview-high', 'moonshotai/kimi-k2.5']
```

---

## Change F — `strategy_config.json`

**File:** `src/the_clone/strategy_config.json`

### F1. findall_breadth synthesis_model

```json
// OLD:
"synthesis_model": "gemini-2.5-flash"

// NEW (in findall_breadth):
"synthesis_model": "gemini-3-flash-preview"
```

### F2. extraction synthesis_model

```json
// OLD:
"synthesis_model": "gemini-2.5-flash"

// NEW (in extraction):
"synthesis_model": "gemini-3-flash-preview"
```

---

## Change G — Action Config JSON Files

### G1. `config_settings.json`

**File:** `src/lambdas/interface/actions/config_generation/config_settings.json`

```json
// OLD:
"model": ["deepseek-v3.2", "gemini-2.5-flash", "claude-sonnet-4-5"]

// NEW:
"model": ["deepseek-v3.2", "gemini-3-flash-preview-high", "claude-sonnet-4-6"]
```

Note: also bumped `claude-sonnet-4-5` → `claude-sonnet-4-6` (current version).

### G2. `table_maker_config.json` — column_definition phase

**File:** `src/lambdas/interface/actions/table_maker/table_maker_config.json`

```json
// OLD (line ~57):
"column_definition": {
    "model": "gemini-2.5-flash",

// NEW:
"column_definition": {
    "model": "gemini-3-flash-preview-high",
```

Update the `_note_model` comment too:
```json
"_note_model": "Uses gemini-3-flash-preview-high for quality column definition (no web search needed)"
```

### G3. `reference_check_config.json` — reference_extraction

**File:** `src/lambdas/interface/actions/reference_check/reference_check_config.json`

```json
// OLD:
"reference_extraction": {
    "model": "gemini-2.5-flash",

// NEW:
"reference_extraction": {
    "model": "gemini-3-flash-preview-high",
```

### G4. `upload_interview_config.json`

**File:** `src/lambdas/interface/actions/upload_interview/upload_interview_config.json`

```json
// OLD:
"interview": {
    "model": ["gemini-2.5-flash", "claude-haiku-4-5"],

// NEW:
"interview": {
    "model": ["gemini-3-flash-preview-high", "openrouter/gemini-3-flash-preview-high", "moonshotai/kimi-k2.5"],
```

### G5. `interview.py` — default fallback chain

**File:** `src/lambdas/interface/actions/upload_interview/interview.py`, line ~42

```python
# OLD:
model = _CONFIG.get('interview', {}).get('model', ['gemini-2.5-flash-lite', 'claude-haiku-4-5'])

# NEW:
model = _CONFIG.get('interview', {}).get('model', ['gemini-3-flash-preview-high', 'openrouter/gemini-3-flash-preview-high', 'moonshotai/kimi-k2.5'])
```

---

## Change H — `unified_model_config.csv`

**File:** `src/unified_model_config.csv`

Add these rows. The exact position matters — add Gemini 3 entries **before** the existing `gemini-2.5-flash*` entries (higher priority due to lower line number in pattern matching, and they should be checked first). For `openrouter/gemini-*`, add near the other OpenRouter entries.

### H1. Gemini 3 Flash Preview (AI Studio native — `gemini` provider)

Add before the existing `gemini-2.5-flash*` block (around line 13):

```csv
# TIER 0: Gemini 3 Flash Preview - AI Studio direct (thinking model, -min/-low/-high variants)
gemini-3-flash-preview-high*,gemini,0,true,50,150,100,1.5,0.6,5,2,0.50,3.00,65535,Tier 0: Gemini 3 Flash Preview HIGH thinking (budget=24576, 65K output, 1M context)
gemini-3-flash-preview-low*,gemini,0,true,50,150,100,1.5,0.6,5,2,0.50,3.00,65535,Tier 0: Gemini 3 Flash Preview LOW thinking (budget=1024, 65K output, 1M context)
gemini-3-flash-preview-min*,gemini,0,true,50,150,100,1.5,0.6,5,2,0.50,3.00,65535,Tier 0: Gemini 3 Flash Preview thinking disabled (budget=0, 65K output, 1M context)
gemini-3-flash-preview*,gemini,0,true,50,150,100,1.5,0.6,5,2,0.50,3.00,65535,Tier 0: Gemini 3 Flash Preview MEDIUM thinking (budget=8192, 65K output, 1M context)
```

**⚠️ Important:** The `-high`, `-low`, `-min` variants MUST appear before the bare `gemini-3-flash-preview*` entry so the more specific patterns match first. The `*` wildcard might cause the bare entry to match them. Verify how the CSV pattern matching works — if needed, use exact matching (no `*`) for the suffix variants.

### H2. OpenRouter Gemini models (`openrouter` provider)

Add near the other OpenRouter entries (moonshotai, minimax, etc.):

```csv
# OpenRouter: Gemini 3 Flash Preview (routes to google/gemini-3-flash-preview)
openrouter/gemini-3-flash-preview-high*,openrouter,1,true,50,150,100,1.5,0.6,5,2,0.50,3.00,65535,OpenRouter: Gemini 3 Flash Preview HIGH thinking via OpenRouter
openrouter/gemini-3-flash-preview*,openrouter,1,true,50,150,100,1.5,0.6,5,2,0.50,3.00,65535,OpenRouter: Gemini 3 Flash Preview via OpenRouter (google/gemini-3-flash-preview)
# OpenRouter: Gemini 2.5 Flash variants
openrouter/gemini-2.5-flash-lite*,openrouter,1,true,50,180,120,1.6,0.65,5,2,0.10,0.40,65535,OpenRouter: Gemini 2.5 Flash Lite via OpenRouter (google/gemini-2.5-flash-lite)
openrouter/gemini-2.5-flash*,openrouter,1,true,50,150,100,1.5,0.6,5,2,0.30,2.50,65535,OpenRouter: Gemini 2.5 Flash via OpenRouter (google/gemini-2.5-flash)
```

Again, **`-lite`** variant must appear before the bare `gemini-2.5-flash*` entry.

---

## Summary of All gemini-2.5-flash References Being Changed

Run this after implementation to verify no stragglers:
```bash
grep -rn "gemini-2.5-flash" src/ --include="*.py" --include="*.json" \
  | grep -v "# OLD" \
  | grep -v "unified_model_config.csv" \
  | grep -v "strategy_loader.py"  # strategy_loader keeps gemini-2.5-flash-lite for extraction
```

Expected remaining references (these STAY):
- `strategy_loader.py` — `gemini-2.5-flash-lite` as primary extraction model
- `strategy_config.json` — `default_extraction_model: "gemini-2.5-flash-lite"` in all providers
- `config_generation/__init__.py` line 478: `cheap_model = 'gemini-2.5-flash-lite'` — this is a repair/cheap model, leave as-is
- `config.py` MODEL_TIMEOUTS — `'gemini-2.5-flash': TIMEOUT_SLOW` (keep for backward compat)
- `unified_model_config.csv` — existing gemini-2.5-flash rows (keep, they're still valid fallbacks)

---

## Verification Checklist

After all changes are made:

1. **Thinking suffix parsing test:**
   ```python
   from src.shared.ai_client.utils import parse_gemini_thinking_suffix
   assert parse_gemini_thinking_suffix('gemini-3-flash-preview') == ('gemini-3-flash-preview', 8192)
   assert parse_gemini_thinking_suffix('gemini-3-flash-preview-high') == ('gemini-3-flash-preview', 24576)
   assert parse_gemini_thinking_suffix('gemini-3-flash-preview-low') == ('gemini-3-flash-preview', 1024)
   assert parse_gemini_thinking_suffix('gemini-3-flash-preview-min') == ('gemini-3-flash-preview', 0)
   assert parse_gemini_thinking_suffix('openrouter/gemini-3-flash-preview-high') == ('openrouter/gemini-3-flash-preview', 24576)
   assert parse_gemini_thinking_suffix('gemini-2.5-flash-lite') == ('gemini-2.5-flash-lite', None)
   ```

2. **OpenRouter normalization test:**
   ```python
   from src.shared.ai_client.utils import normalize_openrouter_model
   assert normalize_openrouter_model('openrouter/gemini-3-flash-preview') == 'google/gemini-3-flash-preview'
   assert normalize_openrouter_model('openrouter/gemini-2.5-flash') == 'google/gemini-2.5-flash'
   assert normalize_openrouter_model('kimi-k2.5') == 'moonshotai/kimi-k2.5'
   assert normalize_openrouter_model('minimax-m2.5') == 'minimax/minimax-m2.5'
   ```

3. **Model chain test:**
   ```python
   from src.the_clone.strategy_loader import get_model_with_backups
   assert get_model_with_backups('gemini-3-flash-preview') == ['gemini-3-flash-preview', 'openrouter/gemini-3-flash-preview', 'moonshotai/kimi-k2.5']
   assert get_model_with_backups('gemini-3-flash-preview-high') == ['gemini-3-flash-preview-high', 'openrouter/gemini-3-flash-preview-high', 'moonshotai/kimi-k2.5']
   assert get_model_with_backups('gemini-2.5-flash') == ['gemini-3-flash-preview', 'openrouter/gemini-3-flash-preview']
   assert get_model_with_backups('gemini-2.5-flash-lite') == ['gemini-2.5-flash-lite', 'openrouter/gemini-2.5-flash-lite', 'minimax/minimax-m2.5', 'claude-haiku-4-5']
   ```

4. **Live call test** (after deploy):
   ```bash
   # Test AI Studio Gemini 3 Flash Preview with thinking
   python3 test_openrouter_structured.mjs  # adapt to test gemini-3-flash-preview
   ```

---

## Order of Implementation

1. **Change A** (`utils.py`) — foundation, other files depend on it
2. **Change B** (`gemini.py`) — thinking config for AI Studio calls
3. **Change C** (`openrouter.py`) — thinking config + model normalization for OpenRouter calls
4. **Change D** (`config.py`) — timeouts and hierarchy
5. **Change E** (`strategy_loader.py`) — model chains
6. **Change F** (`strategy_config.json`) — synthesis model in Clone strategies
7. **Change G** (all action config JSONs + `interview.py`) — conversation model upgrades
8. **Change H** (`unified_model_config.csv`) — cost/token tracking for new models

Run the verification checklist after each group.
