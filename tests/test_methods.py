"""Every operation: request shape, auth header, and parsed response."""

from __future__ import annotations

import datetime
import unittest
import urllib.parse
from typing import Dict, List, Tuple

import pastclimate
from pastclimate import Client, HTTPRequest

from .helpers import (
    DAILY_ROW,
    HOURLY_ROW,
    KEY,
    LOCATION,
    MONTHLY_ROW,
    ME_DATA,
    NORMALS_DATA,
    RECORDS_DATA,
    UNITS_METRIC,
    YEARLY_ROW,
    FakeTransport,
    envelope,
    ok,
)


def parts(request: HTTPRequest) -> Tuple[str, Dict[str, List[str]]]:
    parsed = urllib.parse.urlsplit(request.url)
    return parsed.path, urllib.parse.parse_qs(parsed.query, keep_blank_values=True)


def make(*script):
    transport = FakeTransport(*script)
    client = Client(KEY, base_url="https://api.example.test", transport=transport)
    return client, transport


class RequestBasics(unittest.TestCase):
    def test_every_request_is_a_get_with_bearer_auth_and_user_agent(self):
        client, t = make(ok(envelope({"countries": []}, location=None)))
        client.get_coverage()
        req = t.requests[0]
        self.assertEqual(req.method, "GET")
        self.assertEqual(req.headers["Authorization"], "Bearer " + KEY)
        self.assertEqual(req.headers["User-Agent"], "pastclimate-python/" + pastclimate.__version__)
        self.assertEqual(req.headers["Accept"], "application/json")
        self.assertTrue(req.url.startswith("https://api.example.test/v1/coverage"))

    def test_key_is_never_in_the_url(self):
        client, t = make(ok(envelope([DAILY_ROW], {"units": UNITS_METRIC})))
        client.get_daily("gb/london", start="2024-01-01", end="2024-01-01")
        client.get_daily(lat=51.5, lon=-0.12, country="gb", start="2024-01-01", end="2024-01-01")
        for req in t.requests:
            self.assertNotIn(KEY, req.url)
            self.assertNotIn("key", req.url.lower())
            self.assertNotIn("api_key", req.url)
            self.assertNotIn("x-api-key", {k.lower() for k in req.headers})


