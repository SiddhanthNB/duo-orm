# your_orm/exceptions.py

"""
This module contains the set of custom exceptions raised by your-orm.

Having custom exceptions allows users of the library to reliably catch
errors specific to the ORM's operation, rather than generic Python errors.
"""


class YourOrmError(Exception):
    """Base exception for all errors raised by your-orm."""
    pass


class ConfigurationError(YourOrmError):
    """
    Raised when there is a problem with the ORM's configuration.

    For example, if a required configuration file is missing or a
    database URL is not provided.
    """
    pass


class ObjectNotFoundError(YourOrmError):
    """
    Raised when a query that expects a single result finds none.

    For example, a `.one()` or `.get()` method would raise this.
    """
    pass


class MultipleObjectsFoundError(YourOrmError):
    """
    Raised when a query that expects a single result finds multiple.

    Similar to ObjectNotFoundError, this would be used by `.one()` or `.get()`.
    """
    pass


class InvalidQueryError(YourOrmError):
    """
    Raised when a query is constructed in an invalid way, for example
    by passing an unsupported operator.
    """
    pass


class UnsupportedOperationError(InvalidQueryError):
    """
    Raised when an operation is not supported by the current database dialect.

    For example, using JSONContains on a database that does not support JSON.
    """
    pass


class IntegrityError(YourOrmError):
    """
    Raised when a database integrity constraint is violated.

    This is a wrapper around the database driver's specific integrity error
    (e.g., sqlalchemy.exc.IntegrityError) to provide a consistent API.
    It typically signals a unique constraint violation.
    """
    pass


class ValidationError(YourOrmError):
    """
    Raised when model-level validation fails.

    Attributes:
        field (str | None): Optional field name associated with the error.
        detail (Any): Optional structured detail for the error.
    """

    def __init__(self, message: str, field: str | None = None, detail=None):
        super().__init__(message)
        self.field = field
        self.detail = detail
