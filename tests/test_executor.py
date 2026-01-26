import pytest

from duo_orm.executor import (
    _resolve_db_target,
    _get_db_from_query,
    _get_db_from_instance,
    _get_db_from_class,
)


def test_resolve_db_target_requires_context():
    with pytest.raises(RuntimeError, match="Missing context"):
        _resolve_db_target()


class DummyQuery:
    db = None


class DummyModel:
    _db = None


class DummyInstance:
    __class__ = DummyModel


def test_resolve_db_target_without_db_raises():
    with pytest.raises(RuntimeError, match="Database not configured for this query"):
        _get_db_from_query(DummyQuery())
    with pytest.raises(RuntimeError, match="Database not configured for this model"):
        _get_db_from_instance(DummyInstance())
    with pytest.raises(RuntimeError, match="Database not configured for this model"):
        _get_db_from_class(DummyModel)