class Locations(unittest.TestCase):
    def test_search_locations(self):
        body = envelope(
            [
                {
                    "id": "gb/london",
                    "name": "London",
                    "country": "gb",
                    "population": 8800000,
                    "lat": 51.5,
                    "lon": -0.25,
                    "timezone": "Europe/London",
                    "weather_available": True,
                },
                {"id": "gb/lonely", "name": "Lonely", "country": "gb", "population": None, "weather_available": False},
            ],
            {"query": "lon", "country": "gb", "count": 2},
            location=None,
        )
        client, t = make(ok(body))
        resp = client.search_locations("lon", country="gb")
        path, query = parts(t.requests[0])
        self.assertEqual(path, "/v1/locations/search")
        self.assertEqual(query, {"q": ["lon"], "country": ["gb"]})
        self.assertIsNone(resp.location)
        self.assertEqual(resp.meta.count, 2)
        self.assertEqual(resp.meta.query, "lon")
        self.assertEqual(resp.data[0].id, "gb/london")
        self.assertTrue(resp.data[0].weather_available)
        self.assertFalse(resp.data[1].weather_available)
        self.assertIsNone(resp.data[1].lat)

    def test_search_without_country_omits_it(self):
        client, t = make(ok(envelope([], {"query": "par", "country": None, "count": 0}, location=None)))
        client.search_locations("par")
        self.assertEqual(parts(t.requests[0])[1], {"q": ["par"]})

    def test_search_encodes_spaces(self):
        client, t = make(ok(envelope([], {"query": "new y", "country": None, "count": 0}, location=None)))
        client.search_locations("new y")
        self.assertIn("q=new%20y", t.requests[0].url)

    def test_nearest_location(self):
        data = dict(LOCATION, population=8800000, requested={"lat": 51.5, "lon": -0.12, "distance_km": 9.8})
        client, t = make(ok(envelope(data, location=dict(LOCATION, requested=data["requested"]))))
        resp = client.nearest_location(51.5, -0.12, "gb")
        path, query = parts(t.requests[0])
        self.assertEqual(path, "/v1/locations/nearest")
        self.assertEqual(query, {"lat": ["51.5"], "lon": ["-0.12"], "country": ["gb"]})
        self.assertEqual(resp.data.requested.distance_km, 9.8)
        self.assertEqual(resp.location.requested.lat, 51.5)
        self.assertEqual(resp.data.population, 8800000)

    def test_get_location(self):
        data = dict(LOCATION, population=8800000, coverage={"first_year": 1990, "last_date": "2026-10-31"})
        client, t = make(ok(envelope(data)))
        resp = client.get_location("gb/london")
        path, query = parts(t.requests[0])
        self.assertEqual(path, "/v1/locations/gb/london")
        self.assertEqual(query, {})
        self.assertEqual(resp.data.coverage.first_year, 1990)
        self.assertEqual(resp.data.coverage.last_date, "2026-10-31")
        self.assertEqual(resp.location.id, "gb/london")

    def test_get_location_escapes_the_slug(self):
        client, t = make(ok(envelope(dict(LOCATION, population=None, coverage=None))))
        resp = client.get_location("gb/st john's")
        self.assertEqual(parts(t.requests[0])[0], "/v1/locations/gb/st%20john%27s")
        self.assertIsNone(resp.data.coverage)

    def test_get_location_needs_an_id(self):
        client, t = make(ok(envelope({})))
        for bad in ["london", "gb/", "/london", "a/b/c", ""]:
            with self.assertRaises(pastclimate.InvalidRequestError):
                client.get_location(bad)
        self.assertEqual(t.requests, [])


