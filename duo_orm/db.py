# duo_orm/db.py

from contextlib import contextmanager, asynccontextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.engine import make_url, URL

from .session import active_session_var, is_async_context
from .basemodel import _YourOrmMethods
from .exceptions import ConfigurationError


_DRIVER_CONFIG = {
    "postgresql": {
        "sync": "postgresql+psycopg",
        "async": "postgresql+psycopg",
    },
    "oracle": {
        "sync": "oracle+oracledb",
        "async": "oracle+oracledb_async",
    },
    "mysql": {
        "sync": "mysql+pymysql",
        "async": "mysql+asyncmy",
    },
    "mssql": {
        "sync": "mssql+pyodbc",
        "async": "mssql+aioodbc",
    },
    "sqlite": {
        "sync": "sqlite",
        "async": "sqlite+aiosqlite",
    },
}

_DIALECT_ALIASES = {
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "mysql": "mysql",
    "mariadb": "mysql",
    "mssql": "mssql",
    "sqlite": "sqlite",
    "oracle": "oracle",
}


def _normalize_dialect(url_str: str) -> tuple[URL, str]:
    """Parses a URL and normalizes the dialect."""
    try:
        parsed = make_url(url_str)
    except Exception as e:
        raise ConfigurationError(f"Invalid database URL: {e}") from e

    drivername = parsed.drivername or ""
    if "+" in drivername:
        raise ConfigurationError(
            "Do not include a driver in the database URL. Provide only the base dialect "
            "(e.g., 'postgresql://...'). Drivers are managed automatically."
        )

    base_dialect = _DIALECT_ALIASES.get(drivername.lower())
    if not base_dialect or base_dialect not in _DRIVER_CONFIG:
        raise ConfigurationError(f"Unsupported or unknown dialect '{drivername}'.")

    return parsed, base_dialect


def _resolve_urls(sync_url: str, async_url: str | None, derive_async: bool) -> tuple[str, str | None]:
    """Resolves and reconstructs final sync and async URLs with correct drivers."""
    parsed_sync, dialect = _normalize_dialect(sync_url)
    drivers = _DRIVER_CONFIG[dialect]

    resolved_sync_url = parsed_sync.set(drivername=drivers["sync"]).render_as_string(hide_password=False)
    resolved_async_url: str | None = None

    if async_url:
        parsed_async, dialect_async = _normalize_dialect(async_url)
        if dialect_async != dialect:
            raise ConfigurationError("async_url dialect must match the primary url dialect.")
        resolved_async_url = parsed_async.set(drivername=drivers["async"]).render_as_string(hide_password=False)
    elif derive_async:
        if drivers["async"] == "sqlite+aiosqlite" and parsed_sync.database == ":memory:":
            # aiosqlite can't share a memory space with stdlib sqlite3.
            # It must have its own :memory: identifier.
            memory_url = URL.create(drivername=drivers["async"], database=":memory:")
            resolved_async_url = memory_url.render_as_string(hide_password=False)
        else:
            resolved_async_url = parsed_sync.set(drivername=drivers["async"]).render_as_string(hide_password=False)

    return resolved_sync_url, resolved_async_url


