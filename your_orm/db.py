# your_orm/db.py

from contextlib import contextmanager, asynccontextmanager
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from .session import active_session_var, is_async_context


class Database:
    """
    The main class that manages database connections and sessions.

    An instance of this class is the primary configuration point for the ORM.
    It holds the synchronous and asynchronous SQLAlchemy engines and provides
    the context-aware transaction manager.
    """

    def __init__(self, db_url: str):
        if not db_url:
            raise ValueError("Database URL cannot be empty.")

        self._db_url = db_url
        self._sync_engine = None
        self._async_engine = None
        self._sync_session_factory = None
        self._async_session_factory = None

    @property
    def url(self) -> str:
        """Returns the configured database URL."""
        return self._db_url

    @property
    def sync_engine(self):
        """Lazily initializes and returns the synchronous SQLAlchemy engine."""
        if self._sync_engine is None:
            self._sync_engine = create_engine(self.url)
        return self._sync_engine

    @property
    def async_engine(self):
        """Lazily initializes and returns the asynchronous SQLAlchemy engine."""
        if self._async_engine is None:
            # We assume the user has provided an async-compatible DBAPI driver
            # in their URL (e.g., 'postgresql+psycopg').
            self._async_engine = create_async_engine(self.url)
        return self._async_engine

    @property
    def sync_session_factory(self) -> sessionmaker:
        """Lazily initializes and returns the synchronous session factory."""
        if self._sync_session_factory is None:
            self._sync_session_factory = sessionmaker(
                bind=self.sync_engine, expire_on_commit=False
            )
        return self._sync_session_factory

    @property
    def async_session_factory(self) -> sessionmaker:
        """Lazily initializes and returns the asynchronous session factory."""
        if self._async_session_factory is None:
            self._async_session_factory = sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return self._async_session_factory

    @contextmanager
    def _sync_transaction_context(self):
        """Internal context manager for synchronous transactions."""
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
        """Internal context manager for asynchronous transactions."""
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
        Returns a context-aware transaction manager.

        This is the primary method for handling explicit, atomic transactions.
        It will return either a synchronous or asynchronous context manager
        based on the execution context.
        """
        if is_async_context():
            return self._async_transaction_context()
        else:
            return self._sync_transaction_context()