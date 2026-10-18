"""The one polite HTTP GET every fetcher shares, and the one User-Agent it sends.

Not named ``http.py``: ``tools/`` sits on ``sys.path`` and would shadow the stdlib
``http`` package that ``urllib.request`` itself imports.

* :data:`USER_AGENT`: descriptive, as the Wikimedia API policy and NLM ask. Set
  ``NEURARIUM_FETCH_CONTACT`` to a real e-mail or URL before a large run; no personal
  address is hard-coded.
* :func:`open_with_retry`: open a prepared request, backing off on HTTP 429 / 503
  (honouring ``Retry-After``) so a long run rides through a rate-limit window; any other
  error raises.
* :func:`fetch`: :func:`open_with_retry` on a url with our User-Agent (raises).
* :func:`fetch_or_none`: the lenient variant a resumable crawler wants: warns on stderr
  and returns ``None`` on any network error, pauses :data:`PAUSE_S` after every call.

Stdlib only. Built with the help of Claude Code.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request

CONTACT = os.environ.get("NEURARIUM_FETCH_CONTACT", "contact via repository")
USER_AGENT = f"neurarium-dataset/1.0 (research dataset; {CONTACT})"
PAUSE_S = 0.4        # seconds after each fetch_or_none call, to stay a polite API citizen
RETRY_CODES = (429, 503)
MAX_RETRIES = 5


def open_with_retry(req: urllib.request.Request, timeout: float = 60) -> bytes:
    """The body of ``req``, retried on 429/503 with exponential backoff (5 s doubling,
    capped at 120 s) or the server's numeric ``Retry-After``; any other error raises."""
    backoff = 5.0
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_CODES or attempt == MAX_RETRIES:
                raise
            retry_after = exc.headers.get("Retry-After")
            wait = float(retry_after) if (retry_after or "").isdigit() else backoff
            print(f"    {exc.code}; backing off {wait:.0f}s "
                  f"(attempt {attempt + 1}/{MAX_RETRIES})", file=sys.stderr)
            time.sleep(wait)
            backoff = min(backoff * 2, 120)
    raise RuntimeError("unreachable")


def request(url: str, headers: dict[str, str] | None = None) -> urllib.request.Request:
    """A GET request for ``url`` carrying :data:`USER_AGENT` (plus ``headers``)."""
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})


def fetch(url: str, *, timeout: float = 60, headers: dict[str, str] | None = None) -> bytes:
    """The body of ``url`` (see :func:`open_with_retry`); raises on failure."""
    return open_with_retry(request(url, headers), timeout=timeout)


def fetch_or_none(url: str, *, binary: bool = False, timeout: float = 60):
    """The body of ``url`` as text (or bytes when ``binary``), or ``None`` after a stderr
    warning on any network error; always pauses :data:`PAUSE_S` afterwards."""
    try:
        raw = fetch(url, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"  [warn] {url}: {e}", file=sys.stderr)
        return None
    finally:
        time.sleep(PAUSE_S)
    return raw if binary else raw.decode("utf-8", errors="replace")
