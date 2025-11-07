# your_orm/session.py

import asyncio
from contextvars import ContextVar
from typing import Union

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

# This ContextVar is the heart of our context-aware session management.
# It acts as a task-safe (or thread-safe) global variable that holds the
# active session for the current unit of work (e.g., a web request or a
# transaction block).
#
# The rest of the ORM will use .get() on this variable to find the
# currently active session.
active_session_var: ContextVar[Union[Session, AsyncSession]] = ContextVar("active_session")


def is_async_context() -> bool:
    """
    Checks if the code is currently running inside an asyncio event loop.

    This is the primary mechanism our dispatcher functions use to decide
    whether to run synchronous or asynchronous database logic.

    Returns:
        bool: True if inside an event loop, False otherwise.
    """
    try:
        # This will succeed if an event loop is running in the current thread.
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        # get_running_loop() raises a RuntimeError if no loop is running.
        return False