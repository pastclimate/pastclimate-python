from __future__ import annotations

import os
import re
import unittest
from unittest import mock

import pastclimate
from pastclimate import AuthenticationError, Client, InvalidRequestError

from .helpers import KEY, FakeTransport, envelope, ok

OTHER_KEY = "pc_other_key_not_real"


class KeyHandling(unittest.TestCase):
    def test_explicit_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            t = FakeTransport(ok(envelope({"countries": []}, location=None)))
            Client(KEY, transport=t).get_coverage()
            self.assertEqual(t.requests[0].headers["Authorization"], "Bearer " + KEY)

    def test_key_from_environment(self):
        with mock.patch.dict(os.environ, {"PASTCLIMATE_API_KEY": OTHER_KEY}, clear=True):
            t = FakeTransport(ok(envelope({"countries": []}, location=None)))
            Client(transport=t).get_coverage()
            self.assertEqual(t.requests[0].headers["Authorization"], "Bearer " + OTHER_KEY)

    def test_explicit_key_beats_environment(self):
        with mock.patch.dict(os.environ, {"PASTCLIMATE_API_KEY": OTHER_KEY}, clear=True):
            t = FakeTransport(ok(envelope({"countries": []}, location=None)))
            Client(KEY, transport=t).get_coverage()
            self.assertEqual(t.requests[0].headers["Authorization"], "Bearer " + KEY)

    def test_no_key_raises_authentication_error(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AuthenticationError) as ctx:
                Client()
            self.assertEqual(ctx.exception.code, "missing_key")
            self.assertEqual(ctx.exception.status, 0)
            self.assertIn("PASTCLIMATE_API_KEY", ctx.exception.message)

    def test_blank_key_counts_as_missing(self):
        with mock.patch.dict(os.environ, {"PASTCLIMATE_API_KEY": "  "}, clear=True):
            with self.assertRaises(AuthenticationError):
                Client("")

    def test_key_with_whitespace_is_refused(self):
        with self.assertRaises(AuthenticationError):
            Client("pc_bad key")
        with self.assertRaises(AuthenticationError):
            Client("pc_bad\r\nX-Evil: 1")

    def test_repr_does_not_leak_the_key(self):
        client = Client(KEY)
        self.assertNotIn(KEY, repr(client))
        self.assertNotIn(KEY, str(client))


class Configuration(unittest.TestCase):
    def test_defaults(self):
        client = Client(KEY)
        self.assertEqual(client.base_url, "https://api.pastclimate.com")
        self.assertEqual(client._timeout, 30.0)
        self.assertEqual(client._max_retries, 2)

    def test_base_url_is_configurable_and_trailing_slash_is_trimmed(self):
        t = FakeTransport(ok(envelope({"countries": []}, location=None)))
        Client(KEY, base_url="https://pastclimate-api.example.test/", transport=t).get_coverage()
        self.assertTrue(t.requests[0].url.startswith("https://pastclimate-api.example.test/v1/coverage"))

    def test_bad_arguments(self):
        with self.assertRaises(InvalidRequestError):
            Client(KEY, base_url="api.pastclimate.com")
        with self.assertRaises(InvalidRequestError):
            Client(KEY, max_retries=-1)
        with self.assertRaises(InvalidRequestError):
            Client(KEY, timeout=0)

    def test_user_agent_matches_the_version(self):
        self.assertRegex(pastclimate.USER_AGENT, r"^pastclimate-python/\d+\.\d+\.\d+")
        self.assertEqual(pastclimate.USER_AGENT, "pastclimate-python/" + pastclimate.__version__)

    def test_version_matches_pyproject(self):
        try:
            import tomllib
        except ImportError:  # Python < 3.11
            self.skipTest("tomllib needs Python 3.11+")
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "pyproject.toml"), "rb") as fh:
            project = tomllib.load(fh)
        self.assertEqual(project["project"]["name"], "pastclimate")
        self.assertEqual(project["project"]["dynamic"], ["version"])
        with open(os.path.join(here, "..", "src", "pastclimate", "_version.py")) as fh:
            self.assertIsNotNone(re.search(r'__version__ = "\d+\.\d+\.\d+"', fh.read()))

    def test_no_third_party_dependencies(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest("tomllib needs Python 3.11+")
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "pyproject.toml"), "rb") as fh:
            self.assertEqual(tomllib.load(fh)["project"]["dependencies"], [])

    def test_no_hard_coded_credit_costs_in_the_package(self):
        # Credit costs and plan allowances change; the SDK must read them from responses.
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "pastclimate")
        for name in os.listdir(src):
            if name.endswith(".py"):
                with open(os.path.join(src, name)) as fh:
                    text = fh.read().lower()
                self.assertNotRegex(text, r"\d\s*credits?\b", name)


if __name__ == "__main__":
    unittest.main()
