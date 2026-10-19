"""search_papers: papers on arXiv and their arXiv ids, from the first of ENGINES to answer.

OpenAlex is asked first, so that arXiv is asked as little as it can be, then arXiv's own search,
then DataCite, which registers arXiv's DOIs. Each has WAIT seconds to answer; one that fails,
does not answer in time or finds nothing is passed over for the next, and the result says which
answered and why each before it did not.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree

from contract import Paper, SearchInput, SearchOutput
from plugin.arxiv import fetch

MAX_RESULTS = 50
WAIT = 1.0  # seconds each engine has to answer before the next is asked
HEADERS = {"User-Agent": "nanoagent-arxiv-source"}
# An arXiv id, or its abstract or PDF page, in the query: that paper alone.
GIVEN_ID = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/)?\b(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?\b", re.IGNORECASE
)
VERSION = re.compile(r"v\d+$")
# What passes an engine over: it failed, did not answer in time, or answered what cannot be read.
PASSED_OVER = (OSError, RuntimeError, ValueError, KeyError, TypeError, ElementTree.ParseError)

Engine = Callable[[str | None, str, int, Callable], tuple[str, list[Paper]]]


def _json(url: str, opener) -> dict:
    with opener(urllib.request.Request(url, headers=HEADERS), timeout=WAIT) as response:
        return json.loads(response.read())


def _paper(arxiv_id: str, title: str, authors: list[str], summary: str, published: str) -> Paper:
    arxiv_id = VERSION.sub("", arxiv_id)
    return Paper(
        arxiv_id=arxiv_id,
        title=" ".join(title.split()),
        authors=authors,
        summary=" ".join(summary.split()),
        published=published,
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
    )


# OpenAlex, its works on arXiv (the source S4306400194), each with its arXiv abstract page.
OPENALEX = "https://api.openalex.org/works"
OPENALEX_FIELDS = "title,authorships,publication_date,abstract_inverted_index,locations"
ARXIV_SOURCE = "S4306400194"
ABS_PAGE = re.compile(r"^https?://arxiv\.org/abs/(.+)$")


def _openalex_paper(work: dict) -> Paper:
    pages = [
        ABS_PAGE.match(location.get("landing_page_url") or "")
        for location in work["locations"]
        if (location.get("source") or {}).get("id", "").endswith(f"/{ARXIV_SOURCE}")
    ]
    pages = [page for page in pages if page]
    if not pages:
        raise ValueError(f"OpenAlex lists {work['title']!r} on arXiv without its arXiv abstract page")
    index = work["abstract_inverted_index"] or {}
    words = sorted((position, word) for word, positions in index.items() for position in positions)
    authors = [authorship["author"]["display_name"] for authorship in work["authorships"]]
    summary = " ".join(word for _, word in words)
    return _paper(pages[0][1], work["title"] or "", authors, summary, work["publication_date"])


def openalex(arxiv_id: str | None, text: str, count: int, opener) -> tuple[str, list[Paper]]:
    if arxiv_id:
        # arXiv gives every paper the DOI 10.48550/arXiv.<id>.
        url = f"{OPENALEX}/doi:10.48550/arXiv.{arxiv_id}?{urllib.parse.urlencode({'select': OPENALEX_FIELDS})}"
        return url, [_openalex_paper(_json(url, opener))]
    params = {
        "search": text,
        "filter": f"locations.source.id:{ARXIV_SOURCE}",
        "per-page": count,
        "select": OPENALEX_FIELDS,
    }
    url = f"{OPENALEX}?{urllib.parse.urlencode(params)}"
    return url, [_openalex_paper(work) for work in _json(url, opener)["results"]]


# arXiv's own search, one try: when it limits this computer it fails at once (plugin.arxiv).
ARXIV = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
MAX_FEED = 10 * 1024 * 1024


def _atom(entry: ElementTree.Element, tag: str) -> str:
    return entry.findtext(f"{ATOM}{tag}") or ""


# Words arXiv's search leaves out of its index, which no title then holds.
STOP_WORDS = {"a", "all", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "no", "not"}
STOP_WORDS |= {"of", "on", "or", "that", "the", "this", "to", "we", "with", "you"}


def arxiv(arxiv_id: str | None, text: str, count: int, opener) -> tuple[str, list[Paper]]:
    if arxiv_id:
        params = {"id_list": arxiv_id, "max_results": 1}
    else:
        # The title, or a title holding every other word of the query.
        words = [word for word in re.findall(r"\w+", text) if word.lower() not in STOP_WORDS]
        phrase = " ".join(re.findall(r"\w+", text))
        query = f'ti:"{phrase}"' + (f" OR ({' AND '.join(f'ti:{word}' for word in words)})" if words else "")
        params = {"search_query": query, "max_results": count}
    url = f"{ARXIV}?{urllib.parse.urlencode(params)}"
    feed = ElementTree.fromstring(fetch(url, limit=MAX_FEED, opener=opener, attempts=1, timeout=WAIT))
    papers = []
    for entry in feed.findall(f"{ATOM}entry"):
        page = _atom(entry, "id")
        if "/abs/" not in page:
            # A rejected query is one entry whose id is arXiv's error page.
            raise ValueError(f"arXiv rejected the query: {' '.join(_atom(entry, 'summary').split())}")
        authors = [" ".join(name.text.split()) for name in entry.findall(f"{ATOM}author/{ATOM}name") if name.text]
        published = _atom(entry, "published")[:10]
        papers.append(
            _paper(page.rsplit("/abs/", 1)[1], _atom(entry, "title"), authors, _atom(entry, "summary"), published)
        )
    return url, papers


# DataCite, which registers each arXiv paper's DOI, 10.48550/arXiv.<id>, with its metadata.
DATACITE = "https://api.datacite.org/dois"


def _datacite_paper(record: dict) -> Paper:
    found = record["attributes"]
    doi = found["doi"]
    if not doi.lower().startswith("10.48550/arxiv."):
        raise ValueError(f"DataCite's {doi} is not an arXiv DOI")
    authors = [
        f"{creator['givenName']} {creator['familyName']}" if creator.get("givenName") else creator["name"]
        for creator in found["creators"]
    ]
    descriptions = found.get("descriptions") or []
    abstracts = [part["description"] for part in descriptions if part.get("descriptionType") == "Abstract"]
    submitted = [date["date"] for date in found.get("dates") or [] if date.get("dateType") == "Submitted"]
    summary = abstracts[0] if abstracts else ""
    return _paper(
        doi.split(".", 2)[2], found["titles"][0]["title"], authors, summary, min(submitted)[:10] if submitted else ""
    )


def datacite(arxiv_id: str | None, text: str, count: int, opener) -> tuple[str, list[Paper]]:
    if arxiv_id:
        url = f"{DATACITE}/10.48550/arXiv.{arxiv_id}"
        return url, [_datacite_paper(_json(url, opener)["data"])]
    params = {"query": text, "prefix": "10.48550", "sort": "relevance", "page[size]": count}
    url = f"{DATACITE}?{urllib.parse.urlencode(params)}"
    return url, [_datacite_paper(record) for record in _json(url, opener)["data"]]


ENGINES: tuple[tuple[str, Engine], ...] = (("OpenAlex", openalex), ("arXiv", arxiv), ("DataCite", datacite))


def search_papers(given: SearchInput, workspace: Path, *, opener=urllib.request.urlopen) -> SearchOutput:
    """The papers on arXiv matching ``given.query``, best match first: the one paper whose arXiv id
    (or abstract or PDF page) it names, else the best matches for its words, from the first engine
    to answer with any."""
    text = given.query.strip()
    if not text:
        raise ValueError("query must not be empty")
    if not 1 <= given.max_results <= MAX_RESULTS:
        raise ValueError(f"max_results must be between 1 and {MAX_RESULTS}")
    named = GIVEN_ID.search(text)
    arxiv_id = named[1] if named else None
    passed: list[str] = []
    for name, engine in ENGINES:
        try:
            url, found = engine(arxiv_id, text, given.max_results, opener)
        except urllib.error.HTTPError as error:
            passed.append(f"{name}: HTTP {error.code}")
            continue
        except PASSED_OVER as error:
            passed.append(f"{name}: {error or type(error).__name__}")
            continue
        papers: list[Paper] = []
        for paper in found:
            # A paper an engine lists twice (as preprint and as published work) is one paper.
            if all(paper.arxiv_id != seen.arxiv_id for seen in papers):
                papers.append(paper)
        if papers:
            return SearchOutput(
                query=text, engine=name, passed_over=passed, source_url=url, papers=papers[: given.max_results]
            )
        passed.append(f"{name}: found nothing")
    raise RuntimeError(f"no search engine found {text!r}: {'; '.join(passed)}")
