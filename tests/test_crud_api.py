from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import Integer, String

from duo_orm import Mapped, mapped_column
from duo_orm.exceptions import InvalidQueryError, ValidationError
from tests.test_orm_core import _build_models


@pytest.fixture
def crud_models(db):
    User, Post = _build_models(db)
    db.metadata.drop_all(db.sync_engine)
    db.metadata.create_all(db.sync_engine)
    try:
        yield User, Post, db
    finally:
        db.metadata.drop_all(db.sync_engine)


@pytest_asyncio.fixture
async def async_crud_models(async_db):
    User, Post = _build_models(async_db)
    async_db.metadata.drop_all(async_db.sync_engine)
    async_db.metadata.create_all(async_db.sync_engine)
    try:
        yield User, Post, async_db
    finally:
        async_db.metadata.drop_all(async_db.sync_engine)


def test_model_get_returns_expected(crud_models):
    User, _, _ = crud_models

    alice = User(name="Alice", age=30)
    alice.save()

    fetched = User.get(alice.id)
    assert fetched is not None and fetched.name == "Alice"

    missing = User.get(9999)
    assert missing is None


def test_model_get_composite_pk(db):
    db.metadata.drop_all(db.sync_engine)

    class Compound(db.Model):
        __tablename__ = "compound_get"
        org_id: Mapped[int] = mapped_column(Integer, primary_key=True)
        code: Mapped[str] = mapped_column(String(20), primary_key=True)
        name: Mapped[str] = mapped_column(String(50))

    db.metadata.create_all(db.sync_engine)
    try:
        rec = Compound(org_id=1, code="A", name="alpha")
        rec.save()

        found = Compound.get(org_id=1, code="A")
        assert found is not None and found.name == "alpha"

        with pytest.raises(ValidationError):
            Compound.get(1)  # positional not allowed on composite

        with pytest.raises(ValidationError):
            Compound.get(org_id=1)  # missing component
    finally:
        db.metadata.drop_all(db.sync_engine)


def test_model_create_and_instance_update(crud_models):
    User, _, _ = crud_models

    created = User.create(name="Kw", age=3)
    assert created.id is not None

    with pytest.raises(ValidationError):
        created.update({"age": -5})

    created.update(age=10)
    assert created.age == 10


def test_create_bulk_with_and_without_hooks(crud_models):
    User, _, _ = crud_models

    # with_hooks=True should validate and block bad data
    with pytest.raises(ValidationError):
        User.create_bulk([
            {"name": "bad", "age": -1},
        ], with_hooks=True)

    # with_hooks=False inserts even if validate would fail
    User.create_bulk([
        {"name": "skip", "age": -1},
        {"name": "ok", "age": 10},
    ])
    names = sorted(u.name for u in User.order_by("name").all())
    assert names == ["ok", "skip"]


def test_create_bulk_return_models(crud_models):
    User, _, _ = crud_models
    users = User.create_bulk(
        [
            {"name": "r1", "age": 10},
            {"name": "r2", "age": 11},
        ],
        return_models=True,
    )
    assert isinstance(users, list)
    assert all(u.id is not None for u in users)
    with pytest.raises(ValueError):
        User.create_bulk([], batch_size=0)


def test_update_delete_bulk_require_filter(crud_models):
    User, _, _ = crud_models
    User.create_bulk([
        {"name": "u1", "age": 1},
        {"name": "u2", "age": 2},
    ])

    with pytest.raises(InvalidQueryError):
        User.where().update_bulk({"age": 9})

    with pytest.raises(InvalidQueryError):
        User.where().delete_bulk()

    User.where(User.name == "u1").update_bulk({"age": 5})
    assert User.where(User.age == 5).count() == 1

    User.where(User.name == "u2").delete_bulk()
    assert User.where(User.name == "u2").count() == 0


def test_update_delete_bulk_with_hooks_and_full_table(crud_models):
    User, _, _ = crud_models
    User.create_bulk(
        [
            {"name": "u1", "age": 1},
            {"name": "u2", "age": 2},
        ]
    )

    with pytest.raises(ValidationError):
        User.where(User.name == "u1").update_bulk({"age": -5}, with_hooks=True)

    User.where(User.name == "u1").update_bulk({"age": 5}, with_hooks=True, batch_size=1)
    assert User.where(User.age == 5).count() == 1

    # allow full table update/delete when explicitly opted in
    User.update_bulk({"age": 9}, require_filter=False)
    assert User.where(User.age == 9).count() == 2

    User.delete_bulk(require_filter=False)
    assert User.where().count() == 0
    with pytest.raises(ValueError):
        User.update_bulk({"age": 1}, batch_size=0, require_filter=False)
    with pytest.raises(ValueError):
        User.delete_bulk(batch_size=0, require_filter=False)
    with pytest.raises(ValueError):
        User.delete_bulk(batch_size=0)


