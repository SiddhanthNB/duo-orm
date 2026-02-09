from __future__ import annotations

import pytest
from pydantic import BaseModel

import duo_orm.basemodel as basemodel
from duo_orm.exceptions import ValidationError


def test_get_validates_composite_pk_arguments(db_session, model_registry):
    Compound = model_registry.Compound

    with pytest.raises(ValidationError, match="Provide keyword arguments"):
        Compound.get(1)

    with pytest.raises(ValidationError, match="Missing primary key component 'code'"):
        Compound.get(org_id=1, oops="x")

    with pytest.raises(ValidationError, match="Number of primary key fields"):
        Compound.get(org_id=1, code="A", extra=1)


def test_get_validates_positional_count(core_models):
    User, _, _ = core_models

    with pytest.raises(ValidationError, match="Exactly one positional"):
        User.get(1, 2)


def test_get_raises_when_model_has_no_pk(monkeypatch, model_registry):
    User = model_registry.User

    class DummyMapper:
        primary_key = []

    monkeypatch.setattr(basemodel, "sa_inspect", lambda cls: DummyMapper())

    with pytest.raises(ValidationError, match="has no primary key"):
        User.get(1)


@pytest.mark.asyncio
async def test_async_get_uses_active_session(async_db_session):
    from tests import models as test_models

    User = test_models.registry(async_db_session).User

    created = await User.create({"name": "async", "age": 1})

    async with async_db_session.transaction():
        fetched = await User.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    outside = await User.get(created.id)
    assert outside is not None
    assert outside.id == created.id


@pytest.mark.asyncio
async def test_create_async_returns_instance(async_db_session):
    from tests import models as test_models

    User = test_models.registry(async_db_session).User

    created = await User.create({"name": "async-create", "age": 2})
    assert created.id is not None


def test_create_accepts_instance(core_models):
    User, _, _ = core_models

    instance = User(name="instance", age=3)
    created = User.create(instance)
    assert created is instance
    assert created.id is not None


def test_to_schema_requires_model_validate(db_session, model_registry):
    User = model_registry.User

    user = User(name="schema", age=4)
    user.save()

    class NotSchema:
        pass

    with pytest.raises(ValidationError, match="model_validate"):
        user.to_schema(NotSchema)


def test_to_schema_requires_from_attributes(db_session, model_registry):
    User = model_registry.User

    user = User(name="schema", age=5)
    user.save()

    class Schema(BaseModel):
        name: str

    with pytest.raises(ValidationError, match="from_attributes"):
        user.to_schema(Schema)


def test_to_schema_wraps_pydantic_error(db_session, model_registry):
    User = model_registry.User

    user = User(name="schema", age=6)
    user.save()
    user.age = "bad"

    class Schema(BaseModel):
        model_config = {"from_attributes": True}
        age: int

    with pytest.raises(ValidationError):
        user.to_schema(Schema)
