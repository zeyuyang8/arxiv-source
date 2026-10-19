from __future__ import annotations

import io
import json
import tarfile
from urllib.request import Request


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def tar_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def work(arxiv_id: str) -> dict:
    """OpenAlex's record of the paper ``arxiv_id`` on arXiv, which is also at a journal."""
    return {
        "title": f"Paper {arxiv_id}",
        "authorships": [{"author": {"display_name": "Ashish Vaswani"}}, {"author": {"display_name": "Noam Shazeer"}}],
        "publication_date": "2017-06-12",
        "abstract_inverted_index": {"An": [0], "abstract.": [1]},
        "locations": [
            {"source": {"id": "https://openalex.org/S1"}, "landing_page_url": "https://doi.org/10.1/x"},
            {
                "source": {"id": "https://openalex.org/S4306400194"},
                "landing_page_url": f"http://arxiv.org/abs/{arxiv_id}",
            },
        ],
    }


FEED = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>"""
ENTRY = """<entry><id>http://arxiv.org/abs/{arxiv_id}</id><title>Paper {arxiv_id}
  Wrapped</title><summary> An abstract. </summary><published>2017-06-12T17:57:34Z</published>
  <author><name>Ashish Vaswani</name></author></entry>"""


def record(arxiv_id: str) -> dict:
    """DataCite's record of the paper ``arxiv_id``'s arXiv DOI."""
    return {
        "attributes": {
            "doi": f"10.48550/arxiv.{arxiv_id}",
            "titles": [{"title": f"Paper {arxiv_id}"}],
            "creators": [{"name": "Vaswani, Ashish", "givenName": "Ashish", "familyName": "Vaswani"}],
            "descriptions": [{"description": "An abstract.", "descriptionType": "Abstract"}],
            "dates": [
                {"date": "2017-06-19T16:49:45Z", "dateType": "Submitted"},
                {"date": "2017-06-12T17:57:34Z", "dateType": "Submitted"},
            ],
        }
    }


class FakeArxiv:
    """Answers each search engine (OpenAlex, arXiv, DataCite), searching or looking up one paper,
    with ``arxiv_ids``, but those named in ``down``, which fail; and every arXiv source with a
    one-file archive."""

    def __init__(self, *arxiv_ids: str, down: dict[str, Exception] | None = None) -> None:
        self.arxiv_ids = arxiv_ids
        self.down = down or {}
        self.urls: list[str] = []

    def __call__(self, request: Request, timeout: float | None = None) -> Response:
        url = request.full_url
        self.urls.append(url)
        for host, error in self.down.items():
            if url.startswith(f"https://{host}/"):
                raise error
        if url.startswith("https://api.openalex.org/works/doi:10.48550/arXiv."):
            return Response(json.dumps(work(url.split("arXiv.", 1)[1].split("?", 1)[0])).encode())
        if url.startswith("https://api.openalex.org/works?"):
            return Response(json.dumps({"results": [work(paper) for paper in self.arxiv_ids]}).encode())
        if url.startswith("https://export.arxiv.org/api/query?id_list="):
            paper = url.split("id_list=", 1)[1].split("&", 1)[0].replace("%2F", "/")
            return Response(FEED.format(entries=ENTRY.format(arxiv_id=paper)).encode())
        if url.startswith("https://export.arxiv.org/api/query?"):
            return Response(
                FEED.format(entries="".join(ENTRY.format(arxiv_id=paper) for paper in self.arxiv_ids)).encode()
            )
        if url.startswith("https://api.datacite.org/dois/10.48550/arXiv."):
            return Response(json.dumps({"data": record(url.split("arXiv.", 1)[1])}).encode())
        if url.startswith("https://api.datacite.org/dois?"):
            return Response(json.dumps({"data": [record(paper) for paper in self.arxiv_ids]}).encode())
        paper = url.rsplit("/src/", 1)[1]
        return Response(tar_bytes({"main.tex": paper.encode()}))
