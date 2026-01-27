from __future__ import annotations

import pytest
from sqlalchemy import ForeignKey, Integer, Identity, String
from sqlalchemy.orm import relationship

from duo_orm import Mapped, mapped_column, path
from duo_orm.query import QueryBuilder
from duo_orm.exceptions import InvalidQueryError
from tests.conftest import StatementCounter
from tests.test_orm_core import _build_models


def test_path_validation_errors(db):
    User, _ = _build_models(db)
    with pytest.raises(ValueError):
        path()  # no relationships
    with pytest.raises(TypeError):
        path(User.name)  # not a relationship
    with pytest.raises(ValueError):
        path(User.posts, loader="bogus")


def test_related_rejects_multiple_positionals(db):
    User, _ = _build_models(db)
    qb = QueryBuilder(User, db=db)
    with pytest.raises(TypeError):
        qb.related(User.posts, User.posts)  # type: ignore[arg-type]


def test_related_depth_cap(db):
    """Paths deeper than the allowed max should raise."""
    class A(db.Model):
        __tablename__ = "a_depth"
        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        users = relationship("UserDepth", back_populates="a")

    class B(db.Model):
        __tablename__ = "b_depth"
        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        a_id: Mapped[int] = mapped_column(ForeignKey("a_depth.id"))
        a = relationship(A, back_populates="bs")

    class C(db.Model):
        __tablename__ = "c_depth"
        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        b_id: Mapped[int] = mapped_column(ForeignKey("b_depth.id"))
        b = relationship(B, back_populates="cs")

    class UserDepth(db.Model):
        __tablename__ = "user_depth"
        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        a_id: Mapped[int] = mapped_column(ForeignKey("a_depth.id"))
        a = relationship(A, back_populates="users")

    A.bs = relationship(B, back_populates="a")  # type: ignore[attr-defined]
    B.cs = relationship(C, back_populates="b")  # type: ignore[attr-defined]

    db.metadata.create_all(db.sync_engine)
    try:
        qb = QueryBuilder(UserDepth, db=db)
        deep_path = path(UserDepth.a, A.bs, B.cs, C.b)  # depth 4
        with pytest.raises(InvalidQueryError):
            qb.related(deep_path)
    finally:
        db.metadata.drop_all(db.sync_engine)


def test_related_nested_count_and_query_counts(db, db_target):
    if db_target.is_async:
        pytest.skip("Sync query count check.")
    User, Post = _build_models(db)

    class Comment(db.Model):
        __tablename__ = "comments_related"
        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        post_id: Mapped[int] = mapped_column(ForeignKey(f"{Post.__tablename__}.id"), nullable=False)
        body: Mapped[str] = mapped_column(String(100), nullable=False)
        post = relationship(Post, backref="comments_related")

    db.metadata.create_all(db.sync_engine)
    try:
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
    finally:
        db.metadata.drop_all(db.sync_engine)


def test_related_conflict_same_path(db):
    User, _ = _build_models(db)
    qb = QueryBuilder(User, db=db)
    qb.related(User.posts, aggregate="count")
    with pytest.raises(InvalidQueryError):
        qb.related(User.posts, aggregate="exists")


def test_related_joined_blocked_on_multihop_collection(db):
    User, Post = _build_models(db)
    qb = QueryBuilder(User, db=db)
    with pytest.raises(InvalidQueryError):
        qb.related(path(User.posts, Post.author), loader="joined")
