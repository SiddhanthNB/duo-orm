# your_orm/db.py

from contextlib import contextmanager, asynccontextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from .session import active_session_var, is_async_context
from .basemodel import _YourOrmMethods


class Database:
    """
    The main class that manages database connections and sessions.

    This class acts as a factory for a pre-configured, database-aware
    base model class that users will inherit from.
    """

    def __init__(self, db_url: str):
        if not db_url:
            raise ValueError("Database URL cannot be empty.")

        self._db_url = db_url
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
    def metadata(self):
        """Returns the metadata from the manufactured Model class."""
        # The metadata is now correctly associated with this db instance's models.
        return self.Model.metadata

    # --- The rest of the class remains the same ---

    @property
    def sync_engine(self):
        if self._sync_engine is None:
            self._sync_engine = create_engine(self.url)
        return self._sync_engine

    @property
    def async_engine(self):
        if self._async_engine is None:
            self._async_engine = create_async_engine(self.url)
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
        # Touch all factories so any misconfiguration (bad URL, missing driver, etc.) raises immediately.
        _ = self.sync_engine
        _ = self.async_engine
        _ = self.sync_session_factory
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
