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

    For example, a `.one()` method would raise this instead of returning `None`.
    """
    pass


class MultipleObjectsFoundError(YourOrmError):
    """
    Raised when a query that expects a single result finds multiple.

    Similar to ObjectNotFoundError, this would be used by a `.one()` method.
    """
    pass