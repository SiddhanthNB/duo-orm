from __future__ import annotations

import pytest

from duo_orm.exceptions import InvalidQueryError, ValidationError


def test_model_get_returns_expected(core_models):
    User, _, _ = core_models

    alice = User(name="Alice", age=30)
    alice.save()

    fetched = User.get(alice.id)
    assert fetched is not None and fetched.name == "Alice"

    missing = User.get(9999)
    assert missing is None


def test_model_get_composite_pk(db_session, model_registry):
    Compound = model_registry.Compound

    rec = Compound(org_id=1, code="A", name="alpha")
    rec.save()

    found = Compound.get(org_id=1, code="A")
    assert found is not None and found.name == "alpha"

    with pytest.raises(ValidationError):
        Compound.get(1)  # positional not allowed on composite

    with pytest.raises(ValidationError):
        Compound.get(org_id=1)  # missing component


def test_model_create_and_instance_update(core_models):
    User, _, _ = core_models

    created = User.create(name="Kw", age=3)
    assert created.id is not None

    with pytest.raises(ValidationError, match="age must be non-negative"):
        created.update({"age": -5})

    created.update(age=10)
    assert created.age == 10


def test_create_bulk_with_hooks_validates(core_models):
    User, _, _ = core_models

    with pytest.raises(ValidationError, match="age must be non-negative"):
        User.create_bulk(
            [
                {"name": "bad", "age": -1},
            ],
            with_hooks=True,
        )


def test_create_bulk_without_hooks_skips_validation(core_models):
    User, _, _ = core_models

    User.create_bulk(
        [
            {"name": "skip", "age": -1},
            {"name": "ok", "age": 10},
        ]
    )
    names = sorted(u.name for u in User.order_by("name").all())
    assert names == ["ok", "skip"]


def test_create_bulk_return_models(core_models):
    User, _, _ = core_models
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


def test_update_bulk_requires_filter(core_models):
    User, _, _ = core_models
    User.create_bulk(
        [
            {"name": "u1", "age": 1},
            {"name": "u2", "age": 2},
        ]
    )

    with pytest.raises(InvalidQueryError):
        User.where().update_bulk({"age": 9})

    User.where(User.name == "u1").update_bulk({"age": 5})
    assert User.where(User.age == 5).count() == 1


def test_delete_bulk_requires_filter(core_models):
    User, _, _ = core_models
    User.create_bulk(
        [
            {"name": "u1", "age": 1},
            {"name": "u2", "age": 2},
        ]
    )

    with pytest.raises(InvalidQueryError):
        User.where().delete_bulk()

    User.where(User.name == "u2").delete_bulk()
    assert User.where(User.name == "u2").count() == 0


def test_update_bulk_with_hooks_validates(core_models):
    User, _, _ = core_models
    User.create_bulk(
        [
            {"name": "u1", "age": 1},
            {"name": "u2", "age": 2},
        ]
    )

    with pytest.raises(ValidationError, match="age must be non-negative"):
        User.where(User.name == "u1").update_bulk({"age": -5}, with_hooks=True)

    User.where(User.name == "u1").update_bulk({"age": 5}, with_hooks=True, batch_size=1)
    assert User.where(User.age == 5).count() == 1


def test_bulk_ops_allow_full_table_when_opted_in(core_models):
    User, _, _ = core_models
    User.create_bulk(
        [
            {"name": "u1", "age": 1},
            {"name": "u2", "age": 2},
        ]
    )

    User.update_bulk({"age": 9}, require_filter=False)
    assert User.where(User.age == 9).count() == 2

    User.delete_bulk(require_filter=False)
    assert User.where().count() == 0


def test_bulk_ops_reject_invalid_batch_size(core_models):
    User, _, _ = core_models
    with pytest.raises(ValueError):
        User.update_bulk({"age": 1}, batch_size=0, require_filter=False)
    with pytest.raises(ValueError):
        User.delete_bulk(batch_size=0, require_filter=False)
    with pytest.raises(ValueError):
        User.delete_bulk(batch_size=0)


def test_iterate_batches_return_expected_sizes(core_models):
    User, _, _ = core_models
    User.create_bulk([{"name": f"u{i}", "age": i} for i in range(5)])

    batches = list(User.order_by("id").iterate(batch=True, batch_size=2))
    assert [len(batch) for batch in batches] == [2, 2, 1]


def test_iterate_streamed_rows_match_batches(core_models):
    User, _, _ = core_models
    User.create_bulk([{"name": f"u{i}", "age": i} for i in range(5)])

    batches = list(User.order_by("id").iterate(batch=True, batch_size=2))
    flat = [u.name for batch in batches for u in batch]
    assert flat == ["u0", "u1", "u2", "u3", "u4"]

    streamed = [u.name for u in User.order_by("id").iterate(batch_size=2)]
    assert streamed == ["u0", "u1", "u2", "u3", "u4"]


