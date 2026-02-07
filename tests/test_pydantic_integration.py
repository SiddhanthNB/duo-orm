from __future__ import annotations

import pytest
import pytest_asyncio
from pydantic import BaseModel, ConfigDict

from tests.test_orm_core import _build_models
from duo_orm.exceptions import ValidationError


class UserCreate(BaseModel):
    name: str
    age: int


class UserUpdate(BaseModel):
    name: str | None = None
    age: int | None = None
    model_config = ConfigDict(extra="forbid")


class UserRead(BaseModel):
    id: int
    name: str
    age: int
    model_config = ConfigDict(from_attributes=True)


@pytest.fixture
def models(db):
    User, Post = _build_models(db)
    db.metadata.drop_all(db.sync_engine)
    db.metadata.create_all(db.sync_engine)
    try:
        yield User, db
    finally:
        db.metadata.drop_all(db.sync_engine)


@pytest_asyncio.fixture
async def async_models(async_db):
    User, Post = _build_models(async_db)
    async_db.metadata.drop_all(async_db.sync_engine)
    async_db.metadata.create_all(async_db.sync_engine)
    try:
        yield User, async_db
    finally:
        async_db.metadata.drop_all(async_db.sync_engine)


def test_from_schema_and_to_schema(models):
    User, _ = models
    payload = UserCreate(name="Ada", age=30)
    inst = User.from_schema(payload)
    assert inst.id is None

    inst.save()
    dto = inst.to_schema(UserRead)
    assert dto.name == "Ada"
    assert dto.id == inst.id


def test_apply_schema_partial(models):
    User, _ = models
    u = User.create({"name": "Bob", "age": 25})
    patch = UserUpdate(name="Bobby")
    u.apply_schema(patch)
    assert u.name == "Bobby"
    assert u.age == 25  # unchanged
    u.save()


def test_create_bulk_with_schemas(models):
    User, _ = models
    rows = [
        UserCreate(name="C1", age=20),
        UserCreate(name="C2", age=21),
    ]
    created = User.create_bulk(rows, return_models=True)
    assert len(created) == 2
    names = sorted(u.name for u in created)
    assert names == ["C1", "C2"]


def test_update_bulk_with_schema(models):
    User, _ = models
    User.create_bulk(
        [
            {"name": "D1", "age": 5},
            {"name": "D2", "age": 6},
        ]
    )
    User.where(User.name == "D1").update_bulk(UserUpdate(name="Dx"), with_hooks=True)
    assert User.where(User.name == "Dx").count() == 1


@pytest.mark.asyncio
async def test_async_create_and_update_with_schema(async_models):
    User, _ = async_models
    payload = UserCreate(name="Eve", age=40)
    u = await User.create(payload)
    assert u.id is not None

    await u.update(UserUpdate(name="Evelyn"))
    assert (await User.get(u.id)).name == "Evelyn"


def test_to_schema_requires_from_attributes(models):
    User, _ = models

    class Bad(BaseModel):
        id: int
    user = User.create({"name": "F", "age": 33})
    with pytest.raises(ValidationError):
        user.to_schema(Bad)
