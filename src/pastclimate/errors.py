"""Typed errors.

Every error the SDK raises is a :class:`PastClimateError`.

Errors that come from an HTTP answer are :class:`ApiError` and always carry the
API's ``code``, ``message``, ``docs_url`` and the HTTP ``status``. There is one
subclass per category:

======================  ====================================================
Class                   Codes
======================  ====================================================
AuthenticationError     missing_key, invalid_key, key_revoked,
                        email_not_verified, account_suspended
InvalidRequestError     invalid_request, range_too_large, key_in_query,
                        method_not_allowed, cors_not_supported
NotFoundError           location_not_found, not_published, location_blocked,
                        not_found
PlanRequiredError       plan_required
RateLimitError          rate_limited, daily_request_cap_reached
QuotaExceededError      quota_exceeded
ServerError             internal_error, api_disabled, metering_unavailable
======================  ====================================================

Anything the API adds later falls back to a class chosen by HTTP status, or to
plain :class:`ApiError`, so new codes never crash the SDK.

:class:`NetworkError` is raised when no HTTP answer arrived (connection
failure, timeout) after the retries ran out.

``status`` is ``0`` for an :class:`InvalidRequestError` (or missing-key
:class:`AuthenticationError`) the SDK raised itself before sending anything.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional, Type

from ._http import RateLimit, parse_rate_limit, parse_retry_after

__all__ = [
    "PastClimateError",
    "ApiError",
    "AuthenticationError",
    "InvalidRequestError",
    "NotFoundError",
    "PlanRequiredError",
    "RateLimitError",
    "QuotaExceededError",
    "ServerError",
    "NetworkError",
]


class PastClimateError(Exception):
    """Base class of every error raised by this package."""


class ApiError(PastClimateError):
    """The API (or the SDK, before sending) refused a request.

    Attributes:
        message: Human-readable explanation, safe to show to users.
        status: HTTP status (``0`` when the SDK refused before sending).
        code: Stable machine-readable error code. Branch on this.
        docs_url: Link to the error reference for this code, or ``None``.
        retry_after: Seconds from the ``Retry-After`` header, or ``None``.
        upgrade_url: ``X-Upgrade-URL`` header (set on 429s), or ``None``.
        rate_limit: Rate-limit headers of the response.
        headers: Response headers, lower-cased names.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int,
        code: str,
        docs_url: Optional[str] = None,
        retry_after: Optional[float] = None,
        upgrade_url: Optional[str] = None,
        rate_limit: Optional[RateLimit] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.docs_url = docs_url
        self.retry_after = retry_after
        self.upgrade_url = upgrade_url
        self.rate_limit = rate_limit if rate_limit is not None else RateLimit()
        self.headers: Dict[str, str] = dict(headers) if headers else {}

    def __str__(self) -> str:
        if self.status:
            return "{} {}: {}".format(self.status, self.code, self.message)
        return "{}: {}".format(self.code, self.message)


class AuthenticationError(ApiError):
    """No key, a bad or revoked key, or an account that cannot make calls."""


class InvalidRequestError(ApiError):
    """A parameter is missing or not valid. Fix the request; do not retry."""


class NotFoundError(ApiError):
    """Unknown location, no published data for the request, or a blocked place."""


class PlanRequiredError(ApiError):
    """The plan does not include this request. Ask for less, or upgrade."""


class RateLimitError(ApiError):
    """Too many requests (per minute or per day). See ``retry_after``."""


class QuotaExceededError(ApiError):
    """The credits are used up. On the Free plan this never recovers on its own."""


class ServerError(ApiError):
    """Something went wrong on the API side (5xx)."""


class NetworkError(PastClimateError):
    """No HTTP answer arrived: connection failure or timeout.

    The original exception is available as ``__cause__``.
    """

    def __init__(self, message: str, *, timed_out: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.timed_out = timed_out


_BY_CODE: Dict[str, Type[ApiError]] = {
    "missing_key": AuthenticationError,
    "invalid_key": AuthenticationError,
    "key_revoked": AuthenticationError,
    "email_not_verified": AuthenticationError,
    "account_suspended": AuthenticationError,
    "invalid_request": InvalidRequestError,
    "range_too_large": InvalidRequestError,
    "key_in_query": InvalidRequestError,
    "method_not_allowed": InvalidRequestError,
    "cors_not_supported": InvalidRequestError,
    "location_not_found": NotFoundError,
    "not_published": NotFoundError,
    "location_blocked": NotFoundError,
    "not_found": NotFoundError,
    "plan_required": PlanRequiredError,
    "rate_limited": RateLimitError,
    "daily_request_cap_reached": RateLimitError,
    "quota_exceeded": QuotaExceededError,
    "daily_cap_reached": QuotaExceededError,
    "internal_error": ServerError,
    "api_disabled": ServerError,
    "metering_unavailable": ServerError,
}


def _class_for(status: int, code: str) -> Type[ApiError]:
    known = _BY_CODE.get(code)
    if known is not None:
        return known
    if status >= 500:
        return ServerError
    if status == 401:
        return AuthenticationError
    if status == 404:
        return NotFoundError
    if status == 429:
        return RateLimitError
    if status in (400, 405, 422):
        return InvalidRequestError
    return ApiError


def error_from_response(status: int, headers: Mapping[str, str], body: bytes) -> ApiError:
    """Build the right :class:`ApiError` subclass from a non-2xx answer."""
    code = "unknown_error"
    message = "HTTP {}".format(status)
    docs_url: Optional[str] = None
    parsed: Any = None
    try:
        parsed = json.loads(body.decode("utf-8")) if body else None
    except (ValueError, UnicodeDecodeError):
        parsed = None
    err = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(err, dict):
        if isinstance(err.get("code"), str):
            code = err["code"]
        if isinstance(err.get("message"), str):
            message = err["message"]
        if isinstance(err.get("docs_url"), str):
            docs_url = err["docs_url"]
    elif body:
        text = body.decode("utf-8", "replace").strip()
        if text:
            message = text[:200]
    cls = _class_for(status, code)
    return cls(
        message,
        status=status,
        code=code,
        docs_url=docs_url,
        retry_after=parse_retry_after(headers.get("retry-after")),
        upgrade_url=headers.get("x-upgrade-url"),
        rate_limit=parse_rate_limit(headers),
        headers=headers,
    )
