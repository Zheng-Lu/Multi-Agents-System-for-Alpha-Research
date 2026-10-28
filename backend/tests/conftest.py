import pytest
from alpha_mas.providers.registry import Registry
from alpha_mas.storage.sqlite import Store


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "lab.db"))


@pytest.fixture
def registry(monkeypatch):
    from alpha_mas.security import KEY_NAMES

    for name in KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ALPHA_ALLOW_LIVE", raising=False)
    return Registry()
