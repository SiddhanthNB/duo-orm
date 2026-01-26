import pytest

from duo_orm import Database


def test_rejects_driver_in_url():
    with pytest.raises(ValueError, match="Do not include driver"):
        Database("postgresql+psycopg://user:pass@localhost/db")


def test_rejects_unknown_dialect():
    with pytest.raises(ValueError, match="Unsupported or unknown dialect"):
        Database("foo://user:pass@localhost/db")


def test_async_url_must_match_primary():
    with pytest.raises(ValueError, match="async_url dialect must match"):
        Database("postgresql://user:pass@localhost/db", async_url="mysql://user:pass@localhost/db")


def test_async_engine_requires_url_when_not_derived():
    db = Database("sqlite:///:memory:", derive_async=False)
    with pytest.raises(RuntimeError):
        _ = db.async_engine


def test_sync_engine_typeerror_hints(monkeypatch):
    db = Database("sqlite:///./db.sqlite?bad=1")

    def boom(*args, **kwargs):
        raise TypeError("boom")

    monkeypatch.setattr("duo_orm.db.create_engine", boom)
    with pytest.raises(TypeError) as excinfo:
        _ = db.sync_engine
    assert "bad" in str(excinfo.value)
