"""
HyperplexityClient — thin requests.Session wrapper for the Hyperplexity external API.

External API:  https://api.hyperplexity.ai/v1
Auth:          Authorization: Bearer <hpx_live_...>
Response:      {"success": true, "data": {...}}
Error:         {"success": false, "error": {"code": "...", "message": "..."}}

Usage:
    from client import get_client
    client = get_client()          # reads HYPERPLEXITY_API_KEY from env
    data = client.get("/account/balance")
    # → {"balance_usd": 42.50, "email": "you@example.com"}   (data: envelope unwrapped)
"""

from __future__ import annotations

import os
import requests

BASE_URL = "https://api.hyperplexity.ai/v1"


class HyperplexityClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def _url(self, path: str) -> str:
        return self.base_url + path

    def _check(self, resp: requests.Response) -> dict:
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, dict) and body.get("success") is False:
            err = body.get("error") or body.get("message") or "API returned success=false"
            if isinstance(err, dict):
                code = err.get("code", "")
                msg  = err.get("message", "unknown error")
                raise RuntimeError(f"Hyperplexity API error [{code}]: {msg}")
            raise RuntimeError(f"Hyperplexity API error: {err}")
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
            "Add it to your Claude Desktop MCP config or export it in your shell."
        )
    return HyperplexityClient(api_key)
