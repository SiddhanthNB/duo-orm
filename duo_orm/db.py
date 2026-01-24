# duo_orm/db.py

from contextlib import contextmanager, asynccontextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.engine import make_url

from .session import active_session_var, is_async_context
from .basemodel import _YourOrmMethods


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


def _normalize_dialect(url_str: str) -> tuple:
    parsed = make_url(url_str)
    drivername = parsed.drivername or ""
    if "+" in drivername:
        raise ValueError(
            "Do not include driver in URLs. Provide only the base dialect "
            "(e.g., postgresql://..., mysql://..., sqlite:///...). "
            "Drivers are managed automatically."
        )
    base = _DIALECT_ALIASES.get(drivername.lower())
    if not base or base not in _DRIVER_CONFIG:
        raise ValueError(f"Unsupported or unknown dialect '{drivername}'.")
    return parsed, base


def _resolve_urls(sync_url: str, async_url: str | None, derive_async: bool) -> tuple[str, str | None]:
    parsed_sync, dialect = _normalize_dialect(sync_url)
    drivers = _DRIVER_CONFIG[dialect]

    resolved_sync = parsed_sync.set(drivername=drivers["sync"])
    resolved_async: str | None = None

    if async_url:
        parsed_async, dialect_async = _normalize_dialect(async_url)
        if dialect_async != dialect:
            raise ValueError("async_url dialect must match the primary url dialect.")
        resolved_async = parsed_async.set(drivername=drivers["async"]).render_as_string(hide_password=False)
    elif derive_async:
        resolved_async = parsed_sync.set(drivername=drivers["async"]).render_as_string(hide_password=False)

    return resolved_sync.render_as_string(hide_password=False), resolved_async


class Database:
    """
    The main class that manages database connections and sessions.

    This class acts as a factory for a pre-configured, database-aware
    base model class that users will inherit from.
    """

    def __init__(self, db_url: str, *, async_url: str | None = None, derive_async: bool = True):
        if not db_url:
            raise ValueError("Database URL cannot be empty.")

        self._sync_url, self._async_url = _resolve_urls(db_url, async_url, derive_async)
        self._db_url = self._sync_url
        self._sync_engine = None
        self._async_engine = None
        self._sync_session_factory = None
        self._async_session_factory = None
        self._connected = False

        # --- This is the new "factory" logic ---

        # 1. Create a new, unique declarative base from SQLAlchemy.
        Base = declarative_base()

        # 2. Manufacture the final, user-facing Model class by combining
        #    SQLAlchemy's base with our custom Active Record methods.
        class Model(Base, _YourOrmMethods):
            __abstract__ = True  # make the factory base unmapped; user models define tables
            # This is the magic link that solves the flaw!
            # We inject a reference to this specific `db` instance
            # directly into the Model class itself.
            _db = self

        # 3. Attach the newly created Model class as an attribute to this
        #    instance, so the user can access it via `db.Model`.
        self.Model = Model

    @property
    def url(self):
        return self._db_url

    @property
    def sync_url(self):
        return self._sync_url

    @property
    def async_url(self):
        return self._async_url

    @property
    def metadata(self):
        """Returns the metadata from the manufactured Model class."""
        # The metadata is now correctly associated with this db instance's models.
        return self.Model.metadata

    # --- The rest of the class remains the same ---

    @property
    def sync_engine(self):
        if not self._sync_url:
            raise RuntimeError("Sync engine is not configured for this Database.")
        if self._sync_engine is None:
            try:
                self._sync_engine = create_engine(self._sync_url)
            except TypeError as exc:
                query_keys = make_url(self._sync_url).query.keys()
                hint = ""
                if query_keys:
                    hint = (
                        f" URL includes query parameters {sorted(query_keys)}; "
                        "verify they are supported by the chosen driver."
                    )
                raise TypeError(f"Failed to create sync engine: {exc}.{hint}") from exc
        return self._sync_engine

    @property
    def async_engine(self):
        if not self._async_url:
            raise RuntimeError("Async engine is not configured for this Database.")
        if self._async_engine is None:
            try:
                self._async_engine = create_async_engine(self._async_url)
            except TypeError as exc:
                query_keys = make_url(self._async_url).query.keys()
                hint = ""
                if query_keys:
                    hint = (
                        f" URL includes query parameters {sorted(query_keys)}; "
                        "verify they are supported by the chosen driver."
                    )
                raise TypeError(f"Failed to create async engine: {exc}.{hint}") from exc
        return self._async_engine

    @property
    def sync_session_factory(self) -> sessionmaker:
        if self._sync_session_factory is None:
            self._sync_session_factory = sessionmaker(
                bind=self.sync_engine, expire_on_commit=False
            )
        return self._sync_session_factory

    @property
    def async_session_factory(self) -> sessionmaker:
        if self._async_session_factory is None:
            self._async_session_factory = sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return self._async_session_factory

    def connect(self):
        """
        Eagerly initialize engines and session factories to surface configuration errors early.
        Safe to call multiple times.
        """
        if self._connected:
            return
        # Touch available factories so any misconfiguration (bad URL, missing driver, etc.) raises immediately.
        if self._sync_url:
            _ = self.sync_engine
            _ = self.sync_session_factory
        if self._async_url:
            _ = self.async_engine
            _ = self.async_session_factory
        self._connected = True

    @contextmanager
    def _sync_transaction_context(self):
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
        if is_async_context():
            return self._async_transaction_context()
        else:
            return self._sync_transaction_context()

    @asynccontextmanager
    async def standalone_session(self):
        """Provides a raw, unmanaged SQLAlchemy AsyncSession."""
        async with self.async_session_factory() as session:
            yield session

    @contextmanager
    def sync_standalone_session(self):
        """Provides a raw, unmanaged SQLAlchemy Session."""
        with self.sync_session_factory() as session:
            yield session
