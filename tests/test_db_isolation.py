from __future__ import annotations

import pytest

from your_orm import Database, Mapped, mapped_column


def test_database_model_isolation():
    db1 = Database("sqlite:///:memory:")
    db2 = Database("sqlite:///:memory:")

    class A(db1.Model):
        __tablename__ = "a"
        id: Mapped[int] = mapped_column(primary_key=True)

    class B(db2.Model):
        __tablename__ = "b"
        id: Mapped[int] = mapped_column(primary_key=True)

    assert A.metadata is not B.metadata
    assert db1.metadata is not db2.metadata


def test_database_derives_async_url_sqlite(tmp_path):
    path = tmp_path / "d.sqlite"
    db = Database(f"sqlite:///{path}", derive_async=True)
    assert db.async_url.startswith("sqlite+aiosqlite")


def test_database_rejects_async_url_as_primary(tmp_path):
    path = tmp_path / "d.sqlite"
    with pytest.raises(ValueError):
        Database(f"sqlite+aiosqlite:///{path}")


def test_database_respects_explicit_async_url(tmp_path):
    sync_path = tmp_path / "s.sqlite"
    async_path = tmp_path / "a.sqlite"
    db = Database(f"sqlite:///{sync_path}", async_url=f"sqlite:///{async_path}")
    assert db.sync_url.endswith(str(sync_path))
    assert db.async_url.startswith("sqlite+aiosqlite")
    assert db.async_url.endswith(str(async_path))


def test_metadata_create_and_drop_all(tmp_path):
    db = Database(f"sqlite:///{tmp_path/'meta.sqlite'}")

    class Extra(db.Model):
        __tablename__ = "extras"
        id: Mapped[int] = mapped_column(primary_key=True)
        note: Mapped[str] = mapped_column(nullable=False)

    # Ensure create_all adds the table
    db.metadata.drop_all(db.sync_engine)
    db.metadata.create_all(db.sync_engine)

    with db.sync_engine.begin() as conn:
        conn.execute(Extra.__table__.insert().values(note="ok"))
        res = conn.execute(Extra.__table__.select()).fetchall()
        assert len(res) == 1

    # Drop and verify gone
    db.metadata.drop_all(db.sync_engine)
    with db.sync_engine.begin() as conn:
        with pytest.raises(Exception):
            conn.execute(Extra.__table__.select())
