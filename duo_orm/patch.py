"""
Convenience extensions for SQLAlchemy InstrumentedAttribute objects.

These wrappers enforce string-only usage and provide case-insensitive helpers
so callers can stick to a consistent, pythonic API without remembering SQL
patterns.
"""

from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql import sqltypes


STRING_TYPES = (sqltypes.String,)

_SQLA_CONTAINS = InstrumentedAttribute.contains
_SQLA_STARTSWITH = InstrumentedAttribute.startswith
_SQLA_ENDSWITH = InstrumentedAttribute.endswith


def _assert_string_column(attr: InstrumentedAttribute, op_name: str) -> None:
    column_type = getattr(attr, "type", None)
    if column_type is None or not isinstance(column_type, STRING_TYPES):
        raise TypeError(f"{op_name}() is only available on string-like columns.")


def contains(self: InstrumentedAttribute, value: str):
    """
    Case-sensitive substring match (wraps SQLAlchemy's contains for consistency).
    """
    _assert_string_column(self, "contains")
    return _SQLA_CONTAINS(self, value)


def startswith(self: InstrumentedAttribute, prefix: str):
    _assert_string_column(self, "startswith")
    return _SQLA_STARTSWITH(self, prefix)


def endswith(self: InstrumentedAttribute, suffix: str):
    _assert_string_column(self, "endswith")
    return _SQLA_ENDSWITH(self, suffix)


def icontains(self: InstrumentedAttribute, value: str):
    """
    Case-insensitive substring match (equivalent to ILIKE %value%).
    """
    _assert_string_column(self, "icontains")
    return self.ilike(f"%{value}%")


def istartswith(self: InstrumentedAttribute, prefix: str):
    """
    Case-insensitive prefix match.
    """
    _assert_string_column(self, "istartswith")
    return self.ilike(f"{prefix}%")


def iendswith(self: InstrumentedAttribute, suffix: str):
    """
    Case-insensitive suffix match.
    """
    _assert_string_column(self, "iendswith")
    return self.ilike(f"%{suffix}")


InstrumentedAttribute.contains = contains  # type: ignore[assignment]
InstrumentedAttribute.startswith = startswith  # type: ignore[assignment]
InstrumentedAttribute.endswith = endswith  # type: ignore[assignment]
InstrumentedAttribute.icontains = icontains  # type: ignore[attr-defined]
InstrumentedAttribute.istartswith = istartswith  # type: ignore[attr-defined]
InstrumentedAttribute.iendswith = iendswith  # type: ignore[attr-defined]
