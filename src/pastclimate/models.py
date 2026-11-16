"""Response models.

Every model is a frozen dataclass whose attribute names are the API's JSON
field names. Unknown fields the API adds later are ignored by the models but
stay available in ``ApiResponse.raw``. A field the API leaves out reads as
``None``.

Credit numbers are never computed here: read them from ``meta.credits`` and
``meta.credits_remaining`` (or ``ApiResponse.credits_used`` and
``ApiResponse.credits_remaining``).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Generic,
    List,
    Literal,
    Mapping,
    Optional,
    Type,
    TypeVar,
    cast,
)

from ._http import RateLimit

__all__ = [
    "UnitSystem",
    "OutputFormat",
    "RateLimit",
    "Units",
    "Requested",
    "Location",
    "LocationSearchResult",
    "LocationCoverage",
    "LocationDetail",
    "NearestLocation",
    "DailyRow",
    "HourlyRow",
    "MonthlyRow",
    "YearlyRow",
    "NormalsMonthlyRow",
    "NormalsDayRow",
    "Normals",
    "RecordItem",
    "CountryCoverage",
    "Coverage",
    "MePlan",
    "MeKey",
    "MeCredits",
    "MeRateLimit",
    "Me",
    "Meta",
    "SearchMeta",
    "DailyMeta",
    "HourlyMeta",
    "RowsMeta",
    "NormalsMeta",
    "RecordsMeta",
    "ApiResponse",
    "CsvResponse",
]

UnitSystem = Literal["metric", "imperial"]
OutputFormat = Literal["json", "csv"]

_T = TypeVar("_T", bound="_Model")


class _Model:
    """Builds a dataclass from a JSON object, ignoring unknown keys."""

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {}

    @classmethod
    def from_dict(cls: Type[_T], data: Optional[Mapping[str, Any]]) -> _T:
        source: Mapping[str, Any] = data if isinstance(data, Mapping) else {}
        converters = cls._converters
        kwargs: Dict[str, Any] = {}
        for f in dataclasses.fields(cast(Any, cls)):
            value = source.get(f.name)
            convert = converters.get(f.name)
            if convert is not None and value is not None:
                value = convert(value)
            kwargs[f.name] = value
        return cls(**kwargs)


def _list_of(model: Any) -> Callable[[Any], Any]:
    def convert(items: Any) -> Any:
        return [model.from_dict(item) for item in (items or [])]

    return convert


# --- shared pieces -----------------------------------------------------------


@dataclass(frozen=True)
class Units(_Model):
    """The units used for the values of a response (``meta.units``)."""

    system: Optional[str] = None
    temperature: Optional[str] = None
    precipitation: Optional[str] = None
    wind_speed: Optional[str] = None
    pressure: Optional[str] = None


@dataclass(frozen=True)
class Requested(_Model):
    """The point you asked for, when a lat,lon was snapped to a place."""

    lat: Optional[float] = None
    lon: Optional[float] = None
    distance_km: Optional[float] = None


@dataclass(frozen=True)
class Location(_Model):
    """Which place the numbers are for (the envelope's ``location``)."""

    id: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    timezone: Optional[str] = None
    requested: Optional[Requested] = None

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {"requested": Requested.from_dict}


# --- locations ---------------------------------------------------------------


@dataclass(frozen=True)
class LocationSearchResult(_Model):
    """One hit of ``search_locations``. ``lat``/``lon``/``timezone`` are None when
    ``weather_available`` is false."""

    id: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None
    population: Optional[int] = None
    weather_available: Optional[bool] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    timezone: Optional[str] = None


@dataclass(frozen=True)
class LocationCoverage(_Model):
    first_year: Optional[int] = None
    last_date: Optional[str] = None


@dataclass(frozen=True)
class LocationDetail(_Model):
    """The result of ``get_location``."""

    id: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    timezone: Optional[str] = None
    population: Optional[int] = None
    coverage: Optional[LocationCoverage] = None

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {"coverage": LocationCoverage.from_dict}


@dataclass(frozen=True)
class NearestLocation(_Model):
    """The result of ``nearest_location``."""

    id: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    timezone: Optional[str] = None
    requested: Optional[Requested] = None
    population: Optional[int] = None

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {"requested": Requested.from_dict}


# --- data rows ---------------------------------------------------------------


@dataclass(frozen=True)
class DailyRow(_Model):
    date: Optional[str] = None
    daily_avg_temp: Optional[float] = None
    daily_min_temp: Optional[float] = None
    daily_max_temp: Optional[float] = None
    daily_total_rain: Optional[float] = None
    daily_avg_wind: Optional[float] = None
    daily_avg_cloud_percent: Optional[int] = None
    rain_flag: Optional[bool] = None


@dataclass(frozen=True)
class HourlyRow(_Model):
    timestamp_utc: Optional[str] = None
    temperature: Optional[float] = None
    feels_like_temperature: Optional[float] = None
    dewpoint: Optional[float] = None
    precipitation: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    relative_humidity_percent: Optional[float] = None
    pressure: Optional[float] = None
    cloud_cover_percent: Optional[int] = None
    solar_radiation_kwh_m2: Optional[float] = None


@dataclass(frozen=True)
class MonthlyRow(_Model):
    year: Optional[int] = None
    month: Optional[int] = None
    monthly_avg_temp: Optional[float] = None
    monthly_min_temp: Optional[float] = None
    monthly_max_temp: Optional[float] = None
    monthly_total_rain: Optional[float] = None
    monthly_avg_wind: Optional[float] = None
    monthly_avg_pressure: Optional[float] = None
    monthly_avg_cloud_percent: Optional[float] = None
    monthly_total_solar_j_m2: Optional[float] = None
    rainy_days: Optional[int] = None
    heavy_rain_days: Optional[int] = None
    extreme_heat_days: Optional[int] = None
    extreme_cold_days: Optional[int] = None
    hours: Optional[int] = None
    days: Optional[int] = None


@dataclass(frozen=True)
class YearlyRow(_Model):
    year: Optional[int] = None
    yearly_avg_temp: Optional[float] = None
    yearly_min_temp: Optional[float] = None
    yearly_max_temp: Optional[float] = None
    yearly_total_rain: Optional[float] = None
    yearly_avg_wind: Optional[float] = None
    yearly_avg_pressure: Optional[float] = None
    yearly_avg_cloud_percent: Optional[float] = None
    yearly_total_solar_j_m2: Optional[float] = None
    rainy_days: Optional[int] = None
    heavy_rain_days: Optional[int] = None
    extreme_heat_days: Optional[int] = None
    extreme_cold_days: Optional[int] = None
    hours: Optional[int] = None
    days: Optional[int] = None
    months: Optional[int] = None


@dataclass(frozen=True)
class NormalsMonthlyRow(_Model):
    month: Optional[int] = None
    avg_temp: Optional[float] = None
    min_temp: Optional[float] = None
    max_temp: Optional[float] = None
    total_rain: Optional[float] = None
    rainy_days: Optional[float] = None
    avg_wind: Optional[float] = None
    avg_cloud_pct: Optional[float] = None
    avg_solar_kwh_m2: Optional[float] = None
    years_covered: Optional[int] = None
    avg_humidity_pct: Optional[float] = None


@dataclass(frozen=True)
class NormalsDayRow(_Model):
    md: Optional[str] = None
    avg_temp: Optional[float] = None
    min_temp: Optional[float] = None
    max_temp: Optional[float] = None
    rain_prob: Optional[float] = None


@dataclass(frozen=True)
class Normals(_Model):
    """The ``data`` of ``get_normals``."""

    monthly: Optional[List[NormalsMonthlyRow]] = None
    day_of_year: Optional[List[NormalsDayRow]] = None

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {
        "monthly": _list_of(NormalsMonthlyRow),
        "day_of_year": _list_of(NormalsDayRow),
    }


@dataclass(frozen=True)
class RecordItem(_Model):
    """One extreme: ``metric`` is hottest_day, coldest_day, wettest_day or windiest_day."""

    metric: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    occurred_on: Optional[str] = None


@dataclass(frozen=True)
class CountryCoverage(_Model):
    country: Optional[str] = None
    first_year: Optional[int] = None
    last_date: Optional[str] = None


@dataclass(frozen=True)
class Coverage(_Model):
    """The ``data`` of ``get_coverage``."""

    countries: Optional[List[CountryCoverage]] = None

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {"countries": _list_of(CountryCoverage)}


# --- /v1/me ------------------------------------------------------------------


@dataclass(frozen=True)
class MePlan(_Model):
    id: Optional[str] = None
    name: Optional[str] = None
    commercial_use: Optional[bool] = None
    attribution_link_required: Optional[bool] = None
    hourly_max_days_per_call: Optional[int] = None
    hourly_max_age_months: Optional[int] = None


@dataclass(frozen=True)
class MeKey(_Model):
    spend_order: Optional[str] = None


@dataclass(frozen=True)
class MeCredits(_Model):
    one_time_limit: Optional[int] = None
    one_time_remaining: Optional[int] = None
    used_all_time: Optional[int] = None
    monthly_limit: Optional[int] = None
    used_this_month: Optional[int] = None
    remaining_this_month: Optional[int] = None
    month_resets_at: Optional[str] = None
    daily_cap: Optional[int] = None  # deprecated: always None
    used_today: Optional[int] = None
    remaining_today: Optional[int] = None  # deprecated: always None
    day_resets_at: Optional[str] = None
    topup_balance: Optional[int] = None
    topup_used: Optional[int] = None


@dataclass(frozen=True)
class MeRateLimit(_Model):
    per_minute: Optional[int] = None
    remaining: Optional[int] = None


@dataclass(frozen=True)
class Me(_Model):
    """The ``data`` of ``get_me``: your plan, credit balance and limits."""

    plan: Optional[MePlan] = None
    key: Optional[MeKey] = None
    credits: Optional[MeCredits] = None
    rate_limit: Optional[MeRateLimit] = None

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {
        "plan": MePlan.from_dict,
        "key": MeKey.from_dict,
        "credits": MeCredits.from_dict,
        "rate_limit": MeRateLimit.from_dict,
    }


# --- meta --------------------------------------------------------------------


@dataclass(frozen=True)
class Meta(_Model):
    """``meta`` of every JSON response."""

    credits: Optional[int] = None
    credits_remaining: Optional[int] = None
    methodology_version: Optional[str] = None


@dataclass(frozen=True)
class SearchMeta(Meta):
    query: Optional[str] = None
    country: Optional[str] = None
    count: Optional[int] = None


@dataclass(frozen=True)
class DailyMeta(Meta):
    units: Optional[Units] = None
    start: Optional[str] = None
    end: Optional[str] = None
    days: Optional[int] = None

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {"units": Units.from_dict}


@dataclass(frozen=True)
class HourlyMeta(Meta):
    units: Optional[Units] = None
    date: Optional[str] = None
    days: Optional[int] = None
    timezone: Optional[str] = None

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {"units": Units.from_dict}


@dataclass(frozen=True)
class RowsMeta(Meta):
    """``meta`` of ``get_monthly`` and ``get_yearly``."""

    units: Optional[Units] = None
    rows: Optional[int] = None

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {"units": Units.from_dict}


@dataclass(frozen=True)
class NormalsMeta(Meta):
    units: Optional[Units] = None
    month: Optional[int] = None

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {"units": Units.from_dict}


@dataclass(frozen=True)
class RecordsMeta(Meta):
    units: Optional[Units] = None

    _converters: ClassVar[Dict[str, Callable[[Any], Any]]] = {"units": Units.from_dict}


# --- response wrappers -------------------------------------------------------

D = TypeVar("D")
M = TypeVar("M")


@dataclass(frozen=True)
class ApiResponse(Generic[D, M]):
    """A successful JSON answer.

    Attributes:
        data: The parsed ``data`` (a list of rows, or one object).
        meta: The parsed ``meta`` (credits used and remaining, units, ...).
        location: The place the numbers are for, or ``None`` for calls that are
            not about one place.
        rate_limit: ``RateLimit-*`` headers: limit, remaining, reset.
        credits_used: Credits this call used (``meta.credits``).
        credits_remaining: Credits you can still spend (``meta.credits_remaining``).
        status_code: HTTP status.
        headers: Response headers, lower-cased names.
        raw: The whole decoded JSON body, including fields this SDK does not model.
    """

    data: D
    meta: M
    location: Optional[Location]
    rate_limit: RateLimit
    credits_used: Optional[int]
    credits_remaining: Optional[int]
    status_code: int
    headers: Mapping[str, str]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class CsvResponse:
    """A successful ``format="csv"`` answer.

    CSV has no ``meta``, so credits come from the ``X-Credits-*`` headers.
    """

    text: str
    rate_limit: RateLimit
    credits_used: Optional[int]
    credits_remaining: Optional[int]
    status_code: int
    headers: Mapping[str, str]
