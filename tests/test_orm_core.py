
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Tuple

import pytest
import pytest_asyncio
from sqlalchemy import ARRAY, DateTime, ForeignKey, JSON as SAJSON, String, Integer, Identity

from duo_orm import Database, Mapped, array, json, mapped_column, relationship
from duo_orm.exceptions import (
    MultipleObjectsFoundError,
    ObjectNotFoundError,
    ValidationError,
)
from duo_orm.session import active_session_var
from tests.conftest import StatementCounter


def _build_models(db) -> Tuple[type, type]:
    user_table = "duo_users"
    post_table = "duo_posts"

    class User(db.Model):
        __tablename__ = user_table

        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        name: Mapped[str] = mapped_column(String(255), nullable=False)
        age: Mapped[int] = mapped_column(nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            info={"set_on": "create"},
            nullable=True,
        )
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            info={"set_on": {"create", "update"}},
            nullable=True,
        )

        def validate(self):
            if self.age < 0:
                raise ValidationError("age must be non-negative", field="age")

    class Post(db.Model):
        __tablename__ = post_table

        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        title: Mapped[str] = mapped_column(String(255), nullable=False)
        author_id: Mapped[int] = mapped_column(ForeignKey(f"{user_table}.id"), nullable=False)
        author = relationship(User, back_populates="posts")

    User.posts = relationship(Post, back_populates="author", cascade="all, delete-orphan")
    return User, Post


@pytest.fixture
def sync_models(db, db_target):
    User, Post = _build_models(db)
    db.metadata.drop_all(db.sync_engine)
    db.metadata.create_all(db.sync_engine)
    try:
        yield User, Post, db
    finally:
        db.metadata.drop_all(db.sync_engine)


@pytest_asyncio.fixture
async def async_models(async_db):
    User, Post = _build_models(async_db)
    async_db.metadata.drop_all(async_db.sync_engine)
    async_db.metadata.create_all(async_db.sync_engine)
    try:
        yield User, Post, async_db
    finally:
        async_db.metadata.drop_all(async_db.sync_engine)


def test_database_requires_url():
    from duo_orm import Database

    with pytest.raises(ValueError):
        Database("")


def test_sync_save_and_query_roundtrip(sync_models):
    User, Post, db = sync_models

    user = User(name="Alice", age=30)
    user.save()
    Post(title="first", author=user).save()

    fetched = User.where(User.name == "Alice").first()
    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.to_dict()["name"] == "Alice"
    assert User.where(User.id == user.id).exists()
    assert User.where(User.age >= 18).count() == 1

    posts = Post.where(Post.author_id == user.id).all()
    assert len(posts) == 1
    assert posts[0].title == "first"


def test_sync_transaction_rolls_back_on_error(sync_models):
    User, _, db = sync_models

    with pytest.raises(RuntimeError):
        with db.transaction():
            User(name="Temp", age=1).save()
            raise RuntimeError("boom")

    assert User.where(User.name == "Temp").count() == 0


def test_sync_transaction_reuses_session(sync_models):
    User, _, db = sync_models
    with db.transaction():
        token_before = active_session_var.get(None)
        assert token_before is not None
        User(name="Inside", age=50).save()
        assert active_session_var.get(None) is token_before
    assert active_session_var.get(None) is None


def test_bulk_create_update_and_delete(sync_models):
    User, _, _ = sync_models

    users = [
        User(name="u1", age=20),
        User(name="u2", age=25),
        User(name="u3", age=30),
    ]
    User.bulk_create(users)

    User.where(User.age >= 20).update(age=99)
    refreshed = User.order_by("id").all()
    assert [u.age for u in refreshed] == [99, 99, 99]

    User.where(User.age == 99).delete()
    assert User.where(User.age == 99).count() == 0


def test_bulk_create_is_atomic_on_validation_error(sync_models):
    User, _, _ = sync_models

    users = [
        User(name="good", age=20),
        User(name="bad", age=-1),  # will raise
    ]
    with pytest.raises(ValidationError):
        User.bulk_create(users)

    assert User.where(User.name.in_(["good", "bad"])).count() == 0


def test_timestamp_hooks(sync_models):
    User, _, _ = sync_models

    user = User(name="Timey", age=40)
    user.save()

    first_created = user.created_at
    first_updated = user.updated_at
    assert first_created is not None
    assert first_updated is not None

    user.age = 41
    user.save()
    assert user.updated_at is not None
    assert user.updated_at >= first_updated
    assert user.created_at == first_created
    assert user.updated_at - first_updated < timedelta(seconds=5)


def test_order_by_and_paginate(sync_models):
    User, _, _ = sync_models
    users = [User(name=f"p{i}", age=i) for i in range(5)]
    User.bulk_create(users)

    ordered = User.order_by("-age").paginate(limit=2, offset=1).all()
    ages = [u.age for u in ordered]
    assert ages == [3, 2]


