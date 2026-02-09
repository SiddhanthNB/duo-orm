import pytest
from pydantic import BaseModel
from sqlalchemy import Integer, String, inspect
from sqlalchemy.orm import Mapped, mapped_column

from duo_orm.db import Database


def _build_db():
    return Database("sqlite:///:memory:")


def test_guarded_fields_block_pk_and_custom():
    db = _build_db()

    class User(db.Model):
        __tablename__ = "guard_users"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String, nullable=False)
        role: Mapped[str] = mapped_column(String, nullable=False, default="user")

        __guarded__ = ("role",)

    db.create_all()

    u = User.create({"id": 999, "name": "alice", "role": "admin"})
    # PK is allowed on create (required for manual keys), but guarded fields are blocked.
    assert u.id == 999
    assert u.role == "user"

    u.update({"id": 1234, "role": "super", "name": "alice2"})
    assert u.id != 1234
    assert u.role == "user"
    assert u.name == "alice2"


def test_guarded_composite_pk():
    db = _build_db()

    class Pair(db.Model):
        __tablename__ = "pairs"
        org_id: Mapped[int] = mapped_column(Integer, primary_key=True)
        user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
        role: Mapped[str] = mapped_column(String, nullable=False, default="member")

        __guarded__ = ("role",)

    db.create_all()
    # Guarding should not drop required PKs; they must be present.
    p = Pair.create({"org_id": 1, "user_id": 2, "role": "admin"})
    assert (p.org_id, p.user_id) == (1, 2)
    assert p.role == "member"

    # Updates should ignore guarded + PK fields
    p.update({"org_id": 9, "user_id": 9, "role": "owner"})
    assert (p.org_id, p.user_id) == (1, 2)
    assert p.role == "member"


def test_pydantic_defaults_applied_and_wrapped():
    db = _build_db()

    class User(db.Model):
        __tablename__ = "guard_users_defaults"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String, nullable=False)
        age: Mapped[int] = mapped_column(Integer, nullable=False)

    class UserCreate(BaseModel):
        name: str
        age: int = 30

    db.create_all()
    u = User.create(UserCreate(name="bob"))
    assert u.age == 30


def test_pydantic_partial_ignores_none():
    db = _build_db()

    class User(db.Model):
        __tablename__ = "guard_users_partial"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String, nullable=False)
        age: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    class UserPatch(BaseModel):
        name: str | None = None
        age: int | None = None

    db.create_all()
    u = User.create({"name": "carol"})
    assert u.age == 10
    u.apply_schema(UserPatch(name=None, age=None))
    assert u.name == "carol"
    assert u.age == 10


def test_create_all_and_drop_all_helpers():
    db = _build_db()

    class Item(db.Model):
        __tablename__ = "items_helper"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String, nullable=False)

    db.create_all()
    inspector = inspect(db.sync_engine)
    assert "items_helper" in inspector.get_table_names()
    db.drop_all()
    inspector = inspect(db.sync_engine)
    assert "items_helper" not in inspector.get_table_names()


def test_iterate_uses_seek_for_pk_descending():
    db = _build_db()

    class User(db.Model):
        __tablename__ = "iter_seek_users"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String, nullable=False)

    db.create_all()
    User.create_bulk([{"name": f"u{i}"} for i in range(3)])

    names = [u.name for u in User.order_by("-id").iterate(batch_size=2)]
    assert names == ["u2", "u1", "u0"]


def test_iterate_offset_path_for_non_pk_order():
    db = _build_db()

    class User(db.Model):
        __tablename__ = "iter_offset_users"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String, nullable=False)

    db.create_all()
    User.create_bulk([{"name": n} for n in ["b", "a", "c"]])
    names = [u.name for u in User.order_by("name").iterate(batch_size=1)]
    assert names == ["a", "b", "c"]

    limited = [u.name for u in User.order_by("name").limit(1).offset(1).iterate(batch_size=5)]
    assert limited == ["b"]


def test_update_bulk_with_hooks_single_transaction_toggle():
    db = _build_db()

    class User(db.Model):
        __tablename__ = "hook_toggle_users"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String, nullable=False)
        age: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    db.create_all()
    User.create_bulk([{"name": "a", "age": 1}, {"name": "b", "age": 2}])

    User.where().update_bulk(
        {"age": 5},
        with_hooks=True,
        per_batch_transaction=False,
        batch_size=1,
        require_filter=False,
    )
    ages = sorted([u.age for u in User.where().all()])
    assert ages == [5, 5]


def test_get_uses_identity_map_in_transaction():
    db = _build_db()

    class User(db.Model):
        __tablename__ = "get_identity_users"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String, nullable=False)

    db.create_all()
    u = User.create({"name": "zed"})
    with db.transaction() as session:
        # load once
        first = User.where(User.id == u.id).first()
        again = User.get(u.id)
        assert again is first

    outside = User.get(u.id)
    assert outside.id == u.id
    assert outside is not None
