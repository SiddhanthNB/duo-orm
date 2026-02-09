from __future__ import annotations

import pytest


def _seed_compounds(Compound):
    Compound.create_bulk(
        [
            {"org_id": 1, "code": "A", "name": "one"},
            {"org_id": 1, "code": "B", "name": "two"},
            {"org_id": 2, "code": "C", "name": "three"},
            {"org_id": 2, "code": "D", "name": "four"},
        ]
    )


def test_update_bulk_with_hooks_composite_pk_batches(db_session, model_registry, db_target):
    if db_target.dialect == "mssql":
        pytest.skip("SQL Server does not support row-value comparisons for composite PK batching.")
    Compound = model_registry.Compound
    _seed_compounds(Compound)

    Compound.where(Compound.org_id == 1).update_bulk(
        {"name": "updated"},
        with_hooks=True,
        batch_size=1,
    )

    rows = Compound.where(Compound.org_id == 1).order_by("code").all()
    assert [r.name for r in rows] == ["updated", "updated"]


def test_delete_bulk_with_hooks_composite_pk_single_transaction(db_session, model_registry, db_target):
    if db_target.dialect == "mssql":
        pytest.skip("SQL Server does not support row-value comparisons for composite PK batching.")
    Compound = model_registry.Compound
    _seed_compounds(Compound)

    Compound.where(Compound.org_id == 2).delete_bulk(
        with_hooks=True,
        batch_size=1,
        per_batch_transaction=False,
    )

    remaining = Compound.where(Compound.org_id == 2).count()
    assert remaining == 0


@pytest.mark.asyncio
async def test_async_update_bulk_without_hooks(async_db_session):
    from tests import models as test_models

    User = test_models.registry(async_db_session).User
    await User.create_bulk(
        [
            {"name": "u1", "age": 1},
            {"name": "u2", "age": 2},
        ]
    )

    await User.where(User.age > 0).update_bulk({"age": 10}, with_hooks=False)
    assert await User.where(User.age == 10).count() == 2


@pytest.mark.asyncio
async def test_async_update_bulk_with_hooks_composite_pk_batches(async_db_session, db_target):
    if db_target.dialect == "mssql":
        pytest.skip("SQL Server does not support row-value comparisons for composite PK batching.")
    from tests import models as test_models

    Compound = test_models.registry(async_db_session).Compound
    await Compound.create_bulk(
        [
            {"org_id": 1, "code": "A", "name": "one"},
            {"org_id": 1, "code": "B", "name": "two"},
        ]
    )

    await Compound.where(Compound.org_id == 1).update_bulk(
        {"name": "async"},
        with_hooks=True,
        batch_size=1,
        per_batch_transaction=False,
    )

    rows = await Compound.where(Compound.org_id == 1).order_by("code").all()
    assert [r.name for r in rows] == ["async", "async"]


@pytest.mark.asyncio
async def test_async_delete_bulk_with_hooks_composite_pk_single_transaction(async_db_session, db_target):
    if db_target.dialect == "mssql":
        pytest.skip("SQL Server does not support row-value comparisons for composite PK batching.")
    from tests import models as test_models

    Compound = test_models.registry(async_db_session).Compound
    await Compound.create_bulk(
        [
            {"org_id": 2, "code": "C", "name": "three"},
            {"org_id": 2, "code": "D", "name": "four"},
        ]
    )

    await Compound.where(Compound.org_id == 2).delete_bulk(
        with_hooks=True,
        batch_size=1,
        per_batch_transaction=False,
    )

    remaining = await Compound.where(Compound.org_id == 2).count()
    assert remaining == 0


@pytest.mark.asyncio
async def test_async_delete_instance(async_db_session):
    from tests import models as test_models

    User = test_models.registry(async_db_session).User

    user = User(name="delete-me", age=9)
    await user.save()

    await user.delete()
    assert await User.count() == 0


@pytest.mark.asyncio
async def test_async_one_returns_row(async_db_session):
    from tests import models as test_models

    User = test_models.registry(async_db_session).User

    await User.create({"name": "single", "age": 5})
    found = await User.where(User.name == "single").one()
    assert found is not None
    assert found.name == "single"
