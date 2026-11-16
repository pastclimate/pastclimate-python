"""The PastClimate API client."""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
import random
import re
import time
import urllib.parse
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Mapping,
    Optional,
    Type,
    TypeVar,
    Union,
    overload,
)

from . import models as m
from ._http import (
    TRANSPORT_ERRORS,
    HTTPRequest,
    HTTPResponse,
    Transport,
    is_timeout,
    parse_rate_limit,
    parse_retry_after,
    urllib_transport,
)
from ._version import __version__
from .errors import (
    ApiError,
    AuthenticationError,
    InvalidRequestError,
    NetworkError,
    error_from_response,
)

__all__ = ["Client", "DEFAULT_BASE_URL", "API_KEY_ENV_VAR", "USER_AGENT"]

DEFAULT_BASE_URL = "https://api.pastclimate.com"
API_KEY_ENV_VAR = "PASTCLIMATE_API_KEY"
USER_AGENT = "pastclimate-python/" + __version__

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_RETRY_AFTER = 60.0

_BACKOFF_BASE = 0.5
_BACKOFF_MAX = 8.0

DateLike = Union[str, _dt.date]

_D = TypeVar("_D")
_M = TypeVar("_M", bound=m.Meta)


def _invalid(message: str) -> InvalidRequestError:
    """An error the SDK raises itself, before sending anything."""
    return InvalidRequestError(message, status=0, code="invalid_request")


def _date(name: str, value: Any) -> str:
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise _invalid("{} must be a date (datetime.date or a YYYY-MM-DD string).".format(name))


