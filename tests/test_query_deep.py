from __future__ import annotations

import pytest
from sqlalchemy import JSON as SAJSON, func

from duo_orm import array, json
from duo_orm.exceptions import InvalidQueryError
from duo_orm.query import (
    _is_json_column,
    _is_array_column,
    JSONExpression,
    ArrayExpression,
    QueryBuilder,
)


def test_internal_type_detectors():
    dummy = type("D", (), {"type": None})()
    assert _is_json_column(dummy) is False
    dummy.type = SAJSON()
    assert _is_json_column(dummy) is True

    arr_dummy = type("A", (), {"type": type("T", (), {"_is_array": True})()})()
    assert _is_array_column(arr_dummy) is True


def test_json_scalar_casts_and_astext(monkeypatch, model_registry):
    Doc = model_registry.JsonDoc
    expr = json(Doc.profile)

    # scalar casts cover integer/float/bool branches
    assert str(expr.equals(True))
    assert str(expr.equals(1))
    assert str(expr.equals(1.5))

    # unknown cast falls through default branch
    weird = JSONExpression(expr.column, cast_as="other")
    assert str(weird._scalar_expr())

    # astext branch vs fallback
    dummy_with_astext = type("X", (), {"astext": "text_expr"})
    assert expr._as_text(dummy_with_astext) == "text_expr"
    dummy_plain = object()
    assert str(expr._as_text(dummy_plain))


def test_array_expression_branches(monkeypatch, model_registry):
    Bag = model_registry.BagInt
    expr = array(Bag.tags)

    # includes() when .any missing
    dummy_no_any = type("NoAny", (), {})()
    monkeypatch.setattr(ArrayExpression, "_array_expr", lambda self: dummy_no_any, raising=False)
    with pytest.raises(TypeError):
        expr.includes(1)

    # includes_any() when overlap missing
    dummy_no_overlap = type("NoOverlap", (), {"overlap": None})()
    monkeypatch.setattr(ArrayExpression, "_array_expr", lambda self: dummy_no_overlap, raising=False)
    with pytest.raises(TypeError):
        expr.includes_any([1])

    # includes_all uses comparator.contains when present
    class Comp:
        def contains(self, values):
            return ("contains", values)

    dummy_with_contains = type("WithContains", (), {"comparator": Comp()})()
    monkeypatch.setattr(ArrayExpression, "_array_expr", lambda self: dummy_with_contains, raising=False)
    assert expr.includes_all([1, 2]) == ("contains", [1, 2])

    # length: exercise cardinality branch if available, else fallback
    monkeypatch.setattr(ArrayExpression, "_array_expr", lambda self: Bag.tags, raising=False)
    original_cardinality = getattr(func, "cardinality", None)
    try:
        if hasattr(func, "cardinality"):
            assert str(expr.length())
        else:
            assert "array_length" in str(expr.length())
    finally:
        if original_cardinality is None and hasattr(func, "cardinality"):
            delattr(func, "cardinality")


def test_querybuilder_internal_paths(db, model_registry):
    User = model_registry.User
    Post = model_registry.Post
    qb = QueryBuilder(User, db=db)

    # order_by rejects falsy/invalid fields
    with pytest.raises(InvalidQueryError):
        qb.order_by("", None)

    path = qb._resolve_relationship_path(User.posts)

    # _apply_exists early return with no where
    qb._apply_exists(path, [])

    # _apply_all requires predicate
    with pytest.raises(ValueError):
        qb._apply_all(path, [])

    # _apply_count with having/order callable
    where_clause = [Post.title.isnot(None)]
    having_clause = [lambda c: c > 0]
    order_clause = [lambda c: c.desc()]
    qb._apply_count(path, where_clause, having_clause, order_clause)

    # _build_order_clause invalid key
    with pytest.raises(ValueError):
        qb._build_order_clause("name", func.count())

    # _build_order_clause callable and passthrough (avoid truthiness)
    desc_clause = qb._build_order_clause(lambda c: c.desc(), func.count())
    assert hasattr(desc_clause, "self_group")
    passthrough = qb._build_order_clause(func.count(), func.count())
    assert str(passthrough) == str(func.count())
