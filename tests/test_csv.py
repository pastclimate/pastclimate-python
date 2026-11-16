from __future__ import annotations

import unittest
import urllib.parse

import pastclimate
from pastclimate import Client, CsvResponse, HTTPResponse

from .helpers import KEY, RATE_HEADERS, FakeTransport, error_response

CSV = "date,daily_avg_temp\n2024-01-01,5.1\n2024-01-02,4.9\n"


def csv_response():
    headers = dict(RATE_HEADERS)
    headers["content-type"] = "text/csv; charset=utf-8"
    return HTTPResponse(status=200, headers=headers, body=CSV.encode("utf-8"))


class CsvTests(unittest.TestCase):
    def test_daily_csv(self):
        t = FakeTransport(csv_response())
        client = Client(KEY, base_url="https://api.example.test", transport=t)
        resp = client.get_daily("gb/london", start="2024-01-01", end="2024-01-02", format="csv")
        self.assertIsInstance(resp, CsvResponse)
        self.assertEqual(resp.text, CSV)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(t.requests[0].url).query)
        self.assertEqual(query["format"], ["csv"])
        self.assertEqual(t.requests[0].headers["Accept"], "text/csv")
        self.assertEqual(t.requests[0].headers["Authorization"], "Bearer " + KEY)
        self.assertEqual(resp.credits_used, 2)
        self.assertEqual(resp.credits_remaining, 998)
        self.assertEqual(resp.rate_limit.remaining, 59)
        self.assertEqual(resp.status_code, 200)

    def test_hourly_csv(self):
        t = FakeTransport(csv_response())
        client = Client(KEY, base_url="https://api.example.test", transport=t)
        resp = client.get_hourly("gb/london", date="2024-01-15", days=1, format="csv", units="imperial")
        self.assertEqual(resp.text, CSV)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(t.requests[0].url).query)
        self.assertEqual(query["format"], ["csv"])
        self.assertEqual(query["units"], ["imperial"])

    def test_json_is_the_default_and_sends_no_format(self):
        from .helpers import DAILY_ROW, UNITS_METRIC, envelope, ok

        t = FakeTransport(ok(envelope([DAILY_ROW], {"units": UNITS_METRIC, "start": "a", "end": "b", "days": 1})))
        client = Client(KEY, base_url="https://api.example.test", transport=t)
        client.get_daily("gb/london", start="2024-01-01", end="2024-01-01", format="json")
        self.assertNotIn("format=", t.requests[0].url)

    def test_unknown_format_is_refused_before_sending(self):
        t = FakeTransport(csv_response())
        client = Client(KEY, base_url="https://api.example.test", transport=t)
        with self.assertRaises(pastclimate.InvalidRequestError):
            client.get_daily("gb/london", start="2024-01-01", end="2024-01-02", format="xml")  # type: ignore[call-overload]
        self.assertEqual(t.requests, [])

    def test_csv_request_that_fails_raises_the_json_error(self):
        t = FakeTransport(error_response("not_published", 404, "No published data for this request."))
        client = Client(KEY, base_url="https://api.example.test", transport=t)
        with self.assertRaises(pastclimate.NotFoundError) as ctx:
            client.get_daily("gb/london", start="1900-01-01", end="1900-01-02", format="csv")
        self.assertEqual(ctx.exception.code, "not_published")
        self.assertEqual(len(t.requests), 1)


if __name__ == "__main__":
    unittest.main()
