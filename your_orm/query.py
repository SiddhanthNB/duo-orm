# your_orm/query.py

from __future__ import annotations
from typing import TYPE_CHECKING, Type, TypeVar

from sqlalchemy import select

from .executor import _first, _all, _update, _delete

# This helps with type hinting for the model class itself.
T = TypeVar("T")

if TYPE_CHECKING:
    from .db import Database


class QueryBuilder:
    """
    A chainable, fluent query builder.

    This class is the core of the ORM's query-building API. It constructs
    a SQLAlchemy statement internally and provides terminal methods
    (like .first(), .all()) to execute it.
    """

    def __init__(self, model_cls: Type[T], db: "Database"):
        """
        Initializes the QueryBuilder.

        Args:
            model_cls: The user's model class (e.g., User).
            db: The configured Database instance.
        """
        if not db:
            raise RuntimeError(
                "QueryBuilder cannot be initialized without a Database instance. "
                "Ensure your BaseModel is correctly associated with your db object."
            )
        self._model_cls = model_cls
        self.db = db
        # The internal state: a SQLAlchemy Select object.
        self._statement = select(self._model_cls)

    def where(self, **kwargs) -> "QueryBuilder[T]":
        """
        Adds a WHERE clause to the query based on keyword arguments.

        Example:
            User.where(name="Alice", is_active=True)

        Returns:
            The QueryBuilder instance, to allow for chaining.
        """
        for key, value in kwargs.items():
            if not hasattr(self._model_cls, key):
                raise AttributeError(
                    f"'{self._model_cls.__name__}' has no attribute '{key}'"
                )
            column = getattr(self._model_cls, key)
            self._statement = self._statement.where(column == value)
        return self

    def alchemize(self):
        """
        The "escape hatch".

        Transmutes the current high-level query into a raw
        SQLAlchemy Select object for advanced customization.

        Returns:
            sqlalchemy.sql.Select: The underlying query object.
        """
        return self._statement

    # --- Terminal Methods ---
    # These methods delegate directly to the unified, context-aware
    # functions in the executor module. The executor functions are
    # responsible for handling the sync/async forking.

    first = _first
    all = _all
    update = _update
    delete = _delete
    # count = _count # Would be added in the same way