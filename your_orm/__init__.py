# your_orm/__init__.py

"""
your-orm: An opinionated, modern ORM for Python.

This package provides a clean, symmetrical API for synchronous and
asynchronous database operations, built on SQLAlchemy 2.0.
"""

__version__ = "0.1.0"

from .db import Database
from .basemodel import BaseModel, Column, types

# The __all__ variable defines the public API of the package.
# When a user writes `from your_orm import *`, only these names
# will be imported. It's a best practice for library design.
__all__ = [
    "Database",
    "BaseModel",
    "Column",
    "types",
]