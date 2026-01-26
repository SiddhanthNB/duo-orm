# duo_orm/__init__.py

"""
DuoORM: An opinionated, modern ORM for Python.

This package provides a clean, symmetrical API for synchronous and
asynchronous database operations, built on SQLAlchemy 2.0.
"""

__version__ = "0.1.1"

# Apply lightweight operator ergonomics
from . import patch  # noqa: F401

# --- Import and re-export all common components for a modern 2.0 workflow ---

# 1. The Core Factory
from .db import Database

# 2. The Model Kit (Modern 2.0 Style)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# 3. The Associations & Constraints Kit
from sqlalchemy import Table, ForeignKey, UniqueConstraint, CheckConstraint, Index, not_

# 4. The Types Kit
from sqlalchemy import (
    types,
    Integer,
    BigInteger,
    SmallInteger,
    String,
    Text,
    Boolean,
    DateTime,
    Date,
    Time,
    Float,
    Numeric,
    UUID,
    JSON,
    LargeBinary,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY

# 5. The SQL Functions & Helpers Kit
from sqlalchemy import func, text, select

# 6. The Lifecycle Events Kit
from sqlalchemy import event

# 7. The Custom Exceptions
from .exceptions import (
    DuoOrmError,
    ConfigurationError,
    ObjectNotFoundError,
    MultipleObjectsFoundError,
    InvalidQueryError,
    UnsupportedOperationError,
    IntegrityError,
    ValidationError,
)
from .query import json, array


__all__ = [
    # Core Factory
    "Database",
    # Model Kit
    "Mapped",
    "mapped_column",
    "relationship",  # Often used in model definition
    # Associations & Constraints Kit
    "Table",
    "ForeignKey",
    "UniqueConstraint",
    "CheckConstraint",
    "Index",
    "not_",
    # Types Kit
    "types",
    "Integer",
    "BigInteger",
    "SmallInteger",
    "String",
    "Text",
    "Boolean",
    "DateTime",
    "Date",
    "Time",
    "Float",
    "Numeric",
    "UUID",
    "JSON",
    "LargeBinary",
    "PG_ARRAY",
    # SQL Functions & Helpers Kit
    "func",
    "text",
    "select",
    # Lifecycle Events Kit
    "event",
    # Custom Exceptions
    "DuoOrmError",
    "ConfigurationError",
    "ObjectNotFoundError",
    "MultipleObjectsFoundError",
    "InvalidQueryError",
    "UnsupportedOperationError",
    "IntegrityError",
    "ValidationError",
    "json",
    "array",
]
