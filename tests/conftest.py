import pytest

from plugin import arxiv


@pytest.fixture(autouse=True)
def no_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests answer from fakes, so they need not wait between requests as arXiv asks."""
    monkeypatch.setattr(arxiv, "PAUSE", 0.0)
