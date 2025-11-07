# your_orm/__init__.py

"""
your-orm: An opinionated, modern ORM for Python.

This package provides a clean, symmetrical API for synchronous and
asynchronous database operations, built on SQLAlchemy 2.0.
"""

__version__ = "0.1.0"

# Apply the patch for custom operators
from . import patch

# --- Import and re-export all common components for a modern 2.0 workflow ---

# 1. The Core Factory
from .db import Database

# 2. The Model Kit (Modern 2.0 Style)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# 3. The Associations & Constraints Kit
from sqlalchemy import Table, ForeignKey, UniqueConstraint, CheckConstraint, Index, not_

# 4. The Types Kit
from sqlalchemy import types

# 5. The SQL Functions & Helpers Kit
from sqlalchemy import func, text, select

# 6. The Lifecycle Events Kit
from sqlalchemy import event

# 7. The Custom Exceptions
from .exceptions import (
    YourOrmError,
    ConfigurationError,
    ObjectNotFoundError,
    MultipleObjectsFoundError,
    InvalidQueryError,
    UnsupportedOperationError,
    IntegrityError,
    ValidationError,
)


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
    # SQL Functions & Helpers Kit
    "func",
    "text",
    "select",
    # Lifecycle Events Kit
    "event",
    # Custom Exceptions
    "YourOrmError",
    "ConfigurationError",
    "ObjectNotFoundError",
    "MultipleObjectsFoundError",
    "InvalidQueryError",
    "UnsupportedOperationError",
    "IntegrityError",
    "ValidationError",
]
