from __future__ import annotations

from pathlib import Path

import pytest
from fakes import FakeArxiv
from slimconfig import build_output, plain_output

import verifier
from contract import TASKS, TOOLS, DownloadInput, FoundPaperOutput, SearchInput, Task, Tool
from plugin import download_source, search_papers


# The verifier gets contract instances, as NanoAgent's sandbox builds them from JSON.
def verify_input(tool: str, value: dict) -> dict:
    return verifier.verify_input(tool, build_output(value, TOOLS[Tool(tool)][0]))


def verify_task(task: str, arguments: dict, output: dict, workspace: Path, reference=None) -> dict:
    given, made = TASKS[Task(task)]
    return verifier.verify_task(
        task, build_output(arguments, given), build_output(output, made), reference, str(workspace)
    )


def test_tool_tasks_judge_their_output_as_their_tool_does(tmp_path: Path) -> None:
    query = {"query": "attention", "max_results": 2}
    found = plain_output(search_papers(SearchInput(**query), tmp_path, opener=FakeArxiv("1706.03762v7")))
    assert verify_task("search-papers", query, found, tmp_path)["valid"] is True
    assert verify_task("search-papers", query | {"query": "other"}, found, tmp_path)["valid"] is False
    given = {"arxiv_id": "1706.03762", "destination": "papers"}
    saved = plain_output(download_source(DownloadInput(**given), tmp_path, opener=FakeArxiv()))
    assert verify_task("save-paper-source", given, saved, tmp_path)["valid"] is True
    assert verify_task("save-paper-source", given | {"destination": "other"}, saved, tmp_path)["valid"] is False
    assert verify_task("save-paper-source", given | {"arxiv_id": "1706.99999"}, saved, tmp_path)["valid"] is False


def found_and_saved(workspace: Path) -> dict:
    found = search_papers(SearchInput(query="attention", max_results=1), workspace, opener=FakeArxiv("1706.03762v7"))
    saved = download_source(DownloadInput(arxiv_id="1706.03762", destination="papers"), workspace, opener=FakeArxiv())
    return plain_output(
        FoundPaperOutput(**plain_output(found.papers[0]), source_url=saved.source_url, folder=saved.folder)
    )


def test_approves_the_found_paper_saved_in_the_destination(tmp_path: Path) -> None:
    request = {"request": "the transformer paper", "destination": "papers"}
    verdict = verify_task("find-and-save-paper", request, found_and_saved(tmp_path), tmp_path)
    assert verdict["valid"] is True


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"folder": "elsewhere"}, "not saved in papers/1706.03762"),
        ({"source_url": "https://export.arxiv.org/src/1706.99999"}, "source_url"),
        ({"abs_url": "https://arxiv.org/abs/1706.99999"}, "abs_url"),
        ({"arxiv_id": "not an id"}, "not an arXiv id"),
    ],
)
def test_refuses_a_found_paper_that_is_not_the_saved_one(tmp_path: Path, changes: dict, message: str) -> None:
    request = {"request": "the transformer paper", "destination": "papers"}
    verdict = verify_task("find-and-save-paper", request, found_and_saved(tmp_path) | changes, tmp_path)
    assert verdict["valid"] is False and message in verdict["message"]
    other = request | {"destination": "elsewhere"}
    assert verify_task("find-and-save-paper", other, found_and_saved(tmp_path / "w"), tmp_path / "w")["valid"] is False


def test_checks_what_the_types_cannot_say() -> None:
    assert verify_input("search_papers", {"query": "attention", "max_results": 5})["valid"] is True
    assert verify_input("search_papers", {"query": " ", "max_results": 5})["valid"] is False
    assert verify_input("search_papers", {"query": "x", "max_results": 51})["valid"] is False
    assert verify_input("download_source", {"arxiv_id": "1706.03762", "destination": "papers"})["valid"] is True
    assert verify_input("download_source", {"arxiv_id": "../x", "destination": "papers"})["valid"] is False
    assert verify_input("download_source", {"arxiv_id": "1706.03762", "destination": "../out"})["valid"] is False
