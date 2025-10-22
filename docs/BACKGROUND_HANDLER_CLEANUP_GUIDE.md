# Background Handler Cleanup Guide

**Created:** October 22, 2025
**Purpose:** Guide future cleanup of background_handler.py after dual Lambda architecture stabilizes
**Status:** Planning Document

---

## Architecture Change

We've split the interface Lambda into TWO Lambdas using the same codebase:

### Interface Lambda (Lightweight)
- **Memory:** 512MB (minimal)
- **Timeout:** 30 seconds
- **Purpose:** API routing, quick responses
- **Handles:** HTTP requests only
- **Excludes:** SQS events, background_handler calls, AI operations

### Background Lambda (Heavy)
- **Memory:** 3008MB (provisioned for AI operations)
- **Timeout:** 15 minutes
- **Purpose:** Heavy processing
- **Handles:** SQS events, background processing, AI calls
- **Includes:** Full background_handler.py with all dependencies

---

## Current State (As of Dual Lambda Split)

### Interface Lambda Restrictions

**Environment Variable:** `IS_LIGHTWEIGHT_INTERFACE=true`

**Routing (interface_lambda_function.py):**
```python
if IS_LIGHTWEIGHT_INTERFACE:
    # Only allow HTTP routing
    if 'httpMethod' in event:
        from interface_lambda.handlers import http_handler
        return http_handler.handle(event, context)
    else:
        raise RuntimeError("Lightweight interface Lambda cannot process SQS or background events")
```

**Protected Modules:**
- `background_handler.py` - Throws error if imported in lightweight mode
- `ai_api_client` - Not imported in lightweight Lambda
- Heavy action handlers - Blocked in lightweight mode

### Background Lambda Full Access

**Environment Variable:** `IS_BACKGROUND_PROCESSOR=true`

**Routing:**
- ✅ SQS events → sqs_handler
- ✅ Background processing → background_handler
- ✅ HTTP (for completion callbacks) → http_handler
- ✅ All AI operations allowed

---

## Functions Marked for Future Removal

### In background_handler.py

Functions to deprecate/remove once Table Maker is stable:

#### 1. **Old Preview/Refinement Flow** (DEPRECATED)
- Location: background_handler.py (lines TBD)
- Status: DEPRECATED - Table Maker uses Independent Row Discovery now
- Removal target: After Table Maker validated in production for 1+ month
- Functions:
  - `handle_table_preview_generation()` - Old preview system
  - `handle_table_refinement()` - Old refinement loop
  - `generate_table_preview()` - Preview generation
  - `refine_table_preview()` - Refinement processing

**Deprecation Notice:**
```python
@deprecated(
    reason="Table Maker now uses Independent Row Discovery. "
           "This preview/refinement system is obsolete.",
    removal_target="2025-12-01",
    replacement="Use Table Maker conversation → execution flow"
)
def handle_table_preview_generation(...):
    logger.warning(
        "DEPRECATED: handle_table_preview_generation() is obsolete. "
        "Use Table Maker Independent Row Discovery instead."
    )
    # ... existing code ...
```

#### 2. **Legacy Metrics Building** (DEPRECATED)
- Location: Removed in recent cleanup
- Status: REMOVED (already cleaned up)
- Functions:
  - `_build_provider_metrics()` - Removed
  - `_build_token_usage_structure()` - Removed

#### 3. **Row Expansion Logic** (DEPRECATED)
- Location: finalize.py (removed in cleanup)
- Status: REMOVED (disabled with `if False:` block, then removed)
- Replacement: Independent Row Discovery with progressive escalation

---

## Heavy Dependencies to Review

### Currently in Both Lambdas (should only be in Background):

**AI/ML Libraries:**
- `anthropic` - Claude API client
- `openai` - OpenAI client (if used)
- Large model-specific packages

**Document Processing:**
- `PyMuPDF` (24.1 MB) - PDF processing
- `openpyxl` (250 KB) - Excel reading/writing
- `xlsxwriter` (175 KB) - Excel generation
- `reportlab` (4.4 MB) - PDF generation

**Async HTTP:**
- `aiohttp` (1.7 MB) - Only needed for heavy async operations
- `aioboto3` (35 KB + aiobotocore 86 KB) - Async AWS operations

### Can Stay in Interface Lambda:

**Core AWS:**
- `boto3` - S3, DynamoDB operations
- `botocore` - AWS SDK core

**Web Utilities:**
- `requests` - Simple HTTP requests
- `python-multipart` - File upload parsing

**Data:**
- `pyyaml` - Config files

---

## Cleanup Phases

### Phase 1: Dual Lambda Architecture (CURRENT)
- [x] Create lightweight interface Lambda
- [x] Create heavy background Lambda
- [x] Add runtime detection (IS_LIGHTWEIGHT_INTERFACE)
- [x] Block background_handler in lightweight mode
- [x] Strip heavy dependencies from interface requirements
- [x] Test both Lambdas work correctly

### Phase 2: Mark Deprecated Functions (Next Sprint)
- [ ] Add @deprecated decorators to old preview/refinement functions
- [ ] Add warning logs when deprecated functions called
- [ ] Update documentation to show new flows only
- [ ] Create migration guide for any remaining preview users

