from __future__ import annotations

import pytest

from duo_orm import path
from duo_orm.query import QueryBuilder
from duo_orm.exceptions import InvalidQueryError
from tests.conftest import StatementCounter


def test_path_validation_errors(model_registry):
    User = model_registry.User
    with pytest.raises(ValueError):
        path()  # no relationships
    with pytest.raises(TypeError):
        path(User.name)  # not a relationship
    with pytest.raises(ValueError):
        path(User.posts, loader="bogus")


def test_related_rejects_multiple_positionals(db, model_registry):
    User = model_registry.User
    qb = QueryBuilder(User, db=db)
    with pytest.raises(TypeError):
        qb.related(User.posts, User.posts)  # type: ignore[arg-type]


def test_related_depth_cap(db, model_registry):
    """Paths deeper than the allowed max should raise."""
    UserDepth = model_registry.UserDepth
    A = model_registry.DepthA
    B = model_registry.DepthB
    C = model_registry.DepthC

    qb = QueryBuilder(UserDepth, db=db)
    deep_path = path(UserDepth.a, A.bs, B.cs, C.b)  # depth 4
    with pytest.raises(InvalidQueryError):
        qb.related(deep_path)


def test_related_nested_count_and_query_counts(core_models, model_registry):
    User, Post, db = core_models
    Comment = model_registry.CommentRelated

    with db.transaction():
        u1 = User(name="U1", age=1)
        u1.save()
        p1 = Post(title="p1", author=u1)
        p1.save()
        Comment(post=p1, body="hi").save()
        Comment(post=p1, body="hi2").save()

    with StatementCounter(db.sync_engine) as counter:
        users = (
            User.related(path(User.posts, Post.comments_related), aggregate="count", having=[lambda c: c >= 2])
            .order_by("id")
            .all()
        )
    assert [u.name for u in users] == ["U1"]
    # Expect users + posts + comments (selectin chain) at most 3 selects
    assert counter.select_count <= 3
    assert counter.write_count == 0


def test_related_conflict_same_path(db, model_registry):
    User = model_registry.User
    qb = QueryBuilder(User, db=db)
    qb.related(User.posts, aggregate="count")
    with pytest.raises(InvalidQueryError):
        qb.related(User.posts, aggregate="exists")


def test_related_joined_blocked_on_multihop_collection(db, model_registry):
    User = model_registry.User
    Post = model_registry.Post
    qb = QueryBuilder(User, db=db)
    with pytest.raises(InvalidQueryError):
        qb.related(path(User.posts, Post.author), loader="joined")
