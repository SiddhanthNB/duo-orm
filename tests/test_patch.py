from __future__ import annotations

import pytest
from sqlalchemy import String, select

from duo_orm import Database, Mapped, mapped_column


def _model(db):
    class User(db.Model):
        __tablename__ = "users_patch"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str] = mapped_column(String(255), nullable=False)
        age: Mapped[int] = mapped_column(nullable=False)

    return User


def test_string_helpers_generate_like_patterns():
    db = Database("sqlite:///:memory:")
    User = _model(db)

    expr_contains = User.name.contains("foo")
    expr_icontains = User.name.icontains("bar")
    expr_istartswith = User.name.istartswith("baz")
    expr_iendswith = User.name.iendswith("qux")

    compiled = {
        "contains": str(expr_contains.compile(compile_kwargs={"literal_binds": True})).upper(),
        "icontains": str(expr_icontains.compile(compile_kwargs={"literal_binds": True})).upper(),
        "istartswith": str(expr_istartswith.compile(compile_kwargs={"literal_binds": True})).upper(),
        "iendswith": str(expr_iendswith.compile(compile_kwargs={"literal_binds": True})).upper(),
    }

    assert "LIKE" in compiled["contains"]
    assert "%" in compiled["icontains"]
    assert "%" in compiled["istartswith"]
    assert "%" in compiled["iendswith"]


def test_string_helpers_raise_on_non_string_column():
    db = Database("sqlite:///:memory:")
    User = _model(db)

    with pytest.raises(TypeError):
        User.age.icontains("nope")
    with pytest.raises(TypeError):
        User.age.startswith("nope")


def test_patch_helpers_work_in_select():
    db = Database("sqlite:///:memory:")
    User = _model(db)
    db.metadata.create_all(db.sync_engine)

    expr = select(User).where(User.name.icontains("foo"))
    compiled = str(expr.compile(compile_kwargs={"literal_binds": True})).upper()
    assert "WHERE" in compiled
    assert "LIKE" in compiled