def _coord(name: str, value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _invalid("{} must be a finite number.".format(name))
    text = "{:.6f}".format(value).rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _int(name: str, value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid("{} must be a whole number.".format(name))
    return str(value)


def _place(
    location: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    country: Optional[str],
) -> Dict[str, Optional[str]]:
    """The ``location`` and ``country`` parameters.

    Either a location id (``"gb/london"``), or ``lat`` and ``lon`` with the
    ``country`` the point is in.
    """
    if location is not None:
        if lat is not None or lon is not None:
            raise _invalid("Pass either location or lat and lon, not both.")
        if not isinstance(location, str) or not location.strip():
            raise _invalid("location must be a non-empty string such as 'gb/london'.")
        return {"location": location.strip(), "country": country}
    if lat is None or lon is None:
        raise _invalid("Pass location (an id such as 'gb/london') or both lat and lon.")
    if not country:
        raise _invalid("country is required when the place is given as lat and lon.")
    return {"location": "{},{}".format(_coord("lat", lat), _coord("lon", lon)), "country": country}


def _header_int(headers: Mapping[str, str], name: str) -> Optional[int]:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _encode(query: Mapping[str, Optional[str]]) -> str:
    pairs = [(k, v) for k, v in query.items() if v is not None]
    return urllib.parse.urlencode(pairs, quote_via=urllib.parse.quote)


class Client:
    """Client for the PastClimate API.

    Args:
        api_key: Your API key. When omitted, the ``PASTCLIMATE_API_KEY``
            environment variable is used.
        base_url: API root. Defaults to ``https://api.pastclimate.com``.
        timeout: Seconds to wait for each HTTP attempt (default 30). ``None``
            waits forever.
        max_retries: How many times to retry a failed attempt (default 2).
            Retried: 429 that has ``Retry-After``, 5xx, and network errors.
            Never retried: any other 4xx, and 429 without ``Retry-After``.
        max_retry_after: Longest ``Retry-After`` (seconds, default 60) the
            client will sleep through. A longer wait is raised to you instead,
            for example the wait until midnight UTC after the daily request
            limit.
        transport: A callable ``(HTTPRequest) -> HTTPResponse`` replacing the
            built-in ``urllib`` transport. It should raise ``OSError`` (such as
            ``ConnectionError`` or ``TimeoutError``) when no answer arrives.
        sleep: Replacement for ``time.sleep`` (mainly for tests).

    Raises:
        AuthenticationError: no key was given and the environment has none.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: Optional[float] = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_retry_after: float = DEFAULT_MAX_RETRY_AFTER,
        transport: Optional[Transport] = None,
        sleep: Optional[Callable[[float], None]] = None,
    ) -> None:
        key = (api_key or os.environ.get(API_KEY_ENV_VAR) or "").strip()
        if not key:
            raise AuthenticationError(
                "No API key. Pass api_key=... or set the {} environment variable.".format(API_KEY_ENV_VAR),
                status=0,
                code="missing_key",
            )
        if re.search(r"[\s\x00-\x1f\x7f]", key):
            raise AuthenticationError(
                "The API key contains whitespace or control characters.",
                status=0,
                code="invalid_key",
            )
        base = (base_url or "").strip().rstrip("/")
        if not re.match(r"^https?://[^/\s]+", base):
            raise _invalid("base_url must start with http:// or https://.")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise _invalid("max_retries must be a whole number, 0 or more.")
        if timeout is not None and not timeout > 0:
            raise _invalid("timeout must be positive, or None for no timeout.")
        if not max_retry_after >= 0:
            raise _invalid("max_retry_after must be 0 or more.")
        self._api_key = key
        self._base_url = base
        self._timeout = timeout
        self._max_retries = max_retries
        self._max_retry_after = float(max_retry_after)
        self._transport: Transport = transport if transport is not None else urllib_transport
        self._sleep: Callable[[float], None] = sleep if sleep is not None else time.sleep
        self._random: Callable[[], float] = random.random

    def __repr__(self) -> str:
        return "Client(base_url={!r}, timeout={!r}, max_retries={!r})".format(
            self._base_url, self._timeout, self._max_retries
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    # ------------------------------------------------------------------
    # Locations (free; they still count toward your request limits)
    # ------------------------------------------------------------------

    def search_locations(
        self, q: str, *, country: Optional[str] = None
    ) -> m.ApiResponse[List[m.LocationSearchResult], m.SearchMeta]:
        """Search places by the start of a name (``GET /v1/locations/search``)."""
        if not isinstance(q, str) or not q.strip():
            raise _invalid("q must be a non-empty string.")
        return self._call(
            "/v1/locations/search",
            {"q": q.strip(), "country": country},
            m._list_of(m.LocationSearchResult),
            m.SearchMeta,
        )

    def nearest_location(
        self, lat: float, lon: float, country: str
    ) -> m.ApiResponse[m.NearestLocation, m.Meta]:
        """The place nearest a point, inside one country (``GET /v1/locations/nearest``)."""
        if not country:
            raise _invalid("country is required.")
        return self._call(
            "/v1/locations/nearest",
            {"lat": _coord("lat", lat), "lon": _coord("lon", lon), "country": country},
            m.NearestLocation.from_dict,
            m.Meta,
        )

    def get_location(self, location_id: str) -> m.ApiResponse[m.LocationDetail, m.Meta]:
        """One place by id, such as ``"gb/london"`` (``GET /v1/locations/{country}/{slug}``)."""
        parts = location_id.strip().split("/") if isinstance(location_id, str) else []
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise _invalid("location_id must look like 'gb/london' (country code, slash, slug).")
        path = "/v1/locations/{}/{}".format(
            urllib.parse.quote(parts[0], safe=""), urllib.parse.quote(parts[1], safe="")
        )
        return self._call(path, {}, m.LocationDetail.from_dict, m.Meta)

    # ------------------------------------------------------------------
    # Weather data
    # ------------------------------------------------------------------

    @overload
    def get_daily(
        self,
        location: Optional[str] = ...,
        *,
        start: DateLike,
        end: DateLike,
        lat: Optional[float] = ...,
        lon: Optional[float] = ...,
        country: Optional[str] = ...,
        units: Optional[m.UnitSystem] = ...,
        format: Literal["json"] = ...,
    ) -> m.ApiResponse[List[m.DailyRow], m.DailyMeta]: ...

    @overload
    def get_daily(
        self,
        location: Optional[str] = ...,
        *,
        start: DateLike,
        end: DateLike,
        lat: Optional[float] = ...,
        lon: Optional[float] = ...,
        country: Optional[str] = ...,
        units: Optional[m.UnitSystem] = ...,
        format: Literal["csv"],
    ) -> m.CsvResponse: ...

    def get_daily(
        self,
        location: Optional[str] = None,
        *,
        start: DateLike,
        end: DateLike,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        country: Optional[str] = None,
        units: Optional[m.UnitSystem] = None,
        format: m.OutputFormat = "json",
    ) -> Union[m.ApiResponse[List[m.DailyRow], m.DailyMeta], m.CsvResponse]:
        """Daily values from ``start`` to ``end`` inclusive (``GET /v1/daily``).

        Give the place as ``location="gb/london"``, or as ``lat``, ``lon`` and
        ``country``. ``format="csv"`` returns a :class:`CsvResponse`.
        """
        query = _place(location, lat, lon, country)
        query["start"] = _date("start", start)
        query["end"] = _date("end", end)
        query["units"] = units
        if format == "csv":
            return self._call_csv("/v1/daily", query)
        self._require_json(format)
        return self._call("/v1/daily", query, m._list_of(m.DailyRow), m.DailyMeta)

    @overload
    def get_hourly(
        self,
        location: Optional[str] = ...,
        *,
        date: DateLike,
        days: Optional[int] = ...,
        lat: Optional[float] = ...,
        lon: Optional[float] = ...,
        country: Optional[str] = ...,
        units: Optional[m.UnitSystem] = ...,
        format: Literal["json"] = ...,
    ) -> m.ApiResponse[List[m.HourlyRow], m.HourlyMeta]: ...

    @overload
    def get_hourly(
        self,
        location: Optional[str] = ...,
        *,
        date: DateLike,
        days: Optional[int] = ...,
        lat: Optional[float] = ...,
        lon: Optional[float] = ...,
        country: Optional[str] = ...,
        units: Optional[m.UnitSystem] = ...,
        format: Literal["csv"],
    ) -> m.CsvResponse: ...

    def get_hourly(
        self,
        location: Optional[str] = None,
        *,
        date: DateLike,
        days: Optional[int] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        country: Optional[str] = None,
        units: Optional[m.UnitSystem] = None,
        format: m.OutputFormat = "json",
    ) -> Union[m.ApiResponse[List[m.HourlyRow], m.HourlyMeta], m.CsvResponse]:
        """Hourly values for ``days`` consecutive local days from ``date`` (``GET /v1/hourly``).

        ``days`` defaults to 1 on the server. How many days one call may ask
        for depends on your plan. ``format="csv"`` returns a :class:`CsvResponse`.
        """
        query = _place(location, lat, lon, country)
        query["date"] = _date("date", date)
        if days is not None:
            query["days"] = _int("days", days)
        query["units"] = units
        if format == "csv":
            return self._call_csv("/v1/hourly", query)
        self._require_json(format)
        return self._call("/v1/hourly", query, m._list_of(m.HourlyRow), m.HourlyMeta)

    def get_monthly(
        self,
        location: Optional[str] = None,
        *,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        country: Optional[str] = None,
        units: Optional[m.UnitSystem] = None,
    ) -> m.ApiResponse[List[m.MonthlyRow], m.RowsMeta]:
        """Every month on file, oldest first (``GET /v1/monthly``)."""
        query = _place(location, lat, lon, country)
        query["units"] = units
        return self._call("/v1/monthly", query, m._list_of(m.MonthlyRow), m.RowsMeta)

    def get_yearly(
        self,
        location: Optional[str] = None,
        *,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        country: Optional[str] = None,
        units: Optional[m.UnitSystem] = None,
    ) -> m.ApiResponse[List[m.YearlyRow], m.RowsMeta]:
        """Every year on file, oldest first (``GET /v1/yearly``)."""
        query = _place(location, lat, lon, country)
        query["units"] = units
        return self._call("/v1/yearly", query, m._list_of(m.YearlyRow), m.RowsMeta)

    def get_normals(
        self,
        location: Optional[str] = None,
        *,
        month: Optional[int] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        country: Optional[str] = None,
        units: Optional[m.UnitSystem] = None,
    ) -> m.ApiResponse[m.Normals, m.NormalsMeta]:
        """Climate normals: monthly and day-of-year (``GET /v1/normals``).

        ``month`` (1 to 12) narrows both to that month.
        """
        query = _place(location, lat, lon, country)
        if month is not None:
            query["month"] = _int("month", month)
        query["units"] = units
        return self._call("/v1/normals", query, m.Normals.from_dict, m.NormalsMeta)

    def get_records(
        self,
        location: Optional[str] = None,
        *,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        country: Optional[str] = None,
        units: Optional[m.UnitSystem] = None,
    ) -> m.ApiResponse[List[m.RecordItem], m.RecordsMeta]:
        """The hottest, coldest, wettest and windiest day on file (``GET /v1/records``)."""
        query = _place(location, lat, lon, country)
        query["units"] = units
        return self._call("/v1/records", query, m._list_of(m.RecordItem), m.RecordsMeta)

    # ------------------------------------------------------------------
    # Account and coverage
    # ------------------------------------------------------------------

    def get_coverage(self, country: Optional[str] = None) -> m.ApiResponse[m.Coverage, m.Meta]:
        """Countries served, with first year and last published day (``GET /v1/coverage``)."""
        return self._call("/v1/coverage", {"country": country}, m.Coverage.from_dict, m.Meta)

    def get_me(self) -> m.ApiResponse[m.Me, m.Meta]:
        """Your plan, credit balance and limits (``GET /v1/me``)."""
        return self._call("/v1/me", {}, m.Me.from_dict, m.Meta)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _require_json(fmt: str) -> None:
        if fmt != "json":
            raise _invalid("format must be 'json' or 'csv'.")

    def _call(
        self,
        path: str,
        query: Mapping[str, Optional[str]],
        convert: Callable[[Any], _D],
        meta_cls: Type[_M],
    ) -> m.ApiResponse[_D, _M]:
        response = self._send(path, query, "application/json")
        body = self._decode(response)
        meta = meta_cls.from_dict(body.get("meta"))
        raw_location = body.get("location")
        location = m.Location.from_dict(raw_location) if isinstance(raw_location, Mapping) else None
        return m.ApiResponse(
            data=convert(body.get("data")),
            meta=meta,
            location=location,
            rate_limit=parse_rate_limit(response.headers),
            credits_used=meta.credits
            if meta.credits is not None
            else _header_int(response.headers, "x-credits-used"),
            credits_remaining=meta.credits_remaining
            if meta.credits_remaining is not None
            else _header_int(response.headers, "x-credits-remaining"),
            status_code=response.status,
            headers=dict(response.headers),
            raw=body,
        )

    def _call_csv(self, path: str, query: Dict[str, Optional[str]]) -> m.CsvResponse:
        query["format"] = "csv"
        response = self._send(path, query, "text/csv")
        return m.CsvResponse(
            text=response.body.decode("utf-8", "replace"),
            rate_limit=parse_rate_limit(response.headers),
            credits_used=_header_int(response.headers, "x-credits-used"),
            credits_remaining=_header_int(response.headers, "x-credits-remaining"),
            status_code=response.status,
            headers=dict(response.headers),
        )

    @staticmethod
    def _decode(response: HTTPResponse) -> Dict[str, Any]:
        try:
            body = json.loads(response.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            body = None
        if not isinstance(body, dict) or "data" not in body:
            raise ApiError(
                "The API answered {} with a body that is not the expected JSON envelope.".format(response.status),
                status=response.status,
                code="invalid_response",
                headers=response.headers,
            )
        return body

    def _send(self, path: str, query: Mapping[str, Optional[str]], accept: str) -> HTTPResponse:
        url = self._base_url + path
        encoded = _encode(query)
        if encoded:
            url += "?" + encoded
        request = HTTPRequest(
            method="GET",
            url=url,
            headers={
                # The key travels only in this header, never in the URL.
                "Authorization": "Bearer " + self._api_key,
                "Accept": accept,
                "User-Agent": USER_AGENT,
            },
            timeout=self._timeout,
        )
        attempt = 0
        while True:
            try:
                response = self._transport(request)
            except TRANSPORT_ERRORS as exc:
                if attempt >= self._max_retries:
                    timed_out = is_timeout(exc)
                    message = (
                        "The request timed out after {} seconds.".format(self._timeout)
                        if timed_out
                        else "Could not reach the API: {}".format(exc)
                    )
                    raise NetworkError(message, timed_out=timed_out) from exc
                self._sleep(self._backoff(attempt))
                attempt += 1
                continue
            if 200 <= response.status < 300:
                return response
            error = error_from_response(response.status, response.headers, response.body)
            delay = self._retry_delay(response, attempt)
            if delay is None or attempt >= self._max_retries:
                raise error
            self._sleep(delay)
            attempt += 1

    def _backoff(self, attempt: int) -> float:
        ceiling = min(_BACKOFF_MAX, _BACKOFF_BASE * (2**attempt))
        return ceiling * (0.5 + 0.5 * self._random())

    def _retry_delay(self, response: HTTPResponse, attempt: int) -> Optional[float]:
        """Seconds to wait before retrying this answer, or None to give up."""
        retry_after = parse_retry_after(response.headers.get("retry-after"))
        if response.status == 429:
            # No Retry-After means waiting will not help (for example the free
            # credits are gone), so never retry.
            if retry_after is None or retry_after > self._max_retry_after:
                return None
            return retry_after
        if response.status >= 500:
            if retry_after is None:
                return self._backoff(attempt)
            return retry_after if retry_after <= self._max_retry_after else None
        return None