class Database:
    """
    The main factory for creating a database connection and a model base class.

    This class manages database connections and sessions. Its most important role
    is to create a pre-configured, database-aware `Model` base class that
    user models will inherit from. Each instance of `Database` creates its own
    isolated `Model` class, preventing conflicts when working with multiple
    databases in a single application.

    Args:
        db_url (str): The primary, synchronous database connection URL.
            Do not include a driver (e.g., `+psycopg`).
        async_url (str, optional): The asynchronous database connection URL.
            If not provided, `derive_async` will attempt to create it.
        derive_async (bool): If `True` (default), an async URL is automatically
            derived from `db_url` by swapping the driver.
    """

    def __init__(self, db_url: str, *, async_url: str | None = None, derive_async: bool = True):
        if not db_url:
            raise ValueError("Database URL cannot be empty.")

        self._sync_url, self._async_url = _resolve_urls(db_url, async_url, derive_async)
        self._db_url = self._sync_url  # For backwards compatibility / default
        self._sync_engine = None
        self._async_engine = None
        self._sync_session_factory = None
        self._async_session_factory = None
        self._connected = False

        # Create a new, unique declarative base from SQLAlchemy.
        Base = declarative_base()

        # Manufacture the final, user-facing Model class by combining
        # SQLAlchemy's base with our custom Active Record methods.
        class Model(Base, _YourOrmMethods):
            __abstract__ = True
            # Inject a reference to this specific `db` instance
            # directly into the Model class itself.
            _db = self

        self.Model = Model
        """The declarative base model class tied to this database instance.

        All user models should inherit from this class.

        Example:
            db = Database("sqlite:///test.db")

            class User(db.Model):
                __tablename__ = "users"
                id: Mapped[int] = mapped_column(primary_key=True)
        """

    @property
    def url(self) -> str:
        """The primary (synchronous) database URL."""
        return self._sync_url

    @property
    def sync_url(self) -> str:
        """The fully-resolved synchronous database URL, including the driver."""
        return self._sync_url

    @property
    def async_url(self) -> str | None:
        """The fully-resolved asynchronous database URL, if configured."""
        return self._async_url

    @property
    def metadata(self):
        """The `MetaData` object associated with this database instance's models."""
        return self.Model.metadata

    @property
    def sync_engine(self):
        """The underlying synchronous SQLAlchemy `Engine`."""
        if not self._sync_url:
            raise RuntimeError("Sync engine is not configured for this Database.")
        if self._sync_engine is None:
            try:
                self._sync_engine = create_engine(self._sync_url)
            except Exception as exc:
                raise ConfigurationError(f"Failed to create sync engine for '{self._sync_url}'. Check URL and ensure driver is installed.") from exc
        return self._sync_engine

    @property
    def async_engine(self):
        """The underlying asynchronous SQLAlchemy `AsyncEngine`."""
        if not self._async_url:
            raise RuntimeError("Async engine is not configured for this Database.")
        if self._async_engine is None:
            try:
                self._async_engine = create_async_engine(self._async_url)
            except Exception as exc:
                raise ConfigurationError(f"Failed to create async engine for '{self._async_url}'. Check URL and ensure driver is installed.") from exc
        return self._async_engine

    @property
    def sync_session_factory(self) -> sessionmaker:
        """The factory for creating synchronous SQLAlchemy `Session` objects."""
        if self._sync_session_factory is None:
            self._sync_session_factory = sessionmaker(
                bind=self.sync_engine, expire_on_commit=False
            )
        return self._sync_session_factory

    @property
    def async_session_factory(self) -> sessionmaker:
        """The factory for creating asynchronous SQLAlchemy `AsyncSession` objects."""
        if self._async_session_factory is None:
            self._async_session_factory = sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return self._async_session_factory

    def connect(self):
        """
        Eagerly initialize engines to surface configuration errors early.

        This method attempts to create the sync and async engines, which can
        help catch problems like invalid URLs or missing drivers at application
        startup instead of on the first query. It is safe to call multiple times.
        """
        if self._connected:
            return
        if self._sync_url:
            _ = self.sync_engine
        if self._async_url:
            _ = self.async_engine
        self._connected = True

    @contextmanager
    def _sync_transaction_context(self):
        """Internal implementation of the sync transaction manager."""
        with self.sync_session_factory() as session:
            token = active_session_var.set(session)
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                active_session_var.reset(token)

    @asynccontextmanager
    async def _async_transaction_context(self):
        """Internal implementation of the async transaction manager."""
        async with self.async_session_factory() as session:
            token = active_session_var.set(session)
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                active_session_var.reset(token)

    def transaction(self):
        """
        Provides a context-managed transactional scope for database operations.

        This method is the heart of the Unit of Work pattern in Duo ORM.
        It automatically detects if it's in a sync or async context and returns
        the appropriate context manager. All database operations within the
        `with` or `async with` block will share a single session.

        The transaction is automatically committed if the block exits without
        an exception, and rolled back otherwise.

        Returns:
            A synchronous or asynchronous context manager.
        """
        if is_async_context():
            return self._async_transaction_context()
        return self._sync_transaction_context()

    @asynccontextmanager
    async def standalone_session(self):
        """
        Provides a raw, unmanaged SQLAlchemy `AsyncSession`.

        This is an "escape hatch" for advanced use cases that require direct
        control over the session, outside of Duo ORM's managed context.
        You are responsible for committing or rolling back the session.

        Yields:
            AsyncSession: A new, unmanaged SQLAlchemy AsyncSession.
        """
        async with self.async_session_factory() as session:
            yield session

    @contextmanager
    def sync_standalone_session(self):
        """
        Provides a raw, unmanaged synchronous SQLAlchemy `Session`.

        This is the synchronous version of `standalone_session`, intended for
        advanced use cases.

        Yields:
            Session: A new, unmanaged SQLAlchemy Session.
        """
        with self.sync_session_factory() as session:
            yield session
