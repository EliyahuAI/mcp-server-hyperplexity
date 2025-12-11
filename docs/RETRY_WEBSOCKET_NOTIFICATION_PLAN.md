# Retry WebSocket Notification Plan

## Problem

All retry logic in `src/shared/ai_api_client.py` is internal and invisible to callers. When retries happen (especially long ones like max_tokens retry), the frontend shows timeout errors because it doesn't know a retry is in progress.

## Current Retry Mechanisms (all internal to ai_api_client.py)

1. **Model fallback** - tries backup models in sequence
2. **Refusal fallback** (`[REFUSAL]`) - adds less restrictive models to try
3. **Soft schema fallback** - retries with hard schema if soft fails
4. **Max tokens retry** (`[MAX_TOKENS]`) - doubles tokens and retries (added 2025-11-25)
5. **529 overload** - tries next model when API is overloaded

## Proposed Solution

Add an optional `on_retry_callback` parameter to `call_structured_api` that gets called when retries happen.

### ai_api_client.py Changes

```python
async def call_structured_api(self, prompt: str, schema: Dict, model: Union[str, List[str]] = "claude-sonnet-4-5",
                             ..., on_retry_callback: Callable = None) -> Dict:
    """
    Args:
        ...
        on_retry_callback: Optional async callback(event_type: str, data: dict) called on retries
    """
    ...
    # Example usage in max_tokens retry:
    if "[MAX_TOKENS]" in error_msg:
        if on_retry_callback:
            await on_retry_callback("max_tokens_retry", {
                "model": current_model,
                "old_limit": current_limit,
                "new_limit": new_max_tokens
            })
        ...
```

### Event Types

| Event Type | Data | Description |
|------------|------|-------------|
| `model_fallback` | `{from_model, to_model, reason}` | Switching to backup model |
| `refusal_fallback` | `{model, fallback_models}` | Model refused, trying alternatives |
| `soft_schema_fallback` | `{model}` | Soft schema failed, trying hard schema |
| `max_tokens_retry` | `{model, old_limit, new_limit}` | Response truncated, retrying with more tokens |
| `overload_fallback` | `{model, to_model}` | 529 overload, trying next model |

### Caller Usage (config_generation/__init__.py)

```python
async def retry_callback(event_type, data):
    messages = {
        "max_tokens_retry": f"Response too large, retrying with more capacity...",
        "model_fallback": f"Trying alternative AI model...",
        "refusal_fallback": f"Trying alternative approach...",
        "soft_schema_fallback": f"Adjusting response format...",
        "overload_fallback": f"AI busy, trying backup..."
    }
    if event_type in messages:
        send_websocket_progress(session_id, messages[event_type], 55)

result = await ai_client.call_structured_api(
    prompt=prompt,
    schema=schema,
    ...,
    on_retry_callback=retry_callback
)
```

## Benefits

1. **User visibility** - Frontend knows retries are happening, no false timeout errors
2. **Clean separation** - ai_api_client stays decoupled from WebSocket
3. **Optional** - Callers that don't need notifications can ignore the parameter
4. **Extensible** - Easy to add new retry event types

## Implementation Priority

Medium - Not critical but improves UX significantly for long-running config generation.

## Related Files

- `src/shared/ai_api_client.py` - Add callback parameter and invocations
- `src/lambdas/interface/actions/config_generation/__init__.py` - Implement callback with WebSocket updates
- `src/lambdas/interface/handlers/background_handler.py` - May also benefit from retry visibility
