# Changelog - The Clone

## 2025-12-17 - Major Updates

### Schema Evolution
- **Field name change**: "response" → "answer_raw"
  - Reason: DeepSeek V3.2 strongly prefers "answer_raw" 
  - Result: Zero schema cleanup needed (was triggering Haiku fallback repeatedly)
  - Files updated: `unified_schemas.py`, `unified_synthesizer.py`

### DeepSeek Full Integration
- **Synthesis now uses DeepSeek V3.2** (previously used Claude Sonnet)
  - Config: `deepseek_variant` and `deepseek_synthesis_variant`
  - Cost reduction: 66-71% cheaper than Claude variant
  - Performance: Comparable quality, similar speed
  - Files updated: `config.json`, `config_loader.py`, `the_clone.py`

### Soft Schema Enhancement
- **soft_schema parameter** now passed to ALL components
  - Components: triage, extraction, synthesis
  - Enhanced prompt: "IMPORTANT: Use the EXACT field names specified in the schema"
  - Files updated: `the_clone.py`, `source_triage.py`, `snippet_extractor_streamlined.py`, `unified_synthesizer.py`, `ai_api_client.py`

### Citation Format - Sonar Compatible
- **New unified format** compatible with Sonar/Sonar Pro
  - Core fields (Sonar-compatible): url, title, cited_text, date, last_updated
  - Additional fields (Clone-specific): index, reliability, snippets
  - cited_text: newline-joined snippets for compatibility
  - Files updated: `unified_synthesizer.py`

### Bug Fixes
- **Fixed Python scoping issue**: Removed duplicate `import json` in `unified_synthesizer.py`
- **Fixed Vertex soft schema**: Now applies cleanup to DeepSeek format responses
- **Fixed model tier selection**: DeepSeek variants now use `model_tiers_deepseek`

### Test Suite Expansion
- **comprehensive_test.py**: Now tests 5 systems (added Claude Web Search)
- **comprehensive_schema_test.py**: NEW - Schema validation with individual question files
- **varied_complexity_test.py**: Updated to test all 5 systems
- **Report generation**: Main summary reports reference individual question files

### Documentation Updates
- **README.md**: Updated costs, added DeepSeek synthesis, added config variants, added recent improvements
- **KEY_FIXES.md**: Updated schema evolution, soft schema details, Sonar-compatible citations
- **STARTING_PROMPT.md**: Updated test commands, success criteria, performance expectations

### Performance Improvements
**Cost Comparison (Complex Query):**
- Claude variant: $0.25
- DeepSeek variant: $0.06-0.07 (71% savings)

**Schema Compliance:**
- With "response": Required Haiku cleanup
- With "answer_raw": Zero cleanup needed ✅

