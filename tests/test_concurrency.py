from __future__ import annotations

import concurrent.futures
from typing import Iterable

from tests.conftest import StatementCounter


def _run_in_threads(func, payloads: Iterable[int], workers: int = 4):
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(func, payloads))


def test_parallel_writes_and_reads(core_models_clean):
    User, Post, db = core_models_clean

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


def test_concurrent_transactions_isolate_sessions(core_models_clean):
    User, _, db = core_models_clean

    def create_batch(start: int):
        with db.transaction():
            for i in range(start, start + 3):
                User(name=f"batch-{start}-{i}", age=i).save()

    _run_in_threads(create_batch, [0, 100])

    with StatementCounter(db.sync_engine) as counter:
        names = {u.name for u in User.where(User.name.like("batch-%")).all()}

    assert "batch-0-0" in names and "batch-100-100" in names
    assert counter.write_count == 0
