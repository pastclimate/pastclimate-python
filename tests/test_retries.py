from __future__ import annotations

import unittest

import pastclimate
from pastclimate import (
    Client,
    NetworkError,
    QuotaExceededError,
    RateLimitError,
    ServerError,
)

from .helpers import (
    DAILY_ROW,
    KEY,
    UNITS_METRIC,
    FakeTransport,
    Sleeps,
    envelope,
    error_response,
    ok,
)

GOOD = ok(envelope([DAILY_ROW], {"units": UNITS_METRIC, "start": "a", "end": "b", "days": 1}))


def run(client: Client):
    return client.get_daily("gb/london", start="2024-01-01", end="2024-01-01")


def make(*script, **kwargs):
    t = FakeTransport(*script)
    sleeps = Sleeps()
    client = Client(KEY, transport=t, sleep=sleeps, **kwargs)
    return client, t, sleeps


class RetryOn429(unittest.TestCase):
    def test_retry_after_is_honoured(self):
        client, t, sleeps = make(error_response("rate_limited", 429, headers={"retry-after": "7"}), GOOD)
        resp = run(client)
        self.assertEqual(resp.data[0].date, "2024-01-01")
        self.assertEqual(len(t.requests), 2)
        self.assertEqual(sleeps.calls, [7.0])

    def test_retry_after_zero_retries_straight_away(self):
        client, t, sleeps = make(error_response("rate_limited", 429, headers={"retry-after": "0"}), GOOD)
        run(client)
        self.assertEqual(sleeps.calls, [0.0])
        self.assertEqual(len(t.requests), 2)

    def test_daily_request_cap_with_retry_after_is_retried_when_short(self):
        client, t, sleeps = make(error_response("daily_request_cap_reached", 429, headers={"retry-after": "3"}), GOOD)
        run(client)
        self.assertEqual(sleeps.calls, [3.0])

    def test_429_without_retry_after_is_never_retried(self):
        for code, cls in [("rate_limited", RateLimitError), ("quota_exceeded", QuotaExceededError)]:
            with self.subTest(code=code):
                client, t, sleeps = make(error_response(code, 429), GOOD)
                with self.assertRaises(cls):
                    run(client)
                self.assertEqual(len(t.requests), 1)
                self.assertEqual(sleeps.calls, [])

    def test_quota_exceeded_without_retry_after_does_not_loop(self):
        # The free credits are gone: waiting never helps.
        client, t, sleeps = make(error_response("quota_exceeded", 429, "Your free credits are used up."))
        with self.assertRaises(QuotaExceededError) as ctx:
            run(client)
        self.assertIsNone(ctx.exception.retry_after)
        self.assertEqual(len(t.requests), 1)

    def test_unreadable_retry_after_counts_as_absent(self):
        client, t, _ = make(error_response("rate_limited", 429, headers={"retry-after": "soon"}), GOOD)
        with self.assertRaises(RateLimitError):
            run(client)
        self.assertEqual(len(t.requests), 1)

    def test_retry_after_longer_than_the_cap_is_raised_not_slept(self):
        client, t, sleeps = make(
            error_response("daily_request_cap_reached", 429, headers={"retry-after": "40000"}), GOOD
        )
        with self.assertRaises(RateLimitError) as ctx:
            run(client)
        self.assertEqual(ctx.exception.retry_after, 40000.0)
        self.assertEqual(len(t.requests), 1)
        self.assertEqual(sleeps.calls, [])

    def test_the_cap_can_be_raised(self):
        client, t, sleeps = make(
            error_response("rate_limited", 429, headers={"retry-after": "120"}), GOOD, max_retry_after=300
        )
        run(client)
        self.assertEqual(sleeps.calls, [120.0])

    def test_gives_up_after_max_retries(self):
        client, t, sleeps = make(error_response("rate_limited", 429, headers={"retry-after": "1"}))
        with self.assertRaises(RateLimitError):
            run(client)
        self.assertEqual(len(t.requests), 3)  # 1 try + 2 retries
        self.assertEqual(sleeps.calls, [1.0, 1.0])

    def test_http_date_retry_after(self):
        from pastclimate._http import parse_retry_after

        self.assertEqual(parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT", now=1445412470.0), 10.0)
        self.assertEqual(parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT", now=1445412490.0), 0.0)
        self.assertIsNone(parse_retry_after("-5"))
        self.assertIsNone(parse_retry_after(""))
        self.assertIsNone(parse_retry_after(None))


class RetryOnServerErrors(unittest.TestCase):
    def test_500_then_success(self):
        client, t, sleeps = make(error_response("internal_error", 500), GOOD)
        resp = run(client)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(t.requests), 2)
        self.assertEqual(len(sleeps.calls), 1)
        self.assertTrue(0.0 < sleeps.calls[0] <= 0.5)

    def test_backoff_grows(self):
        client, t, sleeps = make(error_response("api_disabled", 503), error_response("api_disabled", 503), GOOD)
        run(client)
        self.assertEqual(len(sleeps.calls), 2)
        self.assertTrue(0.0 < sleeps.calls[0] <= 0.5)
        self.assertTrue(0.25 < sleeps.calls[1] <= 1.0)

    def test_gives_up_after_max_retries(self):
        client, t, sleeps = make(error_response("metering_unavailable", 503))
        with self.assertRaises(ServerError) as ctx:
            run(client)
        self.assertEqual(ctx.exception.status, 503)
        self.assertEqual(len(t.requests), 3)
        self.assertEqual(len(sleeps.calls), 2)

    def test_retry_after_on_5xx_is_honoured(self):
        client, t, sleeps = make(error_response("api_disabled", 503, headers={"retry-after": "5"}), GOOD)
        run(client)
        self.assertEqual(sleeps.calls, [5.0])

    def test_max_retries_zero_never_retries(self):
        client, t, sleeps = make(error_response("internal_error", 500), GOOD, max_retries=0)
        with self.assertRaises(ServerError):
            run(client)
        self.assertEqual(len(t.requests), 1)
        self.assertEqual(sleeps.calls, [])

    def test_custom_max_retries(self):
        client, t, _ = make(error_response("internal_error", 500), max_retries=4)
        with self.assertRaises(ServerError):
            run(client)
        self.assertEqual(len(t.requests), 5)


class RetryOnNetworkErrors(unittest.TestCase):
    def test_connection_error_then_success(self):
        client, t, sleeps = make(ConnectionResetError("reset"), GOOD)
        run(client)
        self.assertEqual(len(t.requests), 2)
        self.assertEqual(len(sleeps.calls), 1)

    def test_persistent_connection_error_raises_network_error(self):
        client, t, _ = make(ConnectionRefusedError("refused"))
        with self.assertRaises(NetworkError) as ctx:
            run(client)
        self.assertEqual(len(t.requests), 3)
        self.assertFalse(ctx.exception.timed_out)
        self.assertIsInstance(ctx.exception.__cause__, ConnectionRefusedError)
        self.assertIsInstance(ctx.exception, pastclimate.PastClimateError)

    def test_timeout_is_flagged(self):
        client, t, _ = make(TimeoutError("timed out"), max_retries=1)
        with self.assertRaises(NetworkError) as ctx:
            run(client)
        self.assertTrue(ctx.exception.timed_out)
        self.assertEqual(len(t.requests), 2)

    def test_the_request_carries_the_timeout(self):
        client, t, _ = make(GOOD, timeout=5.5)
        run(client)
        self.assertEqual(t.requests[0].timeout, 5.5)


class NeverRetried(unittest.TestCase):
    def test_other_4xx_are_not_retried(self):
        for code, status in [
            ("invalid_request", 400),
            ("invalid_key", 401),
            ("plan_required", 403),
            ("location_not_found", 404),
            ("not_published", 404),
            ("location_blocked", 422),
        ]:
            with self.subTest(code=code):
                client, t, sleeps = make(error_response(code, status, headers={"retry-after": "1"}), GOOD)
                with self.assertRaises(pastclimate.ApiError):
                    run(client)
                self.assertEqual(len(t.requests), 1)
                self.assertEqual(sleeps.calls, [])


if __name__ == "__main__":
    unittest.main()