class DataEndpoints(unittest.TestCase):
    def test_get_daily_by_id(self):
        meta = {"units": UNITS_METRIC, "start": "2024-01-01", "end": "2024-01-31", "days": 31}
        client, t = make(ok(envelope([DAILY_ROW], meta)))
        resp = client.get_daily("gb/london", start="2024-01-01", end=datetime.date(2024, 1, 31), units="imperial")
        path, query = parts(t.requests[0])
        self.assertEqual(path, "/v1/daily")
        self.assertEqual(
            query,
            {"location": ["gb/london"], "start": ["2024-01-01"], "end": ["2024-01-31"], "units": ["imperial"]},
        )
        row = resp.data[0]
        self.assertEqual(row.date, "2024-01-01")
        self.assertEqual(row.daily_max_temp, 8.2)
        self.assertIs(row.rain_flag, False)
        self.assertEqual(resp.meta.days, 31)
        self.assertEqual(resp.meta.units.temperature, "C")
        self.assertEqual(resp.location.timezone, "Europe/London")

    def test_get_daily_by_point(self):
        client, t = make(ok(envelope([DAILY_ROW], {"units": UNITS_METRIC, "start": "a", "end": "b", "days": 1})))
        client.get_daily(lat=51.5, lon=-0.1234567, country="gb", start="2024-01-01", end="2024-01-01")
        _, query = parts(t.requests[0])
        self.assertEqual(query["location"], ["51.5,-0.123457"])
        self.assertEqual(query["country"], ["gb"])

    def test_point_needs_country_and_both_coordinates(self):
        client, t = make(ok(envelope([])))
        with self.assertRaises(pastclimate.InvalidRequestError):
            client.get_monthly(lat=1.0, lon=2.0)
        with self.assertRaises(pastclimate.InvalidRequestError):
            client.get_monthly(lat=1.0, country="gb")
        with self.assertRaises(pastclimate.InvalidRequestError):
            client.get_monthly()
        with self.assertRaises(pastclimate.InvalidRequestError):
            client.get_monthly("gb/london", lat=1.0, lon=2.0, country="gb")
        self.assertEqual(t.requests, [])

    def test_location_string_may_carry_a_point_with_country(self):
        client, t = make(ok(envelope([])))
        client.get_monthly("51.5,-0.12", country="gb")
        _, query = parts(t.requests[0])
        self.assertEqual(query, {"location": ["51.5,-0.12"], "country": ["gb"]})

    def test_get_hourly(self):
        meta = {"units": UNITS_METRIC, "date": "2024-01-15", "days": 2, "timezone": "Europe/London"}
        client, t = make(ok(envelope([HOURLY_ROW], meta)))
        resp = client.get_hourly("gb/london", date="2024-01-15", days=2)
        path, query = parts(t.requests[0])
        self.assertEqual(path, "/v1/hourly")
        self.assertEqual(query, {"location": ["gb/london"], "date": ["2024-01-15"], "days": ["2"]})
        self.assertEqual(resp.data[0].timestamp_utc, "2024-01-15T00:00:00Z")
        self.assertEqual(resp.data[0].solar_radiation_kwh_m2, 0.0)
        self.assertEqual(resp.meta.timezone, "Europe/London")
        self.assertEqual(resp.meta.days, 2)

    def test_get_hourly_days_is_optional(self):
        client, t = make(ok(envelope([], {"units": UNITS_METRIC, "date": "x", "days": 1, "timezone": None})))
        client.get_hourly("gb/london", date=datetime.date(2024, 1, 15))
        self.assertNotIn("days", parts(t.requests[0])[1])

    def test_get_monthly(self):
        client, t = make(ok(envelope([MONTHLY_ROW], {"units": UNITS_METRIC, "rows": 1})))
        resp = client.get_monthly("gb/london", units="metric")
        path, query = parts(t.requests[0])
        self.assertEqual(path, "/v1/monthly")
        self.assertEqual(query, {"location": ["gb/london"], "units": ["metric"]})
        self.assertEqual(resp.data[0].monthly_total_rain, 60.1)
        self.assertEqual(resp.data[0].hours, 744)
        self.assertEqual(resp.meta.rows, 1)

    def test_get_yearly(self):
        client, t = make(ok(envelope([YEARLY_ROW], {"units": UNITS_METRIC, "rows": 1})))
        resp = client.get_yearly("gb/london")
        self.assertEqual(parts(t.requests[0])[0], "/v1/yearly")
        self.assertEqual(resp.data[0].months, 12)
        self.assertEqual(resp.data[0].yearly_total_solar_j_m2, 4.5e9)

    def test_get_normals(self):
        client, t = make(ok(envelope(NORMALS_DATA, {"units": UNITS_METRIC, "month": 7})))
        resp = client.get_normals("gb/london", month=7)
        path, query = parts(t.requests[0])
        self.assertEqual(path, "/v1/normals")
        self.assertEqual(query, {"location": ["gb/london"], "month": ["7"]})
        self.assertEqual(resp.data.monthly[0].avg_temp, 18.5)
        self.assertIsNone(resp.data.monthly[0].avg_humidity_pct)
        self.assertEqual(len(resp.data.day_of_year), 2)
        self.assertEqual(resp.data.day_of_year[1].md, "07-02")
        self.assertEqual(resp.meta.month, 7)

    def test_get_normals_without_month(self):
        client, t = make(ok(envelope(NORMALS_DATA, {"units": UNITS_METRIC, "month": None})))
        resp = client.get_normals("gb/london")
        self.assertNotIn("month", parts(t.requests[0])[1])
        self.assertIsNone(resp.meta.month)

    def test_get_records(self):
        client, t = make(ok(envelope(RECORDS_DATA, {"units": UNITS_METRIC})))
        resp = client.get_records("gb/london", units="imperial")
        path, query = parts(t.requests[0])
        self.assertEqual(path, "/v1/records")
        self.assertEqual(query["units"], ["imperial"])
        self.assertEqual([r.metric for r in resp.data], ["hottest_day", "coldest_day", "wettest_day", "windiest_day"])
        self.assertEqual(resp.data[0].occurred_on, "2022-07-19")
        self.assertIsNone(resp.data[3].occurred_on)

    def test_get_coverage(self):
        data = {"countries": [{"country": "gb", "first_year": 1990, "last_date": "2026-10-31"}]}
        client, t = make(ok(envelope(data, location=None)))
        resp = client.get_coverage("gb")
        path, query = parts(t.requests[0])
        self.assertEqual(path, "/v1/coverage")
        self.assertEqual(query, {"country": ["gb"]})
        self.assertEqual(resp.data.countries[0].country, "gb")
        self.assertEqual(resp.data.countries[0].last_date, "2026-10-31")

    def test_get_coverage_without_country(self):
        client, t = make(ok(envelope({"countries": []}, location=None)))
        client.get_coverage()
        self.assertEqual(parts(t.requests[0])[1], {})

    def test_get_me(self):
        client, t = make(ok(envelope(ME_DATA, {"credits": 0}, location=None)))
        resp = client.get_me()
        path, query = parts(t.requests[0])
        self.assertEqual(path, "/v1/me")
        self.assertEqual(query, {})
        self.assertEqual(resp.data.plan.id, "free")
        self.assertEqual(resp.data.key.spend_order, "plan_first")
        self.assertIsNone(resp.data.credits.monthly_limit)
        self.assertEqual(resp.data.credits.one_time_remaining, 1000)
        self.assertEqual(resp.data.rate_limit.per_minute, 17)
        self.assertEqual(resp.credits_used, 0)


