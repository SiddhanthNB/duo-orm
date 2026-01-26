from __future__ import annotations

import concurrent.futures
from typing import Iterable

import pytest

from duo_orm import Mapped, mapped_column
from tests.conftest import StatementCounter
from tests.test_orm_core import _build_models


@pytest.fixture
def concurrent_models(db, db_target):
    if db_target.is_async:
        pytest.skip("Concurrency stress tests use synchronous engines.")

    User, Post = _build_models(db)
    db.metadata.drop_all(db.sync_engine)
    db.metadata.create_all(db.sync_engine)
    try:
        yield User, Post, db
    finally:
        db.metadata.drop_all(db.sync_engine)


def _run_in_threads(func, payloads: Iterable[int], workers: int = 4):
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(func, payloads))


def test_parallel_writes_and_reads(concurrent_models):
    User, Post, db = concurrent_models

    def writer(idx: int):
        with db.transaction():
            user = User(name=f"user-{idx}", age=idx)
            user.save()
            Post(title=f"post-{idx}", author=user).save()

    _run_in_threads(writer, range(8))

    with StatementCounter(db.sync_engine) as counter:
        users = User.order_by("id").all()
        posts = Post.order_by("id").all()

    assert len(users) == 8
    assert len(posts) == 8
    assert counter.write_count == 0  # read-only queries after writes


def test_concurrent_transactions_isolate_sessions(concurrent_models):
    User, _, db = concurrent_models

    def create_batch(start: int):
        with db.transaction():
            for i in range(start, start + 3):
                User(name=f"batch-{start}-{i}", age=i).save()

    _run_in_threads(create_batch, [0, 100])

    with StatementCounter(db.sync_engine) as counter:
        names = {u.name for u in User.where(User.name.like("batch-%")).all()}

    assert "batch-0-0" in names and "batch-100-100" in names
    assert counter.write_count == 0
