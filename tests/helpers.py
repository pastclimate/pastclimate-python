"""Test doubles: a scripted transport and canned API bodies."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from pastclimate import HTTPRequest, HTTPResponse

KEY = "pc_test_key_not_real"


def json_response(
    body: Any,
    status: int = 200,
    headers: Optional[Dict[str, str]] = None,
) -> HTTPResponse:
    merged = {"content-type": "application/json; charset=utf-8"}
    merged.update(headers or {})
    return HTTPResponse(status=status, headers=merged, body=json.dumps(body).encode("utf-8"))


def error_response(
    code: str,
    status: int,
    message: str = "Something is wrong.",
    headers: Optional[Dict[str, str]] = None,
) -> HTTPResponse:
    body = {
        "error": {
            "code": code,
            "message": message,
            "docs_url": "https://developer.pastclimate.com/api/getting-started/errors/#" + code,
        }
    }
    return json_response(body, status=status, headers=headers)


class FakeTransport:
    """Returns scripted answers in order and records every request.

    An item that is an Exception instance is raised instead of returned. When
    the script runs out, the last item repeats.
    """

    def __init__(self, *script: Union[HTTPResponse, BaseException]) -> None:
        self.script: List[Union[HTTPResponse, BaseException]] = list(script)
        self.requests: List[HTTPRequest] = []

    def __call__(self, request: HTTPRequest) -> HTTPResponse:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.script) - 1)
        item = self.script[index]
        if isinstance(item, BaseException):
            raise item
        return item


class Sleeps:
    """Records the waits the client asks for instead of sleeping."""

    def __init__(self) -> None:
        self.calls: List[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


LOCATION = {
    "id": "gb/london",
    "name": "London",
    "country": "gb",
    "lat": 51.5,
    "lon": -0.25,
    "timezone": "Europe/London",
}

UNITS_METRIC = {
    "system": "metric",
    "temperature": "C",
    "precipitation": "mm",
    "wind_speed": "m/s",
    "pressure": "hPa",
}

RATE_HEADERS = {
    "ratelimit-limit": "60",
    "ratelimit-remaining": "59",
    "ratelimit-reset": "42",
    "x-credits-used": "2",
    "x-credits-remaining": "998",
}


def envelope(data: Any, meta: Optional[Dict[str, Any]] = None, location: Any = LOCATION) -> Dict[str, Any]:
    base: Dict[str, Any] = {"credits": 2, "credits_remaining": 998, "methodology_version": "1.0.0"}
    base.update(meta or {})
    return {"location": location, "data": data, "meta": base}


def ok(body: Dict[str, Any]) -> HTTPResponse:
    return json_response(body, headers=RATE_HEADERS)


DAILY_ROW = {
    "date": "2024-01-01",
    "daily_avg_temp": 5.1,
    "daily_min_temp": 2.0,
    "daily_max_temp": 8.2,
    "daily_total_rain": 0.4,
    "daily_avg_wind": 3.3,
    "daily_avg_cloud_percent": 80,
    "rain_flag": False,
}

HOURLY_ROW = {
    "timestamp_utc": "2024-01-15T00:00:00Z",
    "temperature": 4.0,
    "feels_like_temperature": 1.5,
    "dewpoint": 2.0,
    "precipitation": 0.0,
    "wind_speed": 4.1,
    "wind_direction_deg": 220,
    "relative_humidity_percent": 88.5,
    "pressure": 1012.3,
    "cloud_cover_percent": 90,
    "solar_radiation_kwh_m2": 0.0,
}

MONTHLY_ROW = {
    "year": 2024,
    "month": 1,
    "monthly_avg_temp": 5.0,
    "monthly_min_temp": -2.0,
    "monthly_max_temp": 12.0,
    "monthly_total_rain": 60.1,
    "monthly_avg_wind": 4.0,
    "monthly_avg_pressure": 1010.0,
    "monthly_avg_cloud_percent": 70.2,
    "monthly_total_solar_j_m2": 123456.0,
    "rainy_days": 12,
    "heavy_rain_days": 1,
    "extreme_heat_days": 0,
    "extreme_cold_days": 2,
    "hours": 744,
    "days": 31,
}

YEARLY_ROW = {
    "year": 2023,
    "yearly_avg_temp": 11.0,
    "yearly_min_temp": -5.0,
    "yearly_max_temp": 33.0,
    "yearly_total_rain": 700.5,
    "yearly_avg_wind": 4.2,
    "yearly_avg_pressure": 1012.0,
    "yearly_avg_cloud_percent": 65.0,
    "yearly_total_solar_j_m2": 4.5e9,
    "rainy_days": 140,
    "heavy_rain_days": 6,
    "extreme_heat_days": 0,
    "extreme_cold_days": 3,
    "hours": 8760,
    "days": 365,
    "months": 12,
}

NORMALS_DATA = {
    "monthly": [
        {
            "month": 7,
            "avg_temp": 18.5,
            "min_temp": 13.0,
            "max_temp": 24.0,
            "total_rain": 45.0,
            "rainy_days": 8.5,
            "avg_wind": 3.9,
            "avg_cloud_pct": 60.0,
            "avg_solar_kwh_m2": 5.1,
            "years_covered": 30,
            "avg_humidity_pct": None,
        }
    ],
    "day_of_year": [
        {"md": "07-01", "avg_temp": 18.0, "min_temp": 12.5, "max_temp": 23.5, "rain_prob": 0.31},
        {"md": "07-02", "avg_temp": 18.2, "min_temp": 12.7, "max_temp": 23.7, "rain_prob": 0.29},
    ],
}

RECORDS_DATA = [
    {"metric": "hottest_day", "value": 38.1, "unit": "C", "occurred_on": "2022-07-19"},
    {"metric": "coldest_day", "value": -9.0, "unit": "C", "occurred_on": "2010-12-20"},
    {"metric": "wettest_day", "value": 70.2, "unit": "mm", "occurred_on": "2021-07-12"},
    {"metric": "windiest_day", "value": 15.0, "unit": "m/s", "occurred_on": None},
]

ME_DATA = {
    "plan": {
        "id": "free",
        "name": "Free",
        "commercial_use": False,
        "attribution_link_required": True,
        "hourly_max_days_per_call": 3,
        "hourly_max_age_months": 18,
    },
    "key": {"spend_order": "plan_first"},
    "credits": {
        "one_time_limit": 1234,
        "one_time_remaining": 1000,
        "used_all_time": 234,
        "monthly_limit": None,
        "used_this_month": 234,
        "remaining_this_month": None,
        "month_resets_at": None,
        "daily_cap": None,
        "used_today": 12,
        "remaining_today": None,
        "day_resets_at": "2026-11-15T00:00:00.000Z",
    },
    "rate_limit": {"per_minute": 17, "remaining": 16},
}
