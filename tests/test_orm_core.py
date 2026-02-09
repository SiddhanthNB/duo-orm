
from __future__ import annotations

from datetime import timedelta

import pytest

from duo_orm import array, json, path
from duo_orm.exceptions import (
    MultipleObjectsFoundError,
    ObjectNotFoundError,
    ValidationError,
    InvalidQueryError,
)
from duo_orm.session import active_session_var
from tests.conftest import StatementCounter


def test_database_requires_url():
    from duo_orm import Database

    with pytest.raises(ValueError, match="Database URL cannot be empty"):
        Database("")


def test_first_on_existing_record_returns_instance(core_models):
    User, _, _ = core_models

    user = User(name="Alice", age=30)
    user.save()

    fetched = User.where(User.name == "Alice").first()
    assert fetched is not None
    assert fetched.id == user.id


def test_to_dict_returns_correct_data(core_models):
    User, _, _ = core_models

    user = User(name="Alice", age=30)
    user.save()

    payload = user.to_dict()
    assert payload["name"] == "Alice"
    assert payload["age"] == 30


def test_exists_on_existing_record_returns_true(core_models):
    User, _, _ = core_models

    user = User(name="Alice", age=30)
    user.save()

    assert User.where(User.id == user.id).exists()


def test_count_on_single_record_returns_one(core_models):
    User, _, _ = core_models

    User(name="Alice", age=30).save()
    assert User.where(User.age >= 18).count() == 1


def test_related_query_returns_children(core_models):
    User, Post, _ = core_models

    user = User(name="Alice", age=30)
    user.save()
    Post(title="first", author=user).save()

    posts = Post.where(Post.author_id == user.id).all()
    assert len(posts) == 1
    assert posts[0].title == "first"


def test_sync_transaction_rolls_back_on_error(core_models):
    User, _, db = core_models

    with pytest.raises(RuntimeError, match="boom"):
        with db.transaction():
            User(name="Temp", age=1).save()
            raise RuntimeError("boom")

    assert User.where(User.name == "Temp").count() == 0


def test_sync_transaction_reuses_session(core_models):
    User, _, db = core_models
    with db.transaction():
        token_before = active_session_var.get(None)
        assert token_before is not None
        User(name="Inside", age=50).save()
        assert active_session_var.get(None) is token_before
    assert active_session_var.get(None) is None


def test_bulk_create_inserts_rows(core_models):
    User, _, _ = core_models

    users = [
        User(name="u1", age=20),
        User(name="u2", age=25),
        User(name="u3", age=30),
    ]
    User.create_bulk(users)
    assert User.count() == 3


def test_bulk_update_updates_matching_rows(core_models):
    User, _, _ = core_models

    users = [
        User(name="u1", age=20),
        User(name="u2", age=25),
        User(name="u3", age=30),
    ]
    User.create_bulk(users)

    User.where(User.age >= 20).update_bulk({"age": 99})
    refreshed = User.order_by("id").all()
    assert [u.age for u in refreshed] == [99, 99, 99]


def test_bulk_delete_removes_matching_rows(core_models):
    User, _, _ = core_models

    users = [
        User(name="u1", age=20),
        User(name="u2", age=25),
        User(name="u3", age=30),
    ]
    User.create_bulk(users)

    User.where(User.age >= 20).delete_bulk()
    assert User.count() == 0


def test_bulk_create_is_atomic_on_validation_error(core_models):
    User, _, _ = core_models

    users = [
        User(name="good", age=20),
        User(name="bad", age=-1),  # will raise
    ]
    with pytest.raises(ValidationError, match="age must be non-negative"):
        User.create_bulk(users, with_hooks=True)

    assert User.where(User.name.in_(["good", "bad"])).count() == 0


def test_timestamp_hooks(core_models):
    User, _, _ = core_models

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


def test_order_by_descending(core_models):
    User, _, _ = core_models
    users = [User(name=f"p{i}", age=i) for i in range(5)]
    User.create_bulk(users)

    ordered = User.order_by("-age").all()
    ages = [u.age for u in ordered]
    assert ages == [4, 3, 2, 1, 0]


def test_paginate_returns_subset(core_models):
    User, _, _ = core_models
    users = [User(name=f"p{i}", age=i) for i in range(5)]
    User.create_bulk(users)

    ordered = User.order_by("-age").paginate(limit=2, offset=1).all()
    ages = [u.age for u in ordered]
    assert ages == [3, 2]


def test_validation_hook_blocks_persistence(core_models):
    User, _, _ = core_models

    with pytest.raises(ValidationError, match="age must be non-negative"):
        User(name="Invalid", age=-1).save()


def test_read_only_calls_do_not_write(core_models):
    User, _, _ = core_models
    User(name="Probe", age=20).save()

    with StatementCounter(User._db.sync_engine) as counter:
        fetched = User.where(User.name == "Probe").first()
        assert fetched is not None

    assert counter.write_count == 0


def test_session_per_operation_without_transaction(core_models):
    User, _, db = core_models

    with StatementCounter(db.sync_engine) as counter:
        User(name="NoTx", age=5).save()
    assert counter.write_count >= 1

    with StatementCounter(db.sync_engine) as counter:
        fetched = User.where(User.name == "NoTx").all()
        assert len(fetched) == 1
    assert counter.write_count == 0


def test_one_raises_for_missing_or_multiple(core_models):
    User, _, _ = core_models

    with pytest.raises(ObjectNotFoundError):
        User.where(User.name == "nope").one()

    User.create_bulk([User(name="dup", age=1), User(name="dup", age=2)])
    with pytest.raises(MultipleObjectsFoundError):
        User.where(User.name == "dup").one()


def test_related_helpers_filters_exists(core_models):
    User, Post, db = core_models

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


