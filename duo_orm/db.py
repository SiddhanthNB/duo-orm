# duo_orm/db.py

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncContextManager, AsyncGenerator, AsyncIterator, ContextManager, Generator, Optional, Tuple, Dict, Any, Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .session import active_session_var, is_async_context
from .basemodel import _DuoOrmMethods
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


def _normalize_dialect(url_str: str, *, expected: Optional[str] = None, context: Optional[str] = None) -> Tuple[URL, str]:
    """Parses a URL, normalizes the dialect, and optionally enforces an expected dialect."""
    try:
        parsed = make_url(url_str)
    except Exception as e:
        raise ConfigurationError(f"Invalid database URL: {e}") from e

    drivername = parsed.drivername or ""
    if "+" in drivername:
        raise ConfigurationError(
            f"Do not include a driver in the database URL (found '{drivername}'). "
            "Provide only the base dialect (e.g., 'postgresql://...'). Drivers are managed automatically."
        )

    base_dialect = _DIALECT_ALIASES.get(drivername.lower())
    if not base_dialect or base_dialect not in _DRIVER_CONFIG:
        raise ConfigurationError(f"Unsupported or unknown dialect '{drivername}'.")

    if expected:
        normalized_expected = _DIALECT_ALIASES.get(expected.lower())
        if normalized_expected is None:
            raise ConfigurationError(
                f"Unknown dialect '{expected}'. Accepted values: {', '.join(sorted(_DRIVER_CONFIG))}."
            )
        if normalized_expected != base_dialect:
            raise ConfigurationError(
                f"Dialect mismatch: expected '{normalized_expected}', got '{base_dialect}'."
            )

    return parsed, base_dialect


def _resolve_urls(sync_url: str, derive_async: bool, *, dialect: Optional[str]) -> Tuple[str, Optional[str]]:
    """Resolves and reconstructs final sync and async URLs with correct drivers."""
    parsed_sync, normalized = _normalize_dialect(sync_url, expected=dialect, context="explicit")
    drivers = _DRIVER_CONFIG[normalized]

    resolved_sync_url = parsed_sync.set(drivername=drivers["sync"]).render_as_string(hide_password=False)
    resolved_async_url: str | None = None

    if derive_async:
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
        derive_async (bool): If `True` (default), an async URL is automatically
            derived from `db_url` by swapping the driver.
        dialect (str, optional): Expected dialect name (e.g., "postgresql", "mysql").
            If provided, it must match the dialect parsed from `db_url`; otherwise an error is raised.
        engine_kwargs (dict, optional): Additional kwargs passed to both sync and async engines.
    """

    def __init__(
        self,
        db_url: str,
        *,
        derive_async: bool = True,
        dialect: Optional[str] = None,
        engine_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not db_url:
            raise ValueError("Database URL cannot be empty.")

        self._sync_url, self._async_url = _resolve_urls(db_url, derive_async, dialect=dialect)
        self._db_url = self._sync_url  # For backwards compatibility / default
        self._sync_engine: Optional[Engine] = None
        self._async_engine: Optional[AsyncEngine] = None
        self._sync_session_factory: Optional[sessionmaker] = None
        self._async_session_factory: Optional[sessionmaker] = None
        self._connected = False
        self._engine_kwargs = engine_kwargs or {}

        # Create a new, unique declarative base from SQLAlchemy.
        Base = declarative_base()

        # Manufacture the final, user-facing Model class by combining
        # SQLAlchemy's base with our custom Active Record methods.
        class Model(Base, _DuoOrmMethods):
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
    def async_url(self) -> Optional[str]:
        """The fully-resolved asynchronous database URL, if configured."""
        return self._async_url

    @property
    def metadata(self) -> MetaData:
        """The `MetaData` object associated with this database instance's models."""
        return self.Model.metadata

    @property
    def sync_engine(self) -> Engine:
        """The underlying synchronous SQLAlchemy `Engine`."""
        if not self._sync_url:
            raise RuntimeError("Sync engine is not configured for this Database.")
        if self._sync_engine is None:
            try:
                self._sync_engine = create_engine(self._sync_url, **self._engine_kwargs)
            except Exception as exc:
                raise ConfigurationError(f"Failed to create sync engine for '{self._sync_url}'. Check URL and ensure driver is installed.") from exc
        return self._sync_engine

    @property
    def async_engine(self) -> AsyncEngine:
        """The underlying asynchronous SQLAlchemy `AsyncEngine`."""
        if not self._async_url:
            raise RuntimeError("Async engine is not configured for this Database.")
        if self._async_engine is None:
            try:
                self._async_engine = create_async_engine(self._async_url, **self._engine_kwargs)
            except Exception as exc:
                raise ConfigurationError(f"Failed to create async engine for '{self._async_url}'. Check URL and ensure driver is installed.") from exc
        return self._async_engine

    def disconnect(self) -> None:
        """
        Disposes any initialized sync/async engines and resets cached factories.

        This is a convenience for scripts/CLIs that want to release connections
        before process exit. It is safe to call multiple times; subsequent
        access to `sync_engine`/`async_engine` will recreate engines lazily.
        """
        if self._sync_engine is not None:
            self._sync_engine.dispose()
            self._sync_engine = None
            self._sync_session_factory = None
        if self._async_engine is not None:
            # async engine exposes sync dispose that closes pools;
            # safe to call without awaiting.
            self._async_engine.sync_engine.dispose()
            self._async_engine = None
            self._async_session_factory = None

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

    def connect(self) -> None:
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
    def _sync_transaction_context(self) -> Iterator[Session]:
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
    async def _async_transaction_context(self) -> AsyncIterator[AsyncSession]:
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

    def transaction(self) -> ContextManager[Session] | AsyncContextManager[AsyncSession]:
        """
        Provides a context-managed transactional scope for database operations.

        This method is the heart of the Unit of Work pattern in DuoORM.
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
    async def standalone_session(self) -> AsyncIterator[AsyncSession]:
        """
        Provides a raw, unmanaged SQLAlchemy `AsyncSession`.

        This is an "escape hatch" for advanced use cases that require direct
        control over the session, outside of DuoORM's managed context.
        You are responsible for committing or rolling back the session.

        Yields:
            AsyncSession: A new, unmanaged SQLAlchemy AsyncSession.
        """
        async with self.async_session_factory() as session:
            yield session

    @contextmanager
    def sync_standalone_session(self) -> Iterator[Session]:
        """
        Provides a raw, unmanaged synchronous SQLAlchemy `Session`.

        This is the synchronous version of `standalone_session`, intended for
        advanced use cases.

        Yields:
            Session: A new, unmanaged SQLAlchemy Session.
        """
        with self.sync_session_factory() as session:
            yield session
