"""HTTP plumbing: the transport interface, header parsing and retry timing.

Nothing here knows about PastClimate endpoints. The default transport uses only
the standard library; pass your own callable as ``Client(transport=...)`` to use
``requests``, ``httpx`` or a test double instead.
"""

from __future__ import annotations

import email.utils
import http.client
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, Mapping, Optional

__all__ = [
    "HTTPRequest",
    "HTTPResponse",
    "Transport",
    "RateLimit",
    "urllib_transport",
    "parse_retry_after",
    "parse_rate_limit",
    "TRANSPORT_ERRORS",
    "is_timeout",
]


@dataclass(frozen=True)
class HTTPRequest:
    """One outgoing request, as handed to a transport."""

    method: str
    url: str
    headers: Dict[str, str]
    timeout: Optional[float]


@dataclass(frozen=True)
class HTTPResponse:
    """One incoming answer. ``headers`` must have lower-cased names."""

    status: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""


Transport = Callable[[HTTPRequest], HTTPResponse]


@dataclass(frozen=True)
class RateLimit:
    """The ``RateLimit-*`` headers of a response. ``None`` when a header is absent."""

    limit: Optional[int] = None
    remaining: Optional[int] = None
    reset: Optional[int] = None


# Exceptions a transport may raise for "no answer arrived". urllib.error.URLError
# and socket.timeout are OSError subclasses.
TRANSPORT_ERRORS = (OSError, http.client.HTTPException)


def _to_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def parse_rate_limit(headers: Mapping[str, str]) -> RateLimit:
    return RateLimit(
        limit=_to_int(headers.get("ratelimit-limit")),
        remaining=_to_int(headers.get("ratelimit-remaining")),
        reset=_to_int(headers.get("ratelimit-reset")),
    )


def parse_retry_after(value: Optional[str], now: Optional[float] = None) -> Optional[float]:
    """Seconds to wait from a ``Retry-After`` header, or ``None`` if absent or unreadable.

    Accepts a number of seconds or an HTTP date.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        current = time.time() if now is None else now
        return max(0.0, when.timestamp() - current)
    if seconds != seconds or seconds < 0 or seconds == float("inf"):
        return None
    return seconds


def urllib_transport(request: HTTPRequest) -> HTTPResponse:
    """Default transport, built on ``urllib.request``."""
    req = urllib.request.Request(request.url, headers=request.headers, method=request.method)
    try:
        # The URL scheme is checked by Client (http or https only).
        with urllib.request.urlopen(req, timeout=request.timeout) as resp:  # noqa: S310
            return HTTPResponse(
                status=resp.status,
                headers={k.lower(): v for k, v in resp.headers.items()},
                body=resp.read(),
            )
    except urllib.error.HTTPError as exc:
        # Non-2xx answers are normal data for us, not exceptions.
        try:
            body = exc.read()
        finally:
            exc.close()
        return HTTPResponse(
            status=exc.code,
            headers={k.lower(): v for k, v in exc.headers.items()} if exc.headers else {},
            body=body,
        )


def is_timeout(exc: BaseException) -> bool:
    """True when ``exc`` (as raised by a transport) means the request timed out."""
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return True
    reason = getattr(exc, "reason", None)
    return isinstance(reason, (socket.timeout, TimeoutError))
