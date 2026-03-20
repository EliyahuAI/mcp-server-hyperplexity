
import asyncio
import logging

logger = logging.getLogger(__name__)

# Models that should NOT get a liveness ping (search/agentic flows; always-on or not worth pinging)
_SKIP_LIVENESS_PREFIXES = ('sonar', 'the-clone')


def should_liveness_ping(model: str) -> bool:
    """Return True if this model should be checked via liveness ping mid-call."""
    return not any(model.lower().startswith(p) for p in _SKIP_LIVENESS_PREFIXES)


async def liveness_guard(main_coro, ping_fn, timeout_s: float, model: str):
    """
    Wrap any provider call with a mid-call liveness probe.

    Fires ping_fn() at 20% of timeout_s. If the probe raises (unrecoverable
    failure), cancels main_coro and raises [LIVENESS_CANCELLED].

    Args:
        main_coro:  Unawaited coroutine that makes the actual provider call.
        ping_fn:    async callable() -> None  (raises on failure; return ignored).
        timeout_s:  Full call timeout in seconds (ping fires at 20% of this).
        model:      Internal model name — used in log messages only.

    Returns:
        Whatever main_coro returns.

    Raises:
        Exception with [LIVENESS_CANCELLED] prefix when our probe fails.
        asyncio.CancelledError when cancelled externally (propagated, not wrapped).
    """
    _cancelled_by_ping = False
    main_task = asyncio.ensure_future(main_coro)

    async def _delayed_ping():
        nonlocal _cancelled_by_ping
        await asyncio.sleep(timeout_s * 0.2)
        if main_task.done():
            return
        logger.info(f"[LIVENESS] Pinging {model} at {timeout_s * 0.2:.0f}s elapsed...")
        try:
            await ping_fn()
            logger.info(f"[LIVENESS] {model} is alive")
        except Exception as e:
            logger.warning(f"[LIVENESS] {model} unhealthy ({e}) — cancelling call")
            _cancelled_by_ping = True
            main_task.cancel()

    ping_task = asyncio.ensure_future(_delayed_ping())
    try:
        result = await main_task
    except asyncio.CancelledError:
        if not _cancelled_by_ping:
            raise  # propagate external cancellations — do NOT wrap as LIVENESS_CANCELLED
        raise Exception(
            f"[LIVENESS_CANCELLED] {model} cancelled at {timeout_s * 0.2:.0f}s — endpoint unresponsive"
        )
    finally:
        if not ping_task.done():
            ping_task.cancel()
            try:
                await ping_task  # wait for clean shutdown; suppress CancelledError
            except (asyncio.CancelledError, Exception):
                pass
    return result
