from __future__ import annotations

import urllib.error
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fakes import FakeArxiv, Response

from contract import SearchInput
from plugin.search import search_papers


def test_finds_papers_on_arxiv_through_openalex_best_match_first(tmp_path: Path) -> None:
    arxiv = FakeArxiv("1706.03762v7", "hep-th/9901001v1", "1706.03762")
    result = search_papers(SearchInput(query=" attention is all you need ", max_results=3), tmp_path, opener=arxiv)
    assert result.query == "attention is all you need"
    # Each paper by its arXiv id without a version, once.
    assert [paper.arxiv_id for paper in result.papers] == ["1706.03762", "hep-th/9901001"]
    first = result.papers[0]
    assert (first.title, first.authors) == ("Paper 1706.03762v7", ["Ashish Vaswani", "Noam Shazeer"])
    assert (first.summary, first.published) == ("An abstract.", "2017-06-12")
    assert first.abs_url == "https://arxiv.org/abs/1706.03762"
    query = parse_qs(urlparse(arxiv.urls[0]).query)
    assert query["search"] == ["attention is all you need"] and query["filter"] == ["locations.source.id:S4306400194"]
    assert query["per-page"] == ["3"]
    # arXiv itself is not asked.
    assert all(url.startswith("https://api.openalex.org/") for url in arxiv.urls)


@pytest.mark.parametrize(
    "query", ["1512.03385", "https://arxiv.org/abs/1512.03385v1", "arxiv.org/pdf/1512.03385", "save 1512.03385 please"]
)
def test_looks_up_the_one_paper_whose_arxiv_id_the_query_names(tmp_path: Path, query: str) -> None:
    arxiv = FakeArxiv()
    result = search_papers(SearchInput(query=query, max_results=5), tmp_path, opener=arxiv)
    assert [paper.arxiv_id for paper in result.papers] == ["1512.03385"]
    assert arxiv.urls[0].startswith("https://api.openalex.org/works/doi:10.48550/arXiv.1512.03385?")


def busy(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x/", code, "busy", {}, Response(b""))


@pytest.mark.parametrize("arxiv_id", [None, "1512.03385"])
def test_asks_arxiv_when_openalex_is_slow_then_datacite_when_arxiv_limits_this_computer(
    tmp_path: Path, arxiv_id
) -> None:
    query = arxiv_id or "attention"
    slow = FakeArxiv("1706.03762v7", down={"api.openalex.org": TimeoutError("timed out")})
    result = search_papers(SearchInput(query=query, max_results=1), tmp_path, opener=slow)
    assert (result.engine, result.passed_over) == ("arXiv", ["OpenAlex: timed out"])
    assert result.papers[0].arxiv_id == (arxiv_id or "1706.03762") and result.papers[0].published == "2017-06-12"
    limited = FakeArxiv("1706.03762v7", down={"api.openalex.org": busy(503), "export.arxiv.org": busy(429)})
    result = search_papers(SearchInput(query=query, max_results=1), tmp_path, opener=limited)
    assert result.engine == "DataCite" and result.passed_over[0] == "OpenAlex: HTTP 503"
    assert "limiting requests" in result.passed_over[1]
    first = result.papers[0]
    assert (first.arxiv_id, first.authors, first.published) == (
        arxiv_id or "1706.03762",
        ["Ashish Vaswani"],
        "2017-06-12",
    )


def test_passes_over_an_engine_that_finds_nothing(tmp_path: Path) -> None:
    calls = []

    def openalex_empty(request, timeout=None):
        calls.append(request.full_url)
        if request.full_url.startswith("https://api.openalex.org/"):
            return Response(b'{"results": []}')
        return FakeArxiv("1706.03762")(request, timeout)

    result = search_papers(SearchInput(query="attention", max_results=1), tmp_path, opener=openalex_empty)
    assert (result.engine, result.passed_over) == ("arXiv", ["OpenAlex: found nothing"])


def test_says_why_every_engine_failed(tmp_path: Path) -> None:
    down = FakeArxiv(
        down={
            "api.openalex.org": busy(500),
            "export.arxiv.org": TimeoutError("timed out"),
            "api.datacite.org": busy(404),
        }
    )
    with pytest.raises(RuntimeError, match="OpenAlex: HTTP 500; arXiv: timed out; DataCite: HTTP 404"):
        search_papers(SearchInput(query="attention", max_results=1), tmp_path, opener=down)


@pytest.mark.parametrize(("query", "count"), [("  ", 1), ("x", 0), ("x", 51)])
def test_rejects_bad_input(tmp_path: Path, query: str, count: int) -> None:
    with pytest.raises(ValueError):
        search_papers(SearchInput(query=query, max_results=count), tmp_path, opener=FakeArxiv())
