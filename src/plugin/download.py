from __future__ import annotations

import gzip
import io
import re
import shutil
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

from contract import DownloadInput, DownloadOutput
from plugin.arxiv import fetch

ARXIV_ID = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.IGNORECASE)
MAX_DOWNLOAD = 100 * 1024 * 1024
MAX_EXTRACTED = 500 * 1024 * 1024
MAX_FILES = 10_000


def resolve_destination(workspace: Path, destination: str) -> Path:
    """The folder ``destination`` names inside ``workspace``; it may not leave the workspace."""
    relative = Path(destination)
    root = workspace.resolve()
    folder = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or not folder.is_relative_to(root) or folder == root:
        raise ValueError("destination must stay inside the plugin workspace")
    return folder


def workspace_path(workspace: Path, folder: Path) -> str:
    """``folder`` as the plugin's results name it: relative to the workspace, which is the run's own."""
    return folder.relative_to(workspace.resolve()).as_posix()


def _safe_name(name: str) -> Path:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe archive path: {name}")
    return Path(*path.parts)


def _extract_tar(data: bytes, destination: Path) -> list[str]:
    files: list[str] = []
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        members = archive.getmembers()
        if len(members) > MAX_FILES:
            raise ValueError("arXiv source archive contains too many files")
        for member in members:
            relative = _safe_name(member.name)
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported archive entry: {member.name}")
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            total += member.size
            if total > MAX_EXTRACTED:
                raise ValueError("arXiv source archive exceeds the extraction limit")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"could not read archive entry: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())
            files.append(relative.as_posix())
    return sorted(files)


def unpack_source(data: bytes, destination: Path) -> list[str]:
    try:
        return _extract_tar(data, destination)
    except tarfile.ReadError:
        try:
            content = gzip.decompress(data)
        except gzip.BadGzipFile:
            content = data
        if len(content) > MAX_EXTRACTED:
            raise ValueError("arXiv source file exceeds the extraction limit")
        (destination / "main.tex").write_bytes(content)
        return ["main.tex"]


def paper_folder(arxiv_id: str) -> str:
    """The folder name for one paper, its id: legacy IDs (`hep-th/9901001`) contain a slash."""
    return arxiv_id.replace("/", "_")


def save_source(paper: str, folder: Path, workspace: Path, *, opener=urllib.request.urlopen) -> DownloadOutput:
    """Paper ``paper``'s source in ``folder``: what is there already, else downloaded and unpacked."""
    url = f"https://export.arxiv.org/src/{paper}"
    saved = (
        sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file())
        if folder.is_dir()
        else []
    )
    if saved:
        return DownloadOutput(
            arxiv_id=paper, source_url=url, folder=workspace_path(workspace, folder), files=saved, reused=True
        )
    folder.mkdir(parents=True, exist_ok=True)
    try:
        files = unpack_source(fetch(url, limit=MAX_DOWNLOAD, opener=opener), folder)
    except Exception:
        # The folder held nothing, so a failure leaves nothing half unpacked.
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return DownloadOutput(
        arxiv_id=paper, source_url=url, folder=workspace_path(workspace, folder), files=files, reused=False
    )


def download_source(given: DownloadInput, workspace: Path, *, opener=urllib.request.urlopen) -> DownloadOutput:
    """The paper's source in `<destination>/<arxiv id>/`: one saved there before, else downloaded."""
    paper = given.arxiv_id.strip()
    if not ARXIV_ID.fullmatch(paper):
        raise ValueError("invalid arXiv id")
    resolve_destination(workspace, given.destination)
    folder = resolve_destination(workspace, str(Path(given.destination) / paper_folder(paper)))
    return save_source(paper, folder, workspace, opener=opener)
