from __future__ import annotations

import gzip
import io
import urllib.error

import pytest
from fakes import Response

from plugin import arxiv


def busy(code: int = 503, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://export.arxiv.org/src/1", code, "busy", headers, io.BytesIO())


class Sized(Response):
    """A response that says it is ``length`` bytes long."""

    def __init__(self, body: bytes, length: int) -> None:
        super().__init__(body)
        self.headers = {"Content-Length": str(length)}


class Flaky:
    """Answers with each of ``answers`` in turn (raising the errors), then with b"ok"."""

    def __init__(self, *answers) -> None:
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, request, timeout=None):
        self.calls += 1
        answer = self.answers.pop(0) if self.answers else Response(b"ok")
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(arxiv.time, "sleep", slept.append)
    return slept


def test_waits_the_pause_between_requests(monkeypatch: pytest.MonkeyPatch, waits: list[float]) -> None:
    monkeypatch.setattr(arxiv, "PAUSE", 3.0)
    monkeypatch.setattr(arxiv, "_last", 0.0)
    clock = iter([100.0, 100.0, 101.0, 101.0])
    monkeypatch.setattr(arxiv.time, "monotonic", lambda: next(clock))
    arxiv.fetch("https://export.arxiv.org/a", limit=10, opener=Flaky())
    arxiv.fetch("https://export.arxiv.org/b", limit=10, opener=Flaky())
    assert waits == [2.0]


def test_asks_again_while_arxiv_is_busy(waits: list[float]) -> None:
    opener = Flaky(busy(503, retry_after="7"), busy(503))
    assert arxiv.fetch("https://export.arxiv.org/a", limit=10, opener=opener) == b"ok"
    assert opener.calls == 3
    assert 7.0 in waits


def test_fails_at_once_when_arxiv_limits_this_computer(waits: list[float]) -> None:
    opener = Flaky(busy(429, retry_after="7"))
    with pytest.raises(arxiv.RateLimited, match="HTTP 429"):
        arxiv.fetch("https://export.arxiv.org/a", limit=10, opener=opener)
    assert opener.calls == 1 and 7.0 not in waits


def test_asks_again_for_an_answer_cut_short(waits: list[float]) -> None:
    archive = gzip.compress(b"\\documentclass{article}" * 100)
    opener = Flaky(Sized(archive[:10], len(archive)), Response(archive[:-8]), Sized(archive, len(archive)))
    assert arxiv.fetch("https://export.arxiv.org/a", limit=10_000, opener=opener) == archive
    assert opener.calls == 3


def test_gives_up_after_its_attempts_and_at_once_on_other_errors(waits: list[float]) -> None:
    opener = Flaky(*[busy() for _ in range(arxiv.ATTEMPTS)])
    with pytest.raises(urllib.error.HTTPError, match="busy"):
        arxiv.fetch("https://export.arxiv.org/a", limit=10, opener=opener)
    assert opener.calls == arxiv.ATTEMPTS
    missing = Flaky(busy(404))
    with pytest.raises(urllib.error.HTTPError):
        arxiv.fetch("https://export.arxiv.org/a", limit=10, opener=missing)
    assert missing.calls == 1


def test_refuses_an_answer_past_the_limit() -> None:
    with pytest.raises(ValueError, match="download limit"):
        arxiv.fetch("https://export.arxiv.org/a", limit=1, opener=Flaky())
