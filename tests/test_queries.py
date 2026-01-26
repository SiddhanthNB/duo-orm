from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select, String, Integer, Identity
from sqlalchemy.orm import Session

from duo_orm import Mapped, mapped_column, relationship
from tests.conftest import StatementCounter
from tests.test_orm_core import _build_models


@pytest.fixture
def query_models(db, db_target):
    if db_target.is_async:
        pytest.skip("Complex query coverage runs on sync engines only.")

    User, Post = _build_models(db)
    db.metadata.drop_all(db.sync_engine)
    db.metadata.create_all(db.sync_engine)
    try:
        yield User, Post, db
    finally:
        db.metadata.drop_all(db.sync_engine)


def test_cte_aggregates_and_ordering(query_models):
    User, Post, db = query_models

    with db.transaction():
        alice = User(name="Alice", age=30)
        bob = User(name="Bob", age=25)
        carol = User(name="Carol", age=35)
        alice.save()
        bob.save()
        carol.save()

        Post(title="a1", author=alice).save()
        Post(title="a2", author=alice).save()
        Post(title="b1", author=bob).save()

    with Session(db.sync_engine) as session:
        counts = (
            select(Post.author_id, func.count(Post.id).label("post_count"))
            .group_by(Post.author_id)
            .cte("post_counts")
        )

        results = session.execute(
            select(User.name, counts.c.post_count)
            .join(counts, counts.c.author_id == User.id)
            .order_by(counts.c.post_count.desc(), User.name.asc())
        ).all()

    assert results[0].post_count == 2
    assert {row.name for row in results} == {"Alice", "Bob"}


def test_window_functions_and_multi_join(query_models):
    User, Post, db = query_models

    class Audit(db.Model):
        __tablename__ = "audit_logs"
        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        user_id: Mapped[int] = mapped_column(nullable=False)
        ts: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
        action: Mapped[str] = mapped_column(String(255), nullable=False)

    db.metadata.create_all(db.sync_engine)

    with db.transaction():
        u1 = User(name="Win", age=20)
        u2 = User(name="Row", age=21)
        u1.save()
        u2.save()
        Post(title="p1", author=u1).save()
        Post(title="p2", author=u1).save()
        Post(title="p3", author=u2).save()
        Audit(user_id=u1.id, action="login").save()
        Audit(user_id=u1.id, action="post").save()
        Audit(user_id=u2.id, action="login").save()

    with Session(db.sync_engine) as session, StatementCounter(db.sync_engine) as counter:
        win_row = func.row_number().over(order_by=Audit.id).label("rn")
        stmt = (
            select(User.name, func.count(Post.id).label("post_count"), win_row)
            .join(Post, Post.author_id == User.id)
            .join(Audit, Audit.user_id == User.id)
            .group_by(User.id, User.name, Audit.id)
            .order_by(User.id, win_row)
        )
        rows = session.execute(stmt).all()

    assert counter.write_count == 0
    assert any(r.post_count == 2 for r in rows)
    assert all(r.rn >= 1 for r in rows)
