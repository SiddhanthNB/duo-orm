from __future__ import annotations

import pytest
from sqlalchemy import ARRAY, Integer, String, JSON as SAJSON, Identity, ForeignKey
from sqlalchemy.orm import relationship

from duo_orm import Mapped, mapped_column, path
from duo_orm.query import QueryBuilder, array, json
from duo_orm.exceptions import InvalidQueryError
from tests.test_orm_core import _build_models
from tests.conftest import StatementCounter


def test_json_expression_validation(db):
    User, _ = _build_models(db)

    with pytest.raises(TypeError):
        json(User.name)  # not a JSON column

    class Doc(db.Model):
        __tablename__ = "docs_qh"
        id: Mapped[int] = mapped_column(primary_key=True)
        payload: Mapped[dict] = mapped_column(SAJSON, nullable=False)
        label: Mapped[str] = mapped_column(String(50), nullable=False)

    expr = json(Doc.payload)
    with pytest.raises(TypeError):
        expr[object()]  # invalid path key
    with pytest.raises(TypeError):
        expr.has_key("missing")  # sqlite/json lacks has_key; should raise

    # Basic predicates to cover scalar/dict/list paths (no execution needed)
    _ = expr.equals({"a": 1})
    _ = expr.not_equals({"a": 2})
    _ = expr.equals(1)
    _ = expr.not_equals(2)
    _ = expr.is_null()
    _ = expr.is_not_null()
    _ = expr.as_text().expression(as_text=True)


def test_array_expression_validation_and_values(db):
    User, _ = _build_models(db)
    with pytest.raises(TypeError):
        array(User.name)  # not an ARRAY column

    class Bag(db.Model):
        __tablename__ = "bags_qh"
        id: Mapped[int] = mapped_column(primary_key=True)
        tags: Mapped[list[int]] = mapped_column(ARRAY(Integer))

    expr = array(Bag.tags)
    with pytest.raises(ValueError):
        expr.includes_any(None)
    with pytest.raises(ValueError):
        expr.includes_all([])
    with pytest.raises(ValueError):
        expr._prepare_values(None)


def test_related_error_paths_and_loader(db):
    User, Post = _build_models(db)
    qb = QueryBuilder(User, db=db)

    with pytest.raises(TypeError):
        qb.related(User.name)  # not a relationship

    qb2 = QueryBuilder(User, db=db)
    with pytest.raises(InvalidQueryError):
        qb2.related(Post.author)  # wrong parent model

    qb3 = QueryBuilder(User, db=db)
    with pytest.raises(ValueError):
        qb3.related(User.posts, aggregate="all")  # requires where clause

    qb4 = QueryBuilder(User, db=db)
    with pytest.raises(ValueError):
        qb4.related(User.posts, loader="invalid")  # bad loader option

    qb5 = QueryBuilder(User, db=db)
    with pytest.raises(ValueError):
        qb5.related(User.posts, aggregate="count", order_by="name")  # unsupported order key

    # Loader fallback: selectin on scalar relationship should coerce to joined
    qb_post = QueryBuilder(Post, db=db)
    path = qb_post._resolve_relationship_path(Post.author)
    assert qb_post._determine_loader(path, "selectin") == "joined"


def test_related_conflict_on_same_path(db):
    User, Post = _build_models(db)
    qb = QueryBuilder(User, db=db)
    qb.related(User.posts, loader="selectin")
    with pytest.raises(InvalidQueryError):
        qb.related(User.posts, loader="joined")


def test_related_joined_blocked_on_deep_collection(db):
    User, Post = _build_models(db)
    qb = QueryBuilder(User, db=db)
    with pytest.raises(InvalidQueryError):
        qb.related(path(User.posts, Post.author), loader="joined")


def test_related_chained_siblings_query_counts(db, db_target):
    if db_target.is_async:
        pytest.skip("Query count check uses sync engine.")

    User, Post = _build_models(db)

    class Group(db.Model):
        __tablename__ = "groups_qh"
        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        user_id: Mapped[int] = mapped_column(ForeignKey(f"{User.__tablename__}.id"), nullable=False)
        name: Mapped[str] = mapped_column(String(50), nullable=False)
        user = relationship(User, back_populates="groups_qh")

    # Bind relationship attribute for root model
    User.groups_qh = relationship(Group, back_populates="user")  # type: ignore[attr-defined]

    db.metadata.create_all(db.sync_engine)
    try:
        with db.transaction():
            u = User(name="G", age=1)
            u.save()
            Post(title="p", author=u).save()
            Group(user=u, name="g1").save()

        with StatementCounter(db.sync_engine) as counter:
            fetched = (
                User.related(User.posts, loader="selectin")
                .related(User.groups_qh, loader="selectin")  # sibling path
                .order_by("id")
                .all()
            )

        assert fetched
        # Expect: users + posts + groups -> up to 3 selects
        assert counter.select_count <= 3
        assert counter.write_count == 0
    finally:
        db.metadata.drop_all(db.sync_engine)