### Phase 3: Monitor Usage (1-2 Months)
- [ ] Track CloudWatch logs for deprecated function calls
- [ ] Verify no production usage of old flows
- [ ] Monitor Table Maker success rates
- [ ] Collect user feedback on new flow

### Phase 4: Remove Deprecated Code (After Validation)
**Target Date:** December 2025 or later

Remove these from background_handler.py:
- [ ] `handle_table_preview_generation()`
- [ ] `handle_table_refinement()`
- [ ] `generate_table_preview()`
- [ ] `refine_table_preview()`
- [ ] Any preview-related helper functions
- [ ] Old preview schemas/prompts

**Before Removal:**
1. Verify ZERO calls in CloudWatch logs (30-day window)
2. Confirm all users migrated to Table Maker
3. Create backup branch with old code
4. Document breaking changes
5. Update API documentation

---

## Testing Strategy for Dual Lambda

### Interface Lambda (Lightweight) Tests:

**Should Work:**
- ✅ File upload (CSV/Excel)
- ✅ Balance checking
- ✅ Status queries
- ✅ Session info retrieval
- ✅ WebSocket connection handling
- ✅ Quick routing decisions

**Should Fail with Clear Error:**
- ❌ SQS event processing
- ❌ background_handler.handle() calls
- ❌ AI API calls (ai_api_client)
- ❌ Heavy validation processing

### Background Lambda (Heavy) Tests:

**Should Work:**
- ✅ SQS event processing
- ✅ Background validation
- ✅ Config generation
- ✅ Table Maker execution
- ✅ Email sending
- ✅ Excel report generation
- ✅ PDF generation
- ✅ All AI operations

---

## Memory Provisioning

### Interface Lambda (Lightweight)
- **Provisioned:** 128 MB (absolute minimum)
- **Typical usage:** 64-100 MB
- **Rationale:** API routing, balance checks, file upload handlers are extremely lightweight

### Background Lambda
- **Provisioned:** 512 MB
- **Typical usage:** 256-400 MB
- **Rationale:** Background processing, AI operations, report generation

---

## Cost Impact

### Before (Single Lambda):
- All requests use 512 MB
- API routing overpays for memory (uses ~64MB, pays for 512MB)
- ~$0.0000008 per API call (wasted 87% of memory)

### After (Dual Lambda):
- API routing uses 128 MB → ~$0.0000002 per call (4x cheaper!)
- Background processing uses 512 MB (same as before)
- **Estimated savings:** 50-60% on Lambda costs (most requests are lightweight API routing)

---

## Deployment Strategy

### Same Codebase, Different Configurations

```bash
# Deploy Interface Lambda (lightweight)
python create_interface_package.py --deploy --environment prod --mode lightweight

# Deploy Background Lambda (heavy)
python create_interface_package.py --deploy --environment prod --mode background
```

**Environment Variables:**
- Interface: `IS_LIGHTWEIGHT_INTERFACE=true`, `MEMORY=512MB`
- Background: `IS_BACKGROUND_PROCESSOR=true`, `MEMORY=3008MB`

**SQS Event Source Mappings:**
- Interface: NONE (no SQS triggers)
- Background: ALL completion queues (async, standard, preview)

---

## Migration Checklist

- [x] Dual Lambda architecture implemented
- [x] Runtime detection added
- [x] Background handler protected
- [x] Dependencies stripped from interface
- [ ] Both Lambdas tested independently
- [ ] Load testing performed
- [ ] Cost monitoring enabled
- [ ] Rollback plan documented
- [ ] Old code marked deprecated
- [ ] Usage monitoring active
- [ ] Cleanup scheduled after validation period

---

## Rollback Plan

If dual Lambda architecture causes issues:

1. **Quick Rollback:** Deploy single Lambda from master branch
2. **Partial Rollback:** Keep dual Lambdas but route all events to background Lambda
3. **Gradual Rollback:** Route percentage of traffic to single Lambda

**Rollback trigger:** >5% error rate increase or >2x latency increase

---

## Success Metrics

Track these for 30 days after dual Lambda deployment:

1. **Cost Reduction:** Should see 40-50% reduction in Lambda costs
2. **Latency:** Interface Lambda should respond faster (<100ms for routing)
3. **Error Rate:** Should remain stable or improve
4. **Memory Usage:** Interface should use <512MB, Background <3008MB
5. **Cold Starts:** Lightweight Lambda should have faster cold starts (<500ms)

---

## Future Cleanup Targets

### High Priority (Remove in Phase 4)
1. Old preview/refinement flow
2. Unused Excel processing in lightweight Lambda
3. Duplicate validation logic
4. Legacy config generation paths

### Medium Priority (Review after 3 months)
1. Optimize background_handler.py (399KB is large)
2. Split background_handler into smaller modules
3. Extract email sending to separate module
4. Extract report generation to separate module

### Low Priority (Nice to have)
1. Create separate Lambda for email sending (even lighter)
2. Create separate Lambda for report generation
3. Microservice per feature (Table Maker, Validation, Config)

---

## Notes

- Keep this doc updated as cleanup progresses
- Document any deviations from the plan
- Track actual vs estimated cost savings
- Monitor CloudWatch logs for deprecated function calls
- Review quarterly and adjust timeline as needed

---

**Last Updated:** October 22, 2025
**Next Review:** November 22, 2025
**Cleanup Target:** December 2025
