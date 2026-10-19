from __future__ import annotations

import gzip
from pathlib import Path

import pytest
from fakes import Response, tar_bytes

from contract import DownloadInput
from plugin.download import download_source, unpack_source


def test_unpacks_tar_archive(tmp_path: Path) -> None:
    destination = tmp_path / "paper"
    destination.mkdir()
    files = unpack_source(tar_bytes({"main.tex": b"hello", "figures/a.txt": b"a"}), destination)
    assert files == ["figures/a.txt", "main.tex"]
    assert (destination / "main.tex").read_text() == "hello"


def test_unpacks_single_gzip_file(tmp_path: Path) -> None:
    destination = tmp_path / "paper"
    destination.mkdir()
    assert unpack_source(gzip.compress(b"\\documentclass{article}"), destination) == ["main.tex"]


def test_rejects_path_traversal(tmp_path: Path) -> None:
    destination = tmp_path / "paper"
    destination.mkdir()
    with pytest.raises(ValueError, match="unsafe archive path"):
        unpack_source(tar_bytes({"../outside.tex": b"bad"}), destination)


def test_downloads_into_a_folder_named_by_the_arxiv_id(tmp_path: Path) -> None:
    result = download_source(
        DownloadInput(arxiv_id="1706.03762v7", destination="papers"),
        tmp_path,
        opener=lambda request, timeout=None: Response(tar_bytes({"main.tex": b"attention"})),
    )
    assert result.source_url == "https://export.arxiv.org/src/1706.03762v7"
    assert (result.folder, result.files, result.reused) == ("papers/1706.03762v7", ["main.tex"], False)
    assert (tmp_path / "papers" / "1706.03762v7" / "main.tex").read_text() == "attention"


def test_uses_a_source_saved_before_without_asking_arxiv(tmp_path: Path) -> None:
    saved = tmp_path / "papers" / "1706.03762"
    saved.mkdir(parents=True)
    (saved / "kept.tex").write_text("mine")
    result = download_source(
        DownloadInput(arxiv_id="1706.03762", destination="papers"),
        tmp_path,
        opener=lambda request, timeout=None: pytest.fail("a saved source is not downloaded again"),
    )
    assert (result.folder, result.files, result.reused) == ("papers/1706.03762", ["kept.tex"], True)
    assert (saved / "kept.tex").read_text() == "mine"


def test_names_a_legacy_paper_s_folder_without_its_slash(tmp_path: Path) -> None:
    result = download_source(
        DownloadInput(arxiv_id="hep-th/9901001", destination="papers"),
        tmp_path,
        opener=lambda request, timeout=None: Response(tar_bytes({"main.tex": b"x"})),
    )
    assert result.folder == "papers/hep-th_9901001"


def test_rejects_an_invalid_id_or_a_destination_outside_the_workspace(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid"):
        download_source(DownloadInput(arxiv_id="../../secret", destination="bad"), tmp_path)
    with pytest.raises(ValueError, match="workspace"):
        download_source(DownloadInput(arxiv_id="1706.03762", destination="../outside"), tmp_path)


def test_leaves_no_folder_when_the_download_fails(tmp_path: Path) -> None:
    def failing(request, timeout=None):
        raise ConnectionResetError("dropped")

    with pytest.raises(ConnectionResetError):
        download_source(DownloadInput(arxiv_id="1706.03762", destination="papers"), tmp_path, opener=failing)
    assert not (tmp_path / "papers" / "1706.03762").exists()
