from __future__ import annotations

from sqlalchemy import func, select

from tests.conftest import StatementCounter


def test_cte_aggregates_and_ordering(core_models):
    User, Post, db = core_models

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

    with db.sync_standalone_session() as session:
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


def test_window_functions_and_multi_join(core_models, model_registry):
    User, Post, db = core_models
    Audit = model_registry.Audit

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

    with db.sync_standalone_session() as session, StatementCounter(db.sync_engine) as counter:
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
