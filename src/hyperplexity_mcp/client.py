"""
HyperplexityClient — thin requests.Session wrapper for the Hyperplexity external API.

Auth:     Authorization: Bearer <hpx_live_...>
Response: {"success": true, "data": {...}}  — _check() unwraps the envelope automatically.
Error:    {"success": false, "error": {"code": "...", "message": "..."}}

Base URL resolution order (first one set wins):
  1. HYPERPLEXITY_API_URL env var  — set this to override (e.g. for dev)
  2. Hard-coded default            — https://api.hyperplexity.ai/v1

Usage:
    from hyperplexity_mcp.client import get_client
    client = get_client()
    data = client.get("/account/balance")
    # → {"balance_usd": 42.50, ...}   (data: envelope already unwrapped)
"""

from __future__ import annotations

import os
import requests

_DEFAULT_URL = "https://api.hyperplexity.ai/v1"


class APIError(RuntimeError):
    """Raised by HyperplexityClient._check for API-level errors.

    Attributes:
        status_code: HTTP status code from the response (0 if unknown).
    """
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


def _resolve_base_url() -> str:
    url = os.environ.get("HYPERPLEXITY_API_URL", "").rstrip("/")
    return url if url else _DEFAULT_URL


class HyperplexityClient:
    def __init__(self, api_key: str, base_url: str = ""):
        self.base_url = (base_url or _resolve_base_url()).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def _url(self, path: str) -> str:
        return self.base_url + path

    def _check(self, resp: requests.Response) -> dict:
        # Parse the body first so we can surface the real error message even on
        # non-2xx responses (previously raise_for_status() discarded the body).
        try:
            body = resp.json()
        except Exception:
            resp.raise_for_status()
            raise

        if isinstance(body, dict) and body.get("success") is False:
            err = body.get("error") or body.get("message") or "API returned success=false"
            if isinstance(err, dict):
                code = err.get("code", "")
                msg  = err.get("message", "unknown error")
                raise APIError(f"Hyperplexity API error [{code}]: {msg}", resp.status_code)
            raise APIError(f"Hyperplexity API error: {err}", resp.status_code)

        # Non-2xx with no success=false body — raise with body text for context.
        if not resp.ok:
            raise APIError(
                f"Hyperplexity API error {resp.status_code}: {resp.text[:500]}",
                resp.status_code,
            )

        # Unwrap the "data" envelope present on all external API responses.
        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body

    def get(self, path: str, params: dict | None = None) -> dict:
        resp = self.session.get(self._url(path), params=params)
        return self._check(resp)

    def post(self, path: str, json: dict | None = None) -> dict:
        resp = self.session.post(self._url(path), json=json or {})
        return self._check(resp)

    def put(self, path: str, json: dict | None = None) -> dict:
        resp = self.session.put(self._url(path), json=json or {})
        return self._check(resp)

    def put_raw(self, url: str, data: bytes, content_type: str) -> None:
        """PUT raw bytes to a presigned S3 URL.

        MUST use bare requests.put — NOT self.session.put — because presigned
        S3 URLs break if the Authorization header is included.
        """
        resp = requests.put(url, data=data, headers={"Content-Type": content_type})
        resp.raise_for_status()


def get_client() -> HyperplexityClient:
    """Build a client from the HYPERPLEXITY_API_KEY environment variable."""
    api_key = os.environ.get("HYPERPLEXITY_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "HYPERPLEXITY_API_KEY environment variable is not set. "
            "Get your API key at hyperplexity.ai/account and add it to your "
            "Claude Desktop MCP config or export it in your shell."
        )
    return HyperplexityClient(api_key)