def test_iterate_batches_and_rows(crud_models):
    User, _, _ = crud_models
    User.create_bulk([{"name": f"u{i}", "age": i} for i in range(5)])

    batches = list(User.order_by("id").iterate(batch=True, batch_size=2))
    assert [len(batch) for batch in batches] == [2, 2, 1]
    flat = [u.name for batch in batches for u in batch]
    assert flat == ["u0", "u1", "u2", "u3", "u4"]

    streamed = [u.name for u in User.order_by("id").iterate(batch_size=2)]
    assert streamed == ["u0", "u1", "u2", "u3", "u4"]

    # batch_size=1 works
    ones = [u.name for u in User.order_by("id").iterate(batch_size=1)]
    assert ones == streamed


def test_iterate_ordering_and_empty(crud_models):
    User, _, _ = crud_models
    User.create_bulk(
        [
            {"name": "a", "age": 5},
            {"name": "b", "age": 1},
            {"name": "c", "age": 3},
        ]
    )

    # respects explicit order_by
    ordered = [u.name for u in User.order_by("-age").iterate(batch_size=2)]
    assert ordered == ["a", "c", "b"]

    # auto PK ordering when none provided
    auto = [u.name for u in User.iterate(batch_size=2)]
    assert auto == ["a", "b", "c"]

    empty = list(User.where(User.name == "zzz").iterate())
    assert empty == []

    with pytest.raises(ValueError):
        list(User.iterate(batch_size=0))

    # respects existing limit/offset
    limited = list(User.order_by("id").limit(1).offset(1).iterate(batch_size=5))
    assert [u.name for u in limited] == ["b"]

    # iterate via query builder directly matches model helper
    via_query = [u.name for u in User.where().order_by("id").iterate(batch_size=2)]
    via_model = [u.name for u in User.iterate(batch_size=2)]
    assert via_query == via_model

    # paginate vs iterate should play nicely (iterate over the paginated subset)
    paged = list(User.order_by("id").paginate(limit=2, offset=1).iterate(batch_size=10))
    assert [u.name for u in paged] == ["b", "c"]


def test_deprecated_batch_methods_raise(crud_models):
    User, _, _ = crud_models
    with pytest.raises(InvalidQueryError):
        User.where().find_each()
    with pytest.raises(InvalidQueryError):
        User.where().find_in_batches()
    with pytest.raises(InvalidQueryError):
        User.where().update()
    with pytest.raises(InvalidQueryError):
        User.where().delete()


@pytest.mark.asyncio
async def test_async_create_bulk_return_models(async_crud_models):
    User, _, _ = async_crud_models
    users = await User.create_bulk(
        [
            {"name": "ax", "age": 10},
            {"name": "ay", "age": 11},
        ],
        return_models=True,
    )
    assert isinstance(users, list)
    assert all(u.id is not None for u in users)
    with pytest.raises(ValueError):
        await User.create_bulk([], batch_size=0)


@pytest.mark.asyncio
async def test_async_iterate(async_crud_models):
    User, _, _ = async_crud_models
    await User.create_bulk([{"name": f"au{i}", "age": i} for i in range(4)])

    names = []
    async for u in User.order_by("id").iterate(batch_size=2):
        names.append(u.name)
    assert names == ["au0", "au1", "au2", "au3"]

    batches = []
    async for batch in User.order_by("id").iterate(batch=True, batch_size=3):
        batches.append([u.name for u in batch])
    assert batches == [["au0", "au1", "au2"], ["au3"]]

    empty = [u async for u in User.where(User.name == "none").iterate()]
    assert empty == []

    # iterate with limit/offset
    subset = [u.name async for u in User.order_by("id").limit(2).offset(1).iterate(batch_size=5)]
    assert subset == ["au1", "au2"]


@pytest.mark.asyncio
async def test_async_update_delete_bulk_with_hooks(async_crud_models):
    User, _, _ = async_crud_models
    await User.create_bulk([
        {"name": "h1", "age": 1},
        {"name": "h2", "age": 2},
    ])

    with pytest.raises(ValidationError):
        await User.where(User.name == "h1").update_bulk({"age": -1}, with_hooks=True)

    await User.where(User.name == "h1").update_bulk({"age": 5}, with_hooks=True)
    assert await User.where(User.age == 5).count() == 1

    await User.where(User.name == "h2").delete_bulk(with_hooks=True, batch_size=1)
    assert await User.where(User.name == "h2").count() == 0

    await User.delete_bulk(require_filter=False)
    assert await User.count() == 0


@pytest.mark.asyncio
async def test_async_get_returns_none(async_crud_models):
    User, _, _ = async_crud_models
    missing = await User.get(123456)
    assert missing is None


def test_paginate_on_model_and_query(crud_models):
    User, _, _ = crud_models
    User.create_bulk([{"name": f"p{i}", "age": i} for i in range(4)])

    from_model = User.paginate(limit=2, offset=1).order_by("id").all()
    from_query = User.where().order_by("id").paginate(limit=2, offset=1).all()
    assert [u.name for u in from_model] == [u.name for u in from_query] == ["p1", "p2"]


def test_count_helpers(crud_models):
    User, _, _ = crud_models
    User.create_bulk([{"name": "c1", "age": 1}, {"name": "c2", "age": 2}])
    assert User.count() == 2
    assert User.where(User.age > 1).count() == 1