def test_validation_hook_blocks_persistence(sync_models):
    User, _, _ = sync_models

    with pytest.raises(ValidationError):
        User(name="Invalid", age=-1).save()


def test_read_only_calls_do_not_write(sync_models):
    User, _, _ = sync_models
    User(name="Probe", age=20).save()

    with StatementCounter(User._db.sync_engine) as counter:
        fetched = User.where(User.name == "Probe").first()
        assert fetched is not None

    assert counter.write_count == 0


def test_session_per_operation_without_transaction(sync_models):
    User, _, db = sync_models

    with StatementCounter(db.sync_engine) as counter:
        User(name="NoTx", age=5).save()
    assert counter.write_count >= 1

    with StatementCounter(db.sync_engine) as counter:
        fetched = User.where(User.name == "NoTx").all()
        assert len(fetched) == 1
    assert counter.write_count == 0


def test_one_raises_for_missing_or_multiple(sync_models):
    User, _, _ = sync_models

    with pytest.raises(ObjectNotFoundError):
        User.where(User.name == "nope").one()

    User.bulk_create([User(name="dup", age=1), User(name="dup", age=2)])
    with pytest.raises(MultipleObjectsFoundError):
        User.where(User.name == "dup").one()


def test_related_helpers(sync_models):
    User, Post, db = sync_models

    alice = User(name="Alice", age=30)
    bob = User(name="Bob", age=31)

    with db.transaction():
        alice.save()
        bob.save()
        Post(title="a1", author=alice).save()
        Post(title="a2", author=alice).save()
        Post(title="b1", author=bob).save()

    with_posts = User.related(User.posts, aggregate="exists").where(User.name == "Alice").all()
    assert [u.name for u in with_posts] == ["Alice"]

    at_least_two = User.related(
        User.posts,
        aggregate="count",
        having=[lambda count_expr: count_expr >= 2],
        order_by="-count",
    ).all()
    assert [u.name for u in at_least_two] == ["Alice"]


def test_related_all_aggregate(sync_models):
    User, Post, db = sync_models

    with db.transaction():
        alice = User(name="Alice", age=30)
        bob = User(name="Bob", age=31)
        alice.save()
        bob.save()
        Post(title="ok", author=alice).save()
        Post(title="ok2", author=alice).save()
        Post(title="bad", author=bob).save()

    ok_only = User.related(
        User.posts,
        aggregate="all",
        where=[Post.title.icontains("ok")],
    ).order_by("name").all()

    assert [u.name for u in ok_only] == ["Alice"]


def test_related_does_not_nplus_one(sync_models):
    User, Post, db = sync_models

    with db.transaction():
        users = [User(name=f"U{i}", age=20 + i) for i in range(3)]
        for user in users:
            user.save()
            Post(title=f"p1-{user.name}", author=user).save()
            Post(title=f"p2-{user.name}", author=user).save()

    with StatementCounter(db.sync_engine) as counter:
        fetched = User.related(User.posts, loader="selectin").order_by("id").all()

    assert len(fetched) == 3
    # selectin should emit 2 queries: one for users, one for related posts
    assert counter.select_count <= 2
    assert counter.write_count == 0


def test_related_joined_loader_single_query(sync_models):
    User, Post, db = sync_models

    with db.transaction():
        owner = User(name="owner", age=25)
        owner.save()
        Post(title="p1", author=owner).save()
        Post(title="p2", author=owner).save()

    with StatementCounter(db.sync_engine) as counter:
        fetched = User.related(User.posts, loader="joined").all()

    assert len(fetched) == 1
    assert counter.select_count == 1


def test_delete_cascades_to_children(sync_models):
    User, Post, db = sync_models

    parent = User(name="Parent", age=40)
    Post(title="child1", author=parent)
    Post(title="child2", author=parent)

    parent.save()

    with db.transaction():
        parent.delete()

    assert Post.where(Post.author_id == parent.id).count() == 0


@pytest.mark.asyncio
async def test_async_crud_roundtrip(async_models):
    User, Post, db = async_models

    async with db.transaction():
        user = User(name="Async Alice", age=28)
        await user.save()
        await Post(title="async post", author=user).save()

    fetched = await User.where(User.name == "Async Alice").first()
    assert fetched is not None
    assert fetched.id is not None

    posts = await Post.where(Post.author_id == fetched.id).all()
    assert len(posts) == 1
    assert posts[0].title == "async post"


@pytest.mark.asyncio
async def test_async_transaction_reuses_session_and_resets(async_models):
    User, _, db = async_models

    async with db.transaction():
        session_inside = active_session_var.get(None)
        assert session_inside is not None
        user = User(name="TxUser", age=33)
        await user.save()
        assert await User.where(User.id == user.id).exists()
        assert active_session_var.get(None) is session_inside

    assert active_session_var.get(None) is None