class MetaAndRateLimit(unittest.TestCase):
    def test_credits_and_rate_limit_on_every_response(self):
        client, _ = make(ok(envelope([DAILY_ROW], {"credits": 4, "credits_remaining": 77, "units": UNITS_METRIC})))
        resp = client.get_daily("gb/london", start="2024-01-01", end="2024-01-01")
        self.assertEqual(resp.credits_used, 4)
        self.assertEqual(resp.credits_remaining, 77)
        self.assertEqual(resp.meta.credits, 4)
        self.assertEqual(resp.meta.credits_remaining, 77)
        self.assertEqual(resp.meta.methodology_version, "1.0.0")
        self.assertEqual(resp.rate_limit.limit, 60)
        self.assertEqual(resp.rate_limit.remaining, 59)
        self.assertEqual(resp.rate_limit.reset, 42)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["x-credits-used"], "2")

    def test_missing_rate_limit_headers_read_as_none(self):
        from .helpers import json_response

        client, _ = make(json_response(envelope({"countries": []}, location=None)))
        resp = client.get_coverage()
        self.assertIsNone(resp.rate_limit.limit)
        self.assertIsNone(resp.rate_limit.remaining)
        self.assertIsNone(resp.rate_limit.reset)

    def test_null_credits_remaining_falls_back_to_header(self):
        client, _ = make(ok(envelope({"countries": []}, {"credits_remaining": None}, location=None)))
        resp = client.get_coverage()
        self.assertEqual(resp.credits_remaining, 998)

    def test_unknown_fields_are_ignored_but_kept_in_raw(self):
        body = envelope([dict(DAILY_ROW, brand_new_field=1)], {"units": UNITS_METRIC, "start": "a", "end": "b", "days": 1})
        body["extra_top_level"] = True
        client, _ = make(ok(body))
        resp = client.get_daily("gb/london", start="2024-01-01", end="2024-01-01")
        self.assertEqual(resp.data[0].date, "2024-01-01")
        self.assertEqual(resp.raw["data"][0]["brand_new_field"], 1)
        self.assertTrue(resp.raw["extra_top_level"])

    def test_models_are_immutable(self):
        client, _ = make(ok(envelope([DAILY_ROW], {"units": UNITS_METRIC, "start": "a", "end": "b", "days": 1})))
        resp = client.get_daily("gb/london", start="2024-01-01", end="2024-01-01")
        with self.assertRaises(Exception):
            resp.data[0].date = "x"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
