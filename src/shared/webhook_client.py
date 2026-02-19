"""
Webhook delivery client for Hyperplexity External API.

Delivers HTTP POST notifications to user-provided webhook URLs with:
- HMAC-SHA256 signature for authenticity verification
- SSRF protection (blocks private/internal IP ranges)
- Up to 3 delivery attempts with short retry delays
"""
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

# Retry delays between attempts (seconds) - short delays suitable for Lambda execution
_RETRY_DELAYS = [1, 3]   # waits before attempt 2 and 3; attempt 1 has no wait
_REQUEST_TIMEOUT_SECONDS = 10
_MAX_PAYLOAD_BYTES = 1_048_576  # 1 MB


def _is_private_address(hostname: str) -> bool:
    """Return True if hostname resolves to a private/loopback/link-local IP (SSRF guard)."""
    try:
        # Resolve hostname to IP
        addr_info = socket.getaddrinfo(hostname, None)
        for family, socktype, proto, canonname, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return True
        return False
    except Exception:
        # If we can't resolve, treat as safe (DNS failure vs SSRF is a trade-off)
        return False


def _validate_webhook_url(url: str) -> Optional[str]:
    """
    Validate webhook URL.
    Returns None if valid, or an error message string if invalid.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as e:
        return f"URL parse error: {e}"

    if parsed.scheme != 'https':
        return "webhook_url must use https://"

    if not parsed.netloc:
        return "webhook_url has no hostname"

    hostname = parsed.hostname
    if not hostname:
        return "webhook_url has no hostname"

    # Block obvious private hostnames
    if hostname.lower() in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
        return f"webhook_url hostname '{hostname}' is not allowed (SSRF protection)"

    if _is_private_address(hostname):
        return f"webhook_url hostname '{hostname}' resolves to a private IP (SSRF protection)"

    return None  # valid


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Return HMAC-SHA256 hex digest of payload_bytes using secret."""
    mac = hmac.new(secret.encode('utf-8'), payload_bytes, hashlib.sha256)
    return mac.hexdigest()


def _url_domain(url: str) -> str:
    """Return only the hostname of a URL (safe to log — avoids leaking query params/secrets)."""
    try:
        return urllib.parse.urlparse(url).hostname or "unknown"
    except Exception:
        return "unknown"


def deliver_webhook(
    webhook_url: str,
    webhook_secret: Optional[str],
    event_type: str,
    payload: dict,
) -> bool:
    """
    Deliver a webhook notification.

    Args:
        webhook_url: Target HTTPS URL.
        webhook_secret: Optional HMAC secret for X-Hyperplexity-Signature header.
        event_type: Event name, e.g. 'job.completed' or 'job.failed'.
        payload: Dict to send as JSON body.

    Returns:
        True if delivery succeeded (2xx response), False otherwise.
    """
    url_domain = _url_domain(webhook_url)

    # Validate URL
    url_error = _validate_webhook_url(webhook_url)
    if url_error:
        logger.warning(json.dumps({
            "event": "webhook_ssrf_blocked",
            "url_domain": url_domain,
        }))
        logger.error(f"[WEBHOOK] Invalid webhook URL: {url_error}")
        return False

    # Serialise payload
    try:
        body = json.dumps(payload, default=str).encode('utf-8')
    except Exception as e:
        logger.error(f"[WEBHOOK] Failed to serialise payload: {e}")
        return False

    if len(body) > _MAX_PAYLOAD_BYTES:
        logger.warning(f"[WEBHOOK] Payload too large ({len(body)} bytes), truncating not supported — skipping delivery")
        return False

    # Build headers
    timestamp_ms = int(time.time())
    headers = {
        'Content-Type': 'application/json',
        'X-Hyperplexity-Event': event_type,
        'X-Hyperplexity-Timestamp': str(timestamp_ms),
        'User-Agent': 'Hyperplexity-Webhook/1.0',
    }
    if webhook_secret:
        signature = _sign_payload(body, webhook_secret)
        headers['X-Hyperplexity-Signature'] = f"sha256={signature}"

    # Attempt delivery with retries
    for attempt in range(1, 4):  # attempts 1, 2, 3
        if attempt > 1:
            delay = _RETRY_DELAYS[attempt - 2]
            logger.info(f"[WEBHOOK] Retry {attempt}/3 — waiting {delay}s before next attempt")
            time.sleep(delay)

        try:
            req = urllib.request.Request(
                webhook_url,
                data=body,
                headers=headers,
                method='POST',
            )
            _attempt_start = time.monotonic()
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECONDS) as resp:
                status_code = resp.status
                _attempt_duration_ms = int((time.monotonic() - _attempt_start) * 1000)
                logger.info(json.dumps({
                    "event": "webhook_attempt",
                    "url_domain": url_domain,
                    "attempt": attempt,
                    "status_code": status_code,
                    "duration_ms": _attempt_duration_ms,
                }))
                if 200 <= status_code < 300:
                    logger.info(json.dumps({
                        "event": "webhook_delivered",
                        "url_domain": url_domain,
                        "attempts": attempt,
                    }))
                    return True
                else:
                    logger.warning(f"[WEBHOOK] Non-2xx response {status_code} from {url_domain} (attempt {attempt})")
        except urllib.error.HTTPError as e:
            _attempt_duration_ms = int((time.monotonic() - _attempt_start) * 1000)
            logger.info(json.dumps({
                "event": "webhook_attempt",
                "url_domain": url_domain,
                "attempt": attempt,
                "status_code": e.code,
                "duration_ms": _attempt_duration_ms,
            }))
            logger.warning(f"[WEBHOOK] HTTP error {e.code} from {url_domain} (attempt {attempt}): {e.reason}")
        except urllib.error.URLError as e:
            logger.warning(f"[WEBHOOK] URL error delivering to {url_domain} (attempt {attempt}): {e.reason}")
        except Exception as e:
            logger.warning(f"[WEBHOOK] Unexpected error delivering to {url_domain} (attempt {attempt}): {e}")

    logger.error(json.dumps({
        "event": "webhook_failed",
        "url_domain": url_domain,
        "attempts": 3,
    }))
    return False