def test_related_helpers_filters_count(core_models):
    User, Post, db = core_models

    alice = User(name="Alice", age=30)
    bob = User(name="Bob", age=31)

    with db.transaction():
        alice.save()
        bob.save()
        Post(title="a1", author=alice).save()
        Post(title="a2", author=alice).save()
        Post(title="b1", author=bob).save()

    at_least_two = User.related(
        User.posts,
        aggregate="count",
        having=[lambda count_expr: count_expr >= 2],
        order_by="-count",
    ).all()
    assert [u.name for u in at_least_two] == ["Alice"]


def test_related_all_aggregate(core_models):
    User, Post, db = core_models

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


def test_related_does_not_nplus_one(core_models):
    User, Post, db = core_models

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


def test_related_joined_loader_single_query(core_models):
    User, Post, db = core_models

    with db.transaction():
        owner = User(name="owner", age=25)
        owner.save()
        Post(title="p1", author=owner).save()
        Post(title="p2", author=owner).save()

    with StatementCounter(db.sync_engine) as counter:
        fetched = User.related(User.posts, loader="joined").all()

    assert len(fetched) == 1
    assert counter.select_count == 1


def test_related_nested_selectin_query_counts(core_models, model_registry):
    User, Post, db = core_models
    Comment = model_registry.CommentNest
    with db.transaction():
        u = User(name="Nested", age=33)
        u.save()
        p = Post(title="p", author=u)
        p.save()
        Comment(post=p, body="c1").save()
        Comment(post=p, body="c2").save()

    with StatementCounter(db.sync_engine) as counter:
        fetched = (
            User.related(path(User.posts, Post.comments_nest), loader="selectin")
            .order_by("id")
            .all()
        )

    assert len(fetched) == 1
    # Expect at most 3 selects: users, posts, comments
    assert counter.select_count <= 3
    assert counter.write_count == 0


def test_related_chaining_with_path_and_aggregate(core_models, model_registry):
    User, Post, db = core_models
    Comment = model_registry.CommentRel

    with db.transaction():
        u1 = User(name="U1", age=30)
        u2 = User(name="U2", age=31)
        u1.save()
        u2.save()
        p1 = Post(title="p1", author=u1)
        p2 = Post(title="p2", author=u2)
        p1.save()
        p2.save()
        Comment(post=p1, body="c1").save()
        Comment(post=p1, body="c2").save()

    users = (
        User.related(User.posts, loader="selectin")
        .related(
            path(User.posts, Post.comments_rel_test),
            aggregate="count",
            having=[lambda c: c >= 2],
            loader="selectin",
        )
        .order_by("id")
        .all()
    )

    assert [u.name for u in users] == ["U1"]


def test_delete_cascades_to_children(core_models):
    User, Post, db = core_models

    parent = User(name="Parent", age=40)
    Post(title="child1", author=parent)
    Post(title="child2", author=parent)

    parent.save()

    with db.transaction():
        parent.delete()

    assert Post.where(Post.author_id == parent.id).count() == 0


@pytest.mark.asyncio
async def test_async_crud_roundtrip(async_core_models):
    User, Post, db = async_core_models

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
async def test_async_transaction_reuses_session_and_resets(async_core_models):
    User, _, db = async_core_models

    async with db.transaction():
        session_inside = active_session_var.get(None)
        assert session_inside is not None
        user = User(name="TxUser", age=33)
        await user.save()
        assert await User.where(User.id == user.id).exists()
        assert active_session_var.get(None) is session_inside

    assert active_session_var.get(None) is None


@pytest.mark.asyncio
async def test_async_read_only_calls_do_not_write(async_core_models):
    User, _, db = async_core_models
    await User(name="AsyncProbe", age=22).save()

    with StatementCounter(db.async_engine) as counter:
        fetched = await User.where(User.name == "AsyncProbe").first()
        assert fetched is not None

    assert counter.write_count == 0


@pytest.mark.asyncio
async def test_async_session_per_operation_without_transaction(async_core_models):
    User, _, db = async_core_models

    with StatementCounter(db.async_engine) as counter:
        await User(name="AsyncNoTx", age=7).save()
    assert counter.write_count >= 1

    with StatementCounter(db.async_engine) as counter:
        fetched = await User.where(User.name == "AsyncNoTx").all()
        assert len(fetched) == 1
    assert counter.write_count == 0


def test_json_helper_requires_json_column(core_models):
    User, _, _ = core_models

    with pytest.raises(TypeError):
        json(User.name)


def test_array_helper_requires_array_column(core_models):
    User, _, _ = core_models

    with pytest.raises(TypeError):
        array(User.name)


def test_related_cannot_be_chained(core_models):
    User, Post, db = core_models
    # Chaining multiple related() calls should be allowed and deduped.
    User.related(User.posts).related(User.posts).all()


def test_order_by_invalid_field_raises(core_models):
    User, _, _ = core_models
    with pytest.raises(AttributeError):
        User.order_by("does_not_exist").all()

    with pytest.raises(InvalidQueryError):
        User.order_by(123).all()  # non-string input should fail


def test_standalone_session_does_not_set_contextvar(core_models):
    User, _, db = core_models
    User(name="Solo", age=10).save()

    assert active_session_var.get(None) is None

    with db.sync_standalone_session() as session:
        result = session.execute(User.where(User.name == "Solo").alchemize())
        assert result.scalars().first() is not None
        assert active_session_var.get(None) is None


def test_json_helpers_on_supported_dialect(db_session, require_json, model_registry, db_target):
    Doc = model_registry.JsonDoc

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


def test_array_helpers_on_supported_dialect(db_session, require_array, model_registry):
    Item = model_registry.ArrayItem
    if Item is None:
        pytest.skip("PostgreSQL ARRAY type not available in this environment.")

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
