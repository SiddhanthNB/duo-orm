from __future__ import annotations

import pytest
from sqlalchemy import Integer, String, inspect, select
from sqlalchemy.orm import Mapped, mapped_column

from duo_orm import Database
from duo_orm.exceptions import ConfigurationError


def test_connect_is_idempotent_and_async_engine_requires_url():
    db = Database("sqlite:///:memory:", derive_async=False)
    db.connect()
    db.connect()
    with pytest.raises(RuntimeError, match="Async engine is not configured"):
        _ = db.async_engine


def test_sync_engine_errors_are_wrapped():
    db = Database("sqlite:///:memory:", derive_async=False)
    db._sync_url = "invaliddialect://"
    with pytest.raises(ConfigurationError, match="Failed to create sync engine"):
        _ = db.sync_engine


def test_async_engine_errors_are_wrapped():
    db = Database("sqlite:///:memory:", derive_async=True)
    db._async_url = "invaliddialect://"
    with pytest.raises(ConfigurationError, match="Failed to create async engine"):
        _ = db.async_engine


def test_sync_engine_requires_configured_url():
    db = Database("sqlite:///:memory:", derive_async=False)
    db._sync_url = None
    with pytest.raises(RuntimeError, match="Sync engine is not configured"):
        _ = db.sync_engine


@pytest.mark.asyncio
async def test_async_create_and_drop_all_helpers():
    db = Database("sqlite:///:memory:", derive_async=True)

    class Item(db.Model):
        __tablename__ = "items_async"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String(50), nullable=False)

    await db.create_all()
    async with db.async_engine.begin() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    assert "items_async" in tables

    await db.drop_all()
    async with db.async_engine.begin() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    assert "items_async" not in tables

    db.disconnect()


@pytest.mark.asyncio
async def test_async_transaction_rolls_back():
    db = Database("sqlite:///:memory:", derive_async=True)

    class Item(db.Model):
        __tablename__ = "items_async_tx"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String(50), nullable=False)

    await db.create_all()

    with pytest.raises(RuntimeError, match="boom"):
        async with db.transaction():
            await Item.create({"name": "first"})
            raise RuntimeError("boom")

    async with db.async_session_factory() as session:
        result = await session.execute(select(Item))
        assert result.scalars().all() == []

    db.disconnect()
