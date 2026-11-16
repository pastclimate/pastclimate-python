from __future__ import annotations

import unittest

import pastclimate
from pastclimate import (
    ApiError,
    AuthenticationError,
    Client,
    HTTPResponse,
    InvalidRequestError,
    NotFoundError,
    PastClimateError,
    PlanRequiredError,
    QuotaExceededError,
    RateLimitError,
    ServerError,
)

from .helpers import KEY, FakeTransport, Sleeps, error_response, json_response

# code, HTTP status, expected class
CASES = [
    ("missing_key", 401, AuthenticationError),
    ("invalid_key", 401, AuthenticationError),
    ("key_revoked", 401, AuthenticationError),
    ("email_not_verified", 403, AuthenticationError),
    ("account_suspended", 403, AuthenticationError),
    ("plan_required", 403, PlanRequiredError),
    ("cors_not_supported", 403, InvalidRequestError),
    ("location_not_found", 404, NotFoundError),
    ("not_published", 404, NotFoundError),
    ("not_found", 404, NotFoundError),
    ("method_not_allowed", 405, InvalidRequestError),
    ("invalid_request", 400, InvalidRequestError),
    ("range_too_large", 400, InvalidRequestError),
    ("key_in_query", 400, InvalidRequestError),
    ("location_blocked", 422, NotFoundError),
    ("quota_exceeded", 429, QuotaExceededError),
    ("daily_request_cap_reached", 429, RateLimitError),
    ("rate_limited", 429, RateLimitError),
    ("internal_error", 500, ServerError),
    ("api_disabled", 503, ServerError),
    ("metering_unavailable", 503, ServerError),
]


def call(client: Client):
    return client.get_records("gb/london")


class ErrorMapping(unittest.TestCase):
    def test_every_code_maps_to_its_category(self):
        for code, status, cls in CASES:
            with self.subTest(code=code):
                # max_retries=0: this test is about mapping, not retrying.
                t = FakeTransport(error_response(code, status, "msg for " + code))
                client = Client(KEY, transport=t, max_retries=0, sleep=Sleeps())
                with self.assertRaises(cls) as ctx:
                    call(client)
                err = ctx.exception
                self.assertIs(type(err), cls)
                self.assertEqual(err.code, code)
                self.assertEqual(err.status, status)
                self.assertEqual(err.message, "msg for " + code)
                self.assertTrue(err.docs_url.endswith("#" + code))
                self.assertIsInstance(err, ApiError)
                self.assertIsInstance(err, PastClimateError)

    def test_str_has_status_code_and_message(self):
        t = FakeTransport(error_response("location_not_found", 404, "Location not found."))
        client = Client(KEY, transport=t)
        with self.assertRaises(NotFoundError) as ctx:
            call(client)
        self.assertEqual(str(ctx.exception), "404 location_not_found: Location not found.")

    def test_error_carries_rate_limit_retry_after_and_upgrade_url(self):
        headers = {
            "retry-after": "12",
            "ratelimit-limit": "10",
            "ratelimit-remaining": "0",
            "ratelimit-reset": "12",
            "x-upgrade-url": "https://example.test/upgrade",
        }
        t = FakeTransport(error_response("rate_limited", 429, headers=headers))
        client = Client(KEY, transport=t, max_retries=0)
        with self.assertRaises(RateLimitError) as ctx:
            call(client)
        err = ctx.exception
        self.assertEqual(err.retry_after, 12.0)
        self.assertEqual(err.upgrade_url, "https://example.test/upgrade")
        self.assertEqual(err.rate_limit.limit, 10)
        self.assertEqual(err.rate_limit.remaining, 0)
        self.assertEqual(err.rate_limit.reset, 12)
        self.assertEqual(err.headers["retry-after"], "12")

    def test_unknown_code_falls_back_by_status(self):
        expected = {
            400: InvalidRequestError,
            401: AuthenticationError,
            404: NotFoundError,
            422: InvalidRequestError,
            429: RateLimitError,
            500: ServerError,
            502: ServerError,
            418: ApiError,
            403: ApiError,
        }
        for status, cls in expected.items():
            with self.subTest(status=status):
                t = FakeTransport(error_response("some_future_code", status))
                client = Client(KEY, transport=t, max_retries=0)
                with self.assertRaises(ApiError) as ctx:
                    call(client)
                self.assertIs(type(ctx.exception), cls)
                self.assertEqual(ctx.exception.code, "some_future_code")

    def test_non_json_error_body(self):
        t = FakeTransport(HTTPResponse(status=502, headers={}, body=b"<html>Bad gateway</html>"))
        client = Client(KEY, transport=t, max_retries=0)
        with self.assertRaises(ServerError) as ctx:
            call(client)
        self.assertEqual(ctx.exception.status, 502)
        self.assertEqual(ctx.exception.code, "unknown_error")
        self.assertIn("Bad gateway", ctx.exception.message)
        self.assertIsNone(ctx.exception.docs_url)

    def test_empty_error_body(self):
        t = FakeTransport(HTTPResponse(status=404, headers={}, body=b""))
        client = Client(KEY, transport=t, max_retries=0)
        with self.assertRaises(NotFoundError) as ctx:
            call(client)
        self.assertEqual(ctx.exception.message, "HTTP 404")

    def test_success_with_a_body_that_is_not_the_envelope(self):
        for body in (b"<html>captive portal</html>", b"[]", b'{"nope": 1}'):
            with self.subTest(body=body):
                t = FakeTransport(HTTPResponse(status=200, headers={}, body=body))
                client = Client(KEY, transport=t)
                with self.assertRaises(ApiError) as ctx:
                    call(client)
                self.assertIs(type(ctx.exception), ApiError)
                self.assertEqual(ctx.exception.code, "invalid_response")

    def test_client_side_errors_have_status_zero(self):
        client = Client(KEY, transport=FakeTransport(json_response({})))
        with self.assertRaises(InvalidRequestError) as ctx:
            client.get_monthly()
        self.assertEqual(ctx.exception.status, 0)
        self.assertEqual(ctx.exception.code, "invalid_request")
        self.assertNotIn("0 ", str(ctx.exception).split(":")[0])


class CategoriesAreDistinct(unittest.TestCase):
    def test_one_class_per_category_all_subclass_api_error(self):
        classes = [
            AuthenticationError,
            InvalidRequestError,
            NotFoundError,
            PlanRequiredError,
            RateLimitError,
            QuotaExceededError,
            ServerError,
        ]
        self.assertEqual(len(set(classes)), 7)
        for cls in classes:
            self.assertTrue(issubclass(cls, ApiError))
        # Rate limited and quota exceeded must not catch each other.
        self.assertFalse(issubclass(RateLimitError, QuotaExceededError))
        self.assertFalse(issubclass(QuotaExceededError, RateLimitError))


if __name__ == "__main__":
    unittest.main()
