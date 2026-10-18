#!/usr/bin/env python
"""Unit tests for ``tools/polite_http.py``, the one polite GET every fetcher shares:
the User-Agent rides every request, 429/503 back off and retry, any other error raises
(``fetch``) or warns and yields ``None`` (``fetch_or_none``). No network: ``urlopen``
and ``time.sleep`` are patched.

    python -m unittest discover -t tools/tests -s tools/tests -p test_polite_http.py

Built with the help of Claude Code.
"""

from __future__ import annotations

import io
import sys
import unittest
import urllib.error
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import polite_http  # noqa: E402


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://x/", code, "err", headers, None)


class PoliteHttpTest(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        patcher = mock.patch.object(polite_http.time, "sleep", self.sleeps.append)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_user_agent_is_sent(self):
        seen = []

        def urlopen(req, timeout):
            seen.append(req.get_header("User-agent"))
            return _Resp(b"ok")
        with mock.patch.object(polite_http.urllib.request, "urlopen", urlopen):
            self.assertEqual(polite_http.fetch("https://x/"), b"ok")
        self.assertEqual(seen, [polite_http.USER_AGENT])

    def test_429_backs_off_then_succeeds(self):
        answers = [_http_error(429, "7"), _http_error(503), _Resp(b"body")]

        def urlopen(req, timeout):
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a
        with mock.patch.object(polite_http.urllib.request, "urlopen", urlopen), \
                redirect_stderr(io.StringIO()):
            self.assertEqual(polite_http.fetch("https://x/"), b"body")
        self.assertEqual(self.sleeps, [7.0, 10.0])   # Retry-After, then doubled backoff

    def test_other_errors_raise_or_yield_none(self):
        def urlopen(req, timeout):
            raise _http_error(404)
        with mock.patch.object(polite_http.urllib.request, "urlopen", urlopen):
            with self.assertRaises(urllib.error.HTTPError):
                polite_http.fetch("https://x/")
            with redirect_stderr(io.StringIO()) as err:
                self.assertIsNone(polite_http.fetch_or_none("https://x/"))
        self.assertIn("[warn] https://x/", err.getvalue())
        self.assertEqual(self.sleeps, [polite_http.PAUSE_S])

    def test_fetch_or_none_decodes_unless_binary(self):
        with mock.patch.object(polite_http.urllib.request, "urlopen",
                               lambda req, timeout: _Resp("é".encode())):
            self.assertEqual(polite_http.fetch_or_none("https://x/"), "é")
            self.assertEqual(polite_http.fetch_or_none("https://x/", binary=True), "é".encode())


if __name__ == "__main__":
    unittest.main()