@pytest.mark.asyncio
async def test_async_read_only_calls_do_not_write(async_models):
    User, _, db = async_models
    await User(name="AsyncProbe", age=22).save()

    with StatementCounter(db.async_engine) as counter:
        fetched = await User.where(User.name == "AsyncProbe").first()
        assert fetched is not None

    assert counter.write_count == 0


@pytest.mark.asyncio
async def test_async_session_per_operation_without_transaction(async_models):
    User, _, db = async_models

    with StatementCounter(db.async_engine) as counter:
        await User(name="AsyncNoTx", age=7).save()
    assert counter.write_count >= 1

    with StatementCounter(db.async_engine) as counter:
        fetched = await User.where(User.name == "AsyncNoTx").all()
        assert len(fetched) == 1
    assert counter.write_count == 0


def test_json_helper_requires_json_column(sync_models):
    User, _, _ = sync_models

    with pytest.raises(TypeError):
        json(User.name)


def test_array_helper_requires_array_column(sync_models):
    User, _, _ = sync_models

    with pytest.raises(TypeError):
        array(User.name)


def test_related_cannot_be_chained(sync_models):
    User, Post, _ = sync_models
    with pytest.raises(ValueError):
        User.related(User.posts).related(User.posts)


def test_order_by_invalid_field_raises(sync_models):
    User, _, _ = sync_models
    with pytest.raises(AttributeError):
        User.order_by("does_not_exist").all()


def test_standalone_session_does_not_set_contextvar(sync_models):
    User, _, db = sync_models
    User(name="Solo", age=10).save()

    assert active_session_var.get(None) is None

    with db.sync_standalone_session() as session:
        result = session.execute(User.where(User.name == "Solo").alchemize())
        assert result.scalars().first() is not None
        assert active_session_var.get(None) is None


def test_json_helpers_on_supported_dialect(db_target):
    if db_target.is_async or not db_target.supports_json:
        pytest.skip("Dialect does not support JSON operations in sync mode.")

    db = Database(db_target.url)

    class Doc(db.Model):
        __tablename__ = "docs"
        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        profile: Mapped[dict] = mapped_column(SAJSON, nullable=False)

    db.metadata.create_all(db.sync_engine)
    try:
        Doc(profile={"flags": {"beta": True}, "tags": ["orm"], "quota": 2}).save()
        Doc(profile={"flags": {"beta": False}, "tags": ["other"], "quota": 0}).save()

        beta = Doc.where(json(Doc.profile)["flags"]["beta"].is_true()).all()
        assert len(beta) == 1

        flags_expr = json(Doc.profile)["flags"]
        has_key_op = getattr(flags_expr._json_expr(), "has_key", None)
        if db_target.supports_has_key and has_key_op is not None:
            has_key = Doc.where(flags_expr.has_key("beta")).count()
            assert has_key == 2

        not_beta = Doc.where(json(Doc.profile)["flags"]["beta"].is_false()).all()
        assert len(not_beta) == 1

        quota_two = Doc.where(json(Doc.profile)["quota"].as_integer() == 2).all()
        assert len(quota_two) == 1

        is_null = Doc.where(json(Doc.profile)["missing"].is_null()).count()
        assert is_null == 2

        not_equals = Doc.where(json(Doc.profile)["quota"].not_equals(0)).count()
        assert not_equals == 1
    finally:
        db.metadata.drop_all(db.sync_engine)


def test_array_helpers_on_supported_dialect(db_target):
    if db_target.is_async or not db_target.supports_array:
        pytest.skip("Dialect does not support ARRAY columns in sync mode.")

    db = Database(db_target.url)

    try:
        from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY  # type: ignore
    except Exception:
        pytest.skip("PostgreSQL ARRAY type not available.")

    class Item(db.Model):
        __tablename__ = "items"
        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        tags: Mapped[list[str]] = mapped_column(PG_ARRAY(String), nullable=False)

    db.metadata.create_all(db.sync_engine)
    try:
        Item(tags=["python", "orm"]).save()
        Item(tags=["sql"]).save()

        overlap_op = getattr(array(Item.tags)._array_expr(), "overlap", None)
        if overlap_op is not None:
            match_any = Item.where(array(Item.tags).includes_any(["python", "async"])).all()
            assert len(match_any) == 1

        match_all = Item.where(array(Item.tags).includes_all(["python", "orm"])).all()
        assert len(match_all) == 1

        eq = Item.where(array(Item.tags).equals(["python", "orm"])).count()
        assert eq == 1

        neq = Item.where(array(Item.tags).not_equals(["sql"])).count()
        assert neq == 1

        length_check = Item.where(array(Item.tags).length() >= 1).count()
        assert length_check == 2
    finally:
        db.metadata.drop_all(db.sync_engine)
