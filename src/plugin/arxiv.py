"""Every request this plugin makes of arXiv, made the way arXiv asks of API clients: one at a time,
at least PAUSE seconds after the last, and, when arXiv answers that it is busy (429 or 503) or its
answer is cut short, again after a wait, up to ATTEMPTS times in all. A run keeps one plugin
process, so the pause holds across every tool call of the run."""

from __future__ import annotations

import gzip
import http.client
import time
import urllib.error
import urllib.request
import zlib

HEADERS = {"User-Agent": "nanoagent-arxiv-source/0.1"}
PAUSE = 3.0
ATTEMPTS = 4
BUSY = {429, 503}

_last = 0.0  # time.monotonic() of the last request


class CutShort(Exception):
    """arXiv's answer ended before all of it arrived."""


def _read(response, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := response.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise ValueError("arXiv response exceeds the download limit")
        chunks.append(chunk)
    body = b"".join(chunks)
    expected = response.headers.get("Content-Length") if getattr(response, "headers", None) else None
    if expected and expected.isdigit() and int(expected) != len(body):
        raise CutShort(f"arXiv sent {len(body)} of {expected} bytes")
    # A gzip archive, which most sources are, says itself whether it is whole.
    if body[:2] == b"\x1f\x8b":
        try:
            gzip.decompress(body)
        except (EOFError, zlib.error) as error:
            raise CutShort(f"arXiv's archive is cut short: {error}") from error
    return body


def _wait_after(error: Exception, attempt: int) -> float:
    headers = getattr(error, "headers", None)
    named = headers.get("Retry-After", "") if headers else ""
    return float(named) if named.isdigit() else PAUSE * 2 ** (attempt + 1)


def fetch(url: str, *, limit: int, opener=urllib.request.urlopen) -> bytes:
    """The whole body of a GET of ``url``, at most ``limit`` bytes; raises arXiv's last error once it
    stops being busy, or after ATTEMPTS tries."""
    global _last
    for attempt in range(ATTEMPTS):
        wait = _last + PAUSE - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()
        try:
            with opener(urllib.request.Request(url, headers=HEADERS)) as response:
                return _read(response, limit)
        except (urllib.error.HTTPError, CutShort, http.client.IncompleteRead, ConnectionError) as error:
            retry = not isinstance(error, urllib.error.HTTPError) or error.code in BUSY
            if not retry or attempt == ATTEMPTS - 1:
                raise
            time.sleep(_wait_after(error, attempt))
    raise AssertionError("unreachable")
