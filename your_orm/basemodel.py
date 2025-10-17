# your_orm/basemodel.py

from sqlalchemy import Column as SAColumn
from sqlalchemy import types as SATypes
from sqlalchemy.orm import DeclarativeBase

# We will implement QueryBuilder in a later step. For now, we import it
# with the knowledge of what its API will be.
from .query import QueryBuilder


class BaseModel(DeclarativeBase):
    """
    The base class for all user-defined models.

    This class provides the core Active Record-style API (.where(), .save(), etc.)
    and integrates with SQLAlchemy's declarative mapping system.
    """

    # --- Class-level Querying API ---

    @classmethod
    def _get_query_builder(cls) -> "QueryBuilder":
        """Internal helper to create a QueryBuilder for this model."""
        return QueryBuilder(cls)

    @classmethod
    def where(cls, **kwargs) -> "QueryBuilder":
        """
        Starts a query with a WHERE clause.

        Example:
            User.where(name="Alice")
        """
        return cls._get_query_builder().where(**kwargs)

    @classmethod
    def all(cls):
        """
        Fetches all records for this model.

        Example:
            all_users = User.all()
        """
        return cls._get_query_builder().all()

    @classmethod
    def first(cls):
        """

        Fetches the first record for this model.

        Example:
            one_user = User.first()
        """
        return cls._get_query_builder().first()

    @classmethod
    def bulk_create(cls, instances: list):
        """
        Performs a bulk insert of multiple model instances.

        Example:
            User.bulk_create([User(name="Alice"), User(name="Bob")])
        """
        # This will be implemented in the executor, but the entry point is here.
        # For now, it's a placeholder. In the final version, this would
        # call a function like _bulk_create(cls, instances).
        pass

    # --- Instance-level Actions ---

    def save(self):
        """
        Saves the current instance to the database.

        Handles both INSERT (for new objects) and UPDATE (for existing ones).
        This is a terminal method that will be implemented in the executor.

        Example:
            user = User(name="Charlie")
            user.save() # Performs an INSERT
            user.name = "Charles"
            user.save() # Performs an UPDATE
        """
        # A placeholder for the executor call, e.g., _save(self)
        pass

    def delete(self):
        """
        Deletes the current instance from the database.
        This is a terminal method that will be implemented in the executor.

        Example:
            user = User.where(id=1).first()
            user.delete()
        """
        # A placeholder for the executor call, e.g., _delete(self)
        pass


# --- Convenience Re-exports ---
# This allows the user to write `from your_orm import Column, types`
# instead of having to import them from SQLAlchemy directly.
Column = SAColumn
types = SATypes