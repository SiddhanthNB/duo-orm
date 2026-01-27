import pytest

from duo_orm import Database
from duo_orm.exceptions import ConfigurationError


def test_rejects_driver_in_url():
    with pytest.raises(ConfigurationError, match="Do not include"):
        Database("postgresql+psycopg://user:pass@localhost/db")


def test_rejects_unknown_dialect():
    with pytest.raises(ConfigurationError, match="Unsupported or unknown dialect"):
        Database("foo://user:pass@localhost/db")


def test_async_url_must_match_primary():
    with pytest.raises(ConfigurationError, match="async_url dialect must match"):
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
    with pytest.raises(ConfigurationError) as excinfo:
        _ = db.sync_engine
    assert "bad" in str(excinfo.value)


def test_explicit_dialect_mismatch():
    with pytest.raises(ConfigurationError, match="Dialect mismatch"):
        Database("postgresql://user:pass@localhost/db", dialect="mysql")


def test_explicit_dialect_alias_allowed():
    # postgres alias should normalize to postgresql
    db = Database("postgresql://user:pass@localhost/db", dialect="postgres")
    assert db.sync_url.startswith("postgresql+psycopg://")


def test_explicit_dialect_unknown_value():
    with pytest.raises(ConfigurationError, match="Unknown dialect 'cockroach'"):
        Database("postgresql://user:pass@localhost/db", dialect="cockroach")
