"""The find-and-save-paper task's output check: the paper the agent submits is the one it saved."""

import re
from pathlib import Path

from .checks import ARXIV_ID, result

VERSION = re.compile(r"v\d+$")


def verify_task(arguments, output, reference, workspace):
    """``output``: a contract FoundPaperOutput, its source unpacked in the requested destination."""
    paper = output.arxiv_id
    if not ARXIV_ID.fullmatch(paper) or not output.title:
        return result(False, f"{paper!r} is not an arXiv id, or the paper has no title")
    if VERSION.sub("", output.abs_url.rsplit("/abs/", 1)[-1]) != VERSION.sub("", paper):
        return result(False, f"abs_url {output.abs_url} is not paper {paper}'s")
    if output.source_url != f"https://export.arxiv.org/e-print/{paper}":
        return result(False, f"source_url is not paper {paper}'s e-print")
    folder = Path(workspace) / arguments.destination
    if Path(output.folder) != Path(arguments.destination) or not folder.is_dir():
        return result(False, "the source is not saved in the requested destination in the workspace")
    # download_source's own check held its files to the archive; here the folder must hold them.
    files = sum(1 for path in folder.rglob("*") if path.is_file())
    if not files:
        return result(False, "the destination holds no source files")
    return result(True, f"the source of {paper} is saved", files=files)
