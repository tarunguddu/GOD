"""Dependency-free HTTP transport for LLM providers.

Uses only the standard library (``urllib``) so the agent can talk to any HTTP
LLM endpoint — hosted or local — without requiring a vendor SDK. Providers
accept an injectable transport so they can be unit-tested without a network.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable


class LLMHTTPError(Exception):
    """An HTTP-level failure from an LLM endpoint, carrying the status code."""

    def __init__(self, status: int, message: str, body: str | None = None) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status_code = status
        self.body = body


# A transport posts a JSON payload and returns the parsed JSON response.
Transport = Callable[[str, dict, dict, float], dict]


def post_json(url: str, headers: dict, payload: dict, timeout: float = 60.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        raise LLMHTTPError(exc.code, exc.reason, body) from exc
    except urllib.error.URLError as exc:
        raise LLMHTTPError(0, str(exc.reason)) from exc


def get_json(url: str, headers: dict, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        raise LLMHTTPError(exc.code, exc.reason, body) from exc
    except urllib.error.URLError as exc:
        raise LLMHTTPError(0, str(exc.reason)) from exc


def is_transient(exc: Exception) -> bool:
    """Whether an error is worth retrying (rate limit, overloaded, 5xx, network)."""
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status == 429 or status == 0 or 500 <= int(status) < 600
    name = type(exc).__name__.lower()
    return any(t in name for t in ("timeout", "connection", "ratelimit", "overloaded"))


def with_retry(fn: Callable[[], dict], max_retries: int = 3,
               sleep: Callable[[float], None] = time.sleep) -> dict:
    """Call ``fn`` with exponential backoff on transient failures."""
    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - classified by is_transient
            if not is_transient(exc) or attempt == max_retries - 1:
                raise
            last = exc
            sleep(min(2 ** attempt, 8))
    if last:  # pragma: no cover - defensive
        raise last
    raise RuntimeError("with_retry exhausted without result")  # pragma: no cover
