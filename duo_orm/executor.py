# duo_orm/executor.py

from sqlalchemy import func, select, literal
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update

from .exceptions import ObjectNotFoundError, MultipleObjectsFoundError
from .session import active_session_var, is_async_context


def _get_db_from_query(query_builder):
    """Internal helper to get the db object from a QueryBuilder."""
    if not hasattr(query_builder, "db") or not query_builder.db:
        raise RuntimeError("Database not configured for this query.")
    return query_builder.db


def _get_db_from_instance(instance):
    """Internal helper to get the db object from a model instance."""
    if not hasattr(instance.__class__, "_db") or not instance.__class__._db:
        raise RuntimeError(
            "Database not configured for this model. "
            "Ensure your model inherits from a db.Model class."
        )
    return instance.__class__._db


def _get_db_from_class(cls):
    """Internal helper to get the db object from a model class."""
    if not hasattr(cls, "_db") or not cls._db:
        raise RuntimeError(
            "Database not configured for this model. "
            "Ensure your model inherits from a db.Model class."
        )
    return cls._db

def _resolve_db_target(*, query_builder=None, instance=None, cls=None):
    if query_builder is not None:
        return _get_db_from_query(query_builder)
    if instance is not None:
        return _get_db_from_instance(instance)
    if cls is not None:
        return _get_db_from_class(cls)
    raise RuntimeError("Missing context for resolving database target.")


def _run_with_session(
    *,
    query_builder=None,
    instance=None,
    cls=None,
    transactional: bool = False,
    work_sync,
    work_async,
):
    active_session = active_session_var.get(None)

    if is_async_context():

        async def _execute_async():
            if active_session is not None:
                return await work_async(active_session)
            db = _resolve_db_target(query_builder=query_builder, instance=instance, cls=cls)
            async with db.async_session_factory() as session:
                if transactional:
                    async with session.begin():
                        return await work_async(session)
                return await work_async(session)

        return _execute_async()

    if active_session is not None:
        return work_sync(active_session)

    db = _resolve_db_target(query_builder=query_builder, instance=instance, cls=cls)
    with db.sync_session_factory() as session:
        if transactional:
            with session.begin():
                return work_sync(session)
        return work_sync(session)


# --- READ OPERATIONS ---

def _first(query_builder):
    """Handles fetching the first record."""
    stmt = query_builder._statement

    def _sync(session):
        result = session.execute(stmt)
        return result.unique().scalars().first()

    async def _async(session):
        result = await session.execute(stmt)
        return result.unique().scalars().first()

    return _run_with_session(
        query_builder=query_builder,
        work_sync=_sync,
        work_async=_async,
    )

def _all(query_builder):
    """Handles fetching all records."""
    stmt = query_builder._statement

    def _sync(session):
        result = session.execute(stmt)
        return result.unique().scalars().all()

    async def _async(session):
        result = await session.execute(stmt)
        return result.unique().scalars().all()

    return _run_with_session(
        query_builder=query_builder,
        work_sync=_sync,
        work_async=_async,
    )

def _count(query_builder):
    """Handles counting the number of records for a query."""
    count_stmt = func.count().select().select_from(query_builder._statement.alias("subquery"))

    def _sync(session):
        result = session.execute(count_stmt)
        return result.scalar_one()

    async def _async(session):
        result = await session.execute(count_stmt)
        return result.scalar_one()

    return _run_with_session(
        query_builder=query_builder,
        work_sync=_sync,
        work_async=_async,
    )

def _one(query_builder):
    """Fetches exactly one record, raising if zero or multiple are found."""
    stmt = query_builder._statement.limit(2)

    def _handle_rows(rows):
        if not rows:
            raise ObjectNotFoundError(f"No {query_builder._model_cls.__name__} matches the query.")
        if len(rows) > 1:
            raise MultipleObjectsFoundError(
                f"Multiple {query_builder._model_cls.__name__} instances match the query."
            )
        return rows[0]

    def _sync(session):
        result = session.execute(stmt)
        rows = result.unique().scalars().all()
        return _handle_rows(rows)

    async def _async(session):
        result = await session.execute(stmt)
        rows = result.unique().scalars().all()
        return _handle_rows(rows)

    return _run_with_session(
        query_builder=query_builder,
        work_sync=_sync,
        work_async=_async,
    )

def _exists(query_builder):
    """Returns True if the query matches at least one record."""
    exists_expr = query_builder._statement.exists()
    # SQL Server (and some dialects) do not support `SELECT EXISTS (...)` directly.
    # Use `SELECT 1 WHERE EXISTS (...)` which is portable.
    exists_stmt = select(literal(True)).where(exists_expr).limit(1)
    def _sync(session):
        result = session.execute(exists_stmt)
        return bool(result.scalar())

    async def _async(session):
        result = await session.execute(exists_stmt)
        return bool(result.scalar())

    return _run_with_session(
        query_builder=query_builder,
        work_sync=_sync,
        work_async=_async,
    )


# --- WRITE OPERATIONS (Refactored) ---

def _save(instance):
    """Handles saving (INSERT/UPDATE) a model instance."""
    def _sync(session):
        session.add(instance)
        session.flush()

    async def _async(session):
        session.add(instance)
        await session.flush()

    return _run_with_session(
        instance=instance,
        transactional=True,
        work_sync=_sync,
        work_async=_async,
    )

def _delete_instance(instance):
    """Handles deleting a model instance."""
    def _sync(session):
        session.delete(instance)
        session.flush()

    async def _async(session):
        session.delete(instance)
        await session.flush()

    return _run_with_session(
        instance=instance,
        transactional=True,
        work_sync=_sync,
        work_async=_async,
    )

def _bulk_create(cls, instances):
    """Handles bulk creating model instances."""
    def _sync(session):
        session.add_all(instances)
        session.flush()

    async def _async(session):
        session.add_all(instances)
        await session.flush()

    return _run_with_session(
        cls=cls,
        transactional=True,
        work_sync=_sync,
        work_async=_async,
    )

def _update(query_builder, **values):
    """Handles bulk updates for a query."""
    update_stmt = sa_update(query_builder._model_cls).values(**values)
    where_clause = query_builder._statement.whereclause
    if where_clause is not None:
        update_stmt = update_stmt.where(where_clause)
    def _sync(session):
        session.execute(update_stmt)
        session.flush()

    async def _async(session):
        await session.execute(update_stmt)
        await session.flush()

    return _run_with_session(
        query_builder=query_builder,
        transactional=True,
        work_sync=_sync,
        work_async=_async,
    )

def _delete(query_builder):
    """Handles bulk deletes for a query."""
    delete_stmt = sa_delete(query_builder._model_cls)
    where_clause = query_builder._statement.whereclause
    if where_clause is not None:
        delete_stmt = delete_stmt.where(where_clause)
    def _sync(session):
        session.execute(delete_stmt)
        session.flush()

    async def _async(session):
        await session.execute(delete_stmt)
        await session.flush()

    return _run_with_session(
        query_builder=query_builder,
        transactional=True,
        work_sync=_sync,
        work_async=_async,
    )
