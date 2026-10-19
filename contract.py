"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    SEARCH_PAPERS = "search_papers"
    DOWNLOAD_SOURCE = "download_source"


class Task(Enum):
    SEARCH_PAPERS = "search-papers"
    SAVE_PAPER_SOURCE = "save-paper-source"
    FIND_AND_SAVE_PAPER = "find-and-save-paper"


QUERY = "The paper in plain words: its title, topic or authors, e.g. attention is all you need vaswani"
DESTINATION = (
    "The folder relative to the plugin workspace that papers are saved in, e.g. papers: a paper's source"
    " goes in <destination>/<arxiv id>, and one saved there before is used again"
)
ARXIV_ID = "The arXiv identifier, without a version"
TITLE = "The title, as the search engine lists it"
AUTHORS = "The authors' names, as the search engine lists them, in order"
SUMMARY = "The abstract, as the search engine lists it; empty when it has none"
PUBLISHED = "When it was published, YYYY-MM-DD, as the search engine lists it; empty when it has no date"
ABS_URL = "The paper's arXiv abstract page"
SOURCE_URL = "The arXiv URL the source archive came from, export.arxiv.org/src/<arxiv id>"
FOLDER = "The folder the source is in, <destination>/<arxiv id>, relative to the plugin workspace"
FILES = "The unpacked files, relative to the folder"


@dataclass
class Paper(Output):
    arxiv_id: Annotated[str, ARXIV_ID]
    title: Annotated[str, TITLE]
    authors: Annotated[list[str], AUTHORS]
    summary: Annotated[str, SUMMARY]
    published: Annotated[str, PUBLISHED]
    abs_url: Annotated[str, ABS_URL]


@dataclass
class FoundPaperOutput(Output):
    # What the agent submits: the paper it picked, and where download_source saved it. Not the
    # files: download_source's own check holds them, and a long list is no list to retype.
    arxiv_id: Annotated[str, ARXIV_ID]
    title: Annotated[str, TITLE]
    authors: Annotated[list[str], AUTHORS]
    summary: Annotated[str, SUMMARY]
    published: Annotated[str, PUBLISHED]
    abs_url: Annotated[str, ABS_URL]
    source_url: Annotated[str, SOURCE_URL]
    folder: Annotated[str, FOLDER]


@dataclass
class SearchInput(Output):
    query: Annotated[str, QUERY]
    max_results: Annotated[int, "How many papers to return, best match first, 1 to 50"]


@dataclass
class SearchOutput(Output):
    query: Annotated[str, "The query, as given without surrounding spaces"]
    engine: Annotated[str, "The search engine the papers came from: OpenAlex, arXiv or DataCite, the first to find any"]
    passed_over: Annotated[
        list[str], "Each engine asked before it, and why it found none: it failed, was slow or found nothing"
    ]
    source_url: Annotated[str, "The engine's request the papers came from"]
    papers: Annotated[list[Paper], "The matching papers on arXiv, best match first"]


@dataclass
class DownloadInput(Output):
    arxiv_id: Annotated[str, "A modern or legacy arXiv identifier, optionally with a version"]
    destination: Annotated[str, DESTINATION]


@dataclass
class DownloadOutput(Output):
    arxiv_id: Annotated[str, "The arXiv identifier, as given without surrounding spaces"]
    source_url: Annotated[str, SOURCE_URL]
    folder: Annotated[str, FOLDER]
    files: Annotated[list[str], FILES]
    reused: Annotated[bool, "Whether the source was in the folder already, so nothing was downloaded"]


@dataclass
class FindInput(Output):
    request: Annotated[str, "The paper in the person's words: its title, topic, authors, year or arXiv id"]
    destination: Annotated[str, DESTINATION]


TOOLS = {
    Tool.SEARCH_PAPERS: (SearchInput, SearchOutput),
    Tool.DOWNLOAD_SOURCE: (DownloadInput, DownloadOutput),
}
TASKS = {
    Task.SEARCH_PAPERS: (SearchInput, SearchOutput),
    Task.SAVE_PAPER_SOURCE: (DownloadInput, DownloadOutput),
    Task.FIND_AND_SAVE_PAPER: (FindInput, FoundPaperOutput),
}
