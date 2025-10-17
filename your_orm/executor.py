# your_orm/executor.py

from .session import is_async_context, active_session_var


def _get_session_or_raise(query_builder):
    """Internal helper to get the session from a QueryBuilder's db object."""
    # In a real implementation, this would be more robust, potentially
    # accessing a globally configured db object if not on the builder.
    if not hasattr(query_builder, "db") or not query_builder.db:
        raise RuntimeError("Database not configured for this query.")
    return query_builder.db


def _first(query_builder):
    """
    Handles fetching the first record. This single function contains
    the logic for both sync and async execution, including Autosession.
    """
    if is_async_context():
        # Async Path: Define and return an awaitable.
        async def _execute_async():
            try:
                # Use existing session from a transaction block if available.
                session = active_session_var.get()
                result = await session.execute(query_builder._statement)
                return result.scalars().first()
            except LookupError:
                # Autosession: Create a temporary session for this single operation.
                db = _get_session_or_raise(query_builder)
                async with db.async_session_factory() as session:
                    result = await session.execute(query_builder._statement)
                    return result.scalars().first()

        return _execute_async()
    else:
        # Sync Path: Execute directly and return the final value.
        try:
            session = active_session_var.get()
            result = session.execute(query_builder._statement)
            return result.scalars().first()
        except LookupError:
            db = _get_session_or_raise(query_builder)
            with db.sync_session_factory() as session:
                result = session.execute(query_builder._statement)
                return result.scalars().first()


def _all(query_builder):
    """Handles fetching all records."""
    if is_async_context():
        async def _execute_async():
            try:
                session = active_session_var.get()
                result = await session.execute(query_builder._statement)
                return result.scalars().all()
            except LookupError:
                db = _get_session_or_raise(query_builder)
                async with db.async_session_factory() as session:
                    result = await session.execute(query_builder._statement)
                    return result.scalars().all()

        return _execute_async()
    else:
        try:
            session = active_session_var.get()
            result = session.execute(query_builder._statement)
            return result.scalars().all()
        except LookupError:
            db = _get_session_or_raise(query_builder)
            with db.sync_session_factory() as session:
                result = session.execute(query_builder._statement)
                return result.scalars().all()


def _save(instance):
    """Handles saving (INSERT/UPDATE) a model instance."""
    if is_async_context():
        async def _execute_async():
            try:
                session = active_session_var.get()
                session.add(instance)
                await session.flush()
            except LookupError:
                # This part is complex. For Autosession, we'd need to
                # get the db object associated with the instance's class.
                # This is a simplification for now.
                print("NOTE: Async Autosession for .save() requires db configuration.")
                pass
        return _execute_async()
    else:
        try:
            session = active_session_var.get()
            session.add(instance)
            session.flush()
        except LookupError:
            print("NOTE: Sync Autosession for .save() requires db configuration.")
            pass


def _delete(instance):
    """Handles deleting a model instance."""
    if is_async_context():
        async def _execute_async():
            try:
                session = active_session_var.get()
                await session.delete(instance)
                await session.flush()
            except LookupError:
                print("NOTE: Async Autosession for .delete() requires db configuration.")
                pass
        return _execute_async()
    else:
        try:
            session = active_session_var.get()
            session.delete(instance)
            session.flush()
        except LookupError:
            print("NOTE: Sync Autosession for .delete() requires db configuration.")
            pass