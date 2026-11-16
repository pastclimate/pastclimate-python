"""The default urllib transport against a real local HTTP server (127.0.0.1)."""

from __future__ import annotations

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple

import pastclimate
from pastclimate import Client

from .helpers import KEY, UNITS_METRIC, DAILY_ROW, envelope

SEEN: List[Tuple[str, Dict[str, str]]] = []
STATE: Dict[str, Any] = {"calls": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # silence
        pass

    def _send(self, status: int, body: bytes, headers: Dict[str, str]) -> None:
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        SEEN.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
        STATE["calls"] += 1
        if self.path.startswith("/v1/daily"):
            if "format=csv" in self.path:
                self._send(200, b"date\n2024-01-01\n", {"Content-Type": "text/csv", "X-Credits-Used": "2"})
                return
            body = json.dumps(envelope([DAILY_ROW], {"units": UNITS_METRIC, "start": "a", "end": "b", "days": 1}))
            self._send(
                200,
                body.encode(),
                {"Content-Type": "application/json", "RateLimit-Limit": "60", "RateLimit-Remaining": "59"},
            )
        elif self.path.startswith("/v1/flaky"):
            if STATE["calls"] % 2 == 1:
                err = {"error": {"code": "rate_limited", "message": "slow down", "docs_url": "https://x/#rate_limited"}}
                self._send(429, json.dumps(err).encode(), {"Content-Type": "application/json", "Retry-After": "0"})
            else:
                self._send(200, json.dumps(envelope({"countries": []}, location=None)).encode(), {})
        elif self.path.startswith("/v1/slow"):
            time.sleep(1.0)
            self._send(200, b"{}", {})
        else:
            err = {"error": {"code": "not_found", "message": "No such endpoint.", "docs_url": "https://x/#not_found"}}
            self._send(404, json.dumps(err).encode(), {"Content-Type": "application/json"})


class LocalServerTests(unittest.TestCase):
    server: ThreadingHTTPServer
    base: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = "http://127.0.0.1:{}".format(cls.server.server_address[1])
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        del SEEN[:]
        STATE["calls"] = 0

    def test_json_round_trip_with_real_headers(self) -> None:
        client = Client(KEY, base_url=self.base)
        resp = client.get_daily("gb/london", start="2024-01-01", end="2024-01-01")
        self.assertEqual(resp.data[0].daily_max_temp, 8.2)
        self.assertEqual(resp.rate_limit.limit, 60)
        self.assertEqual(resp.rate_limit.remaining, 59)
        path, headers = SEEN[0]
        self.assertEqual(headers["authorization"], "Bearer " + KEY)
        self.assertEqual(headers["user-agent"], pastclimate.USER_AGENT)
        self.assertNotIn(KEY, path)

    def test_csv_round_trip(self) -> None:
        client = Client(KEY, base_url=self.base)
        resp = client.get_daily("gb/london", start="2024-01-01", end="2024-01-01", format="csv")
        self.assertEqual(resp.text, "date\n2024-01-01\n")
        self.assertEqual(resp.credits_used, 2)

    def test_error_status_becomes_a_typed_error(self) -> None:
        client = Client(KEY, base_url=self.base)
        with self.assertRaises(pastclimate.NotFoundError) as ctx:
            client._call("/v1/nothing", {}, lambda d: d, pastclimate.Meta)
        self.assertEqual(ctx.exception.code, "not_found")
        self.assertEqual(ctx.exception.docs_url, "https://x/#not_found")

    def test_retry_after_zero_retries_and_succeeds(self) -> None:
        client = Client(KEY, base_url=self.base)
        resp = client._call("/v1/flaky", {}, lambda d: d, pastclimate.Meta)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(STATE["calls"], 2)

    def test_timeout_becomes_a_network_error(self) -> None:
        client = Client(KEY, base_url=self.base, timeout=0.2, max_retries=0)
        with self.assertRaises(pastclimate.NetworkError) as ctx:
            client._call("/v1/slow", {}, lambda d: d, pastclimate.Meta)
        self.assertTrue(ctx.exception.timed_out)

    def test_connection_refused_becomes_a_network_error(self) -> None:
        client = Client(KEY, base_url="http://127.0.0.1:9", max_retries=0, timeout=2)
        with self.assertRaises(pastclimate.NetworkError):
            client.get_coverage()


if __name__ == "__main__":
    unittest.main()
