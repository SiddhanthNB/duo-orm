from __future__ import annotations

import asyncio

from duo_orm.session import is_async_context


def test_is_async_context_sync_returns_false():
    assert is_async_context() is False


def test_is_async_context_async_returns_true():
    async def _probe():
        return is_async_context()

    result = asyncio.run(_probe())
    assert result is True