def test_iterate_batch_size_one_matches_streamed(core_models):
    User, _, _ = core_models
    User.create_bulk([{"name": f"u{i}", "age": i} for i in range(5)])

    streamed = [u.name for u in User.order_by("id").iterate(batch_size=2)]
    ones = [u.name for u in User.order_by("id").iterate(batch_size=1)]
    assert ones == streamed


def test_iterate_respects_order_and_defaults(core_models):
    User, _, _ = core_models
    User.create_bulk(
        [
            {"name": "a", "age": 5},
            {"name": "b", "age": 1},
            {"name": "c", "age": 3},
        ]
    )

    ordered = [u.name for u in User.order_by("-age").iterate(batch_size=2)]
    assert ordered == ["a", "c", "b"]

    auto = [u.name for u in User.iterate(batch_size=2)]
    assert auto == ["a", "b", "c"]


def test_iterate_empty_and_errors(core_models):
    User, _, _ = core_models
    User.create_bulk([{"name": "a", "age": 1}])

    empty = list(User.where(User.name == "zzz").iterate())
    assert empty == []

    with pytest.raises(ValueError):
        list(User.iterate(batch_size=0))


def test_iterate_respects_limit_and_offset(core_models):
    User, _, _ = core_models
    User.create_bulk(
        [
            {"name": "a", "age": 5},
            {"name": "b", "age": 1},
            {"name": "c", "age": 3},
        ]
    )

    limited = list(User.order_by("id").limit(1).offset(1).iterate(batch_size=5))
    assert [u.name for u in limited] == ["b"]


def test_iterate_query_builder_matches_model(core_models):
    User, _, _ = core_models
    User.create_bulk(
        [
            {"name": "a", "age": 5},
            {"name": "b", "age": 1},
            {"name": "c", "age": 3},
        ]
    )

    via_query = [u.name for u in User.where().order_by("id").iterate(batch_size=2)]
    via_model = [u.name for u in User.iterate(batch_size=2)]
    assert via_query == via_model


def test_iterate_respects_paginate_subset(core_models):
    User, _, _ = core_models
    User.create_bulk(
        [
            {"name": "a", "age": 5},
            {"name": "b", "age": 1},
            {"name": "c", "age": 3},
        ]
    )

    paged = list(User.order_by("id").paginate(limit=2, offset=1).iterate(batch_size=10))
    assert [u.name for u in paged] == ["b", "c"]


def test_deprecated_batch_methods_raise(core_models):
    User, _, _ = core_models
    with pytest.raises(InvalidQueryError):
        User.where().find_each()
    with pytest.raises(InvalidQueryError):
        User.where().find_in_batches()
    with pytest.raises(InvalidQueryError):
        User.where().update()
    with pytest.raises(InvalidQueryError):
        User.where().delete()


@pytest.mark.asyncio
async def test_async_create_bulk_return_models(async_core_models):
    User, _, _ = async_core_models
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
async def test_async_iterate(async_core_models):
    User, _, _ = async_core_models
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
async def test_async_update_delete_bulk_with_hooks(async_core_models):
    User, _, _ = async_core_models
    await User.create_bulk([
        {"name": "h1", "age": 1},
        {"name": "h2", "age": 2},
    ])

    with pytest.raises(ValidationError, match="age must be non-negative"):
        await User.where(User.name == "h1").update_bulk({"age": -1}, with_hooks=True)

    await User.where(User.name == "h1").update_bulk({"age": 5}, with_hooks=True)
    assert await User.where(User.age == 5).count() == 1

    await User.where(User.name == "h2").delete_bulk(with_hooks=True, batch_size=1)
    assert await User.where(User.name == "h2").count() == 0

    await User.delete_bulk(require_filter=False)
    assert await User.count() == 0


@pytest.mark.asyncio
async def test_async_get_returns_none(async_core_models):
    User, _, _ = async_core_models
    missing = await User.get(123456)
    assert missing is None


def test_paginate_on_model_and_query(core_models):
    User, _, _ = core_models
    User.create_bulk([{"name": f"p{i}", "age": i} for i in range(4)])

    from_model = User.paginate(limit=2, offset=1).order_by("id").all()
    from_query = User.where().order_by("id").paginate(limit=2, offset=1).all()
    assert [u.name for u in from_model] == [u.name for u in from_query] == ["p1", "p2"]


def test_count_helpers(core_models):
    User, _, _ = core_models
    User.create_bulk([{"name": "c1", "age": 1}, {"name": "c2", "age": 2}])
    assert User.count() == 2
    assert User.where(User.age > 1).count() == 1
