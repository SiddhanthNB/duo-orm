# your_orm/executor.py

from sqlalchemy import func, select
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

# --- READ OPERATIONS (Refactored) ---

def _first(query_builder):
    """Handles fetching the first record."""
    active_session = active_session_var.get(None)

    if is_async_context():
        async def _execute_async():
            if active_session:
                result = await active_session.execute(query_builder._statement)
                return result.scalars().first()
            else:
                db = _get_db_from_query(query_builder)
                async with db.async_session_factory() as session:
                    result = await session.execute(query_builder._statement)
                    return result.scalars().first()
        return _execute_async()
    else:
        if active_session:
            result = active_session.execute(query_builder._statement)
            return result.scalars().first()
        else:
            db = _get_db_from_query(query_builder)
            with db.sync_session_factory() as session:
                result = session.execute(query_builder._statement)
                return result.scalars().first()

def _all(query_builder):
    """Handles fetching all records."""
    active_session = active_session_var.get(None)
    if is_async_context():
        async def _execute_async():
            if active_session:
                result = await active_session.execute(query_builder._statement)
                return result.scalars().all()
            else:
                db = _get_db_from_query(query_builder)
                async with db.async_session_factory() as session:
                    result = await session.execute(query_builder._statement)
                    return result.scalars().all()
        return _execute_async()
    else:
        if active_session:
            result = active_session.execute(query_builder._statement)
            return result.scalars().all()
        else:
            db = _get_db_from_query(query_builder)
            with db.sync_session_factory() as session:
                result = session.execute(query_builder._statement)
                return result.scalars().all()

def _count(query_builder):
    """Handles counting the number of records for a query."""
    active_session = active_session_var.get(None)
    count_stmt = func.count().select().select_from(query_builder._statement.alias("subquery"))

    if is_async_context():
        async def _execute_async():
            if active_session:
                result = await active_session.execute(count_stmt)
                return result.scalar_one()
            else:
                db = _get_db_from_query(query_builder)
                async with db.async_session_factory() as session:
                    result = await session.execute(count_stmt)
                    return result.scalar_one()
        return _execute_async()
    else:
        if active_session:
            result = active_session.execute(count_stmt)
            return result.scalar_one()
        else:
            db = _get_db_from_query(query_builder)
            with db.sync_session_factory() as session:
                result = session.execute(count_stmt)
                return result.scalar_one()

def _one(query_builder):
    """Fetches exactly one record, raising if zero or multiple are found."""
    active_session = active_session_var.get(None)
    stmt = query_builder._statement.limit(2)

    def _handle_rows(rows):
        if not rows:
            raise ObjectNotFoundError(f"No {query_builder._model_cls.__name__} matches the query.")
        if len(rows) > 1:
            raise MultipleObjectsFoundError(
                f"Multiple {query_builder._model_cls.__name__} instances match the query."
            )
        return rows[0]

    if is_async_context():
        async def _execute_async():
            if active_session:
                result = await active_session.execute(stmt)
            else:
                db = _get_db_from_query(query_builder)
                async with db.async_session_factory() as session:
                    result = await session.execute(stmt)
            rows = result.scalars().all()
            return _handle_rows(rows)
        return _execute_async()
    else:
        if active_session:
            result = active_session.execute(stmt)
        else:
            db = _get_db_from_query(query_builder)
            with db.sync_session_factory() as session:
                result = session.execute(stmt)
        rows = result.scalars().all()
        return _handle_rows(rows)

def _exists(query_builder):
    """Returns True if the query matches at least one record."""
    active_session = active_session_var.get(None)
    exists_stmt = select(query_builder._statement.exists())

    if is_async_context():
        async def _execute_async():
            if active_session:
                result = await active_session.execute(exists_stmt)
            else:
                db = _get_db_from_query(query_builder)
                async with db.async_session_factory() as session:
                    result = await session.execute(exists_stmt)
            return bool(result.scalar())
        return _execute_async()
    else:
        if active_session:
            result = active_session.execute(exists_stmt)
        else:
            db = _get_db_from_query(query_builder)
            with db.sync_session_factory() as session:
                result = session.execute(exists_stmt)
        return bool(result.scalar())


# --- WRITE OPERATIONS (Refactored) ---

def _save(instance):
    """Handles saving (INSERT/UPDATE) a model instance."""
    active_session = active_session_var.get(None)

    if is_async_context():
        async def _execute_async():
            if active_session:
                active_session.add(instance)
                await active_session.flush()
            else:
                db = _get_db_from_instance(instance)
                async with db.async_session_factory() as session:
                    async with session.begin():
                        session.add(instance)
        return _execute_async()
    else:
        if active_session:
            active_session.add(instance)
            active_session.flush()
        else:
            db = _get_db_from_instance(instance)
            with db.sync_session_factory() as session:
                with session.begin():
                    session.add(instance)

def _delete_instance(instance):
    """Handles deleting a model instance."""
    active_session = active_session_var.get(None)

    if is_async_context():
        async def _execute_async():
            if active_session:
                active_session.delete(instance)
                await active_session.flush()
            else:
                db = _get_db_from_instance(instance)
                async with db.async_session_factory() as session:
                    async with session.begin():
                        session.delete(instance)
        return _execute_async()
    else:
        if active_session:
            active_session.delete(instance)
            active_session.flush()
        else:
            db = _get_db_from_instance(instance)
            with db.sync_session_factory() as session:
                with session.begin():
                    session.delete(instance)

def _bulk_create(cls, instances):
    """Handles bulk creating model instances."""
    active_session = active_session_var.get(None)

    if is_async_context():
        async def _execute_async():
            if active_session:
                active_session.add_all(instances)
                await active_session.flush()
            else:
                db = _get_db_from_class(cls)
                async with db.async_session_factory() as session:
                    async with session.begin():
                        session.add_all(instances)
        return _execute_async()
    else:
        if active_session:
            active_session.add_all(instances)
            active_session.flush()
        else:
            db = _get_db_from_class(cls)
            with db.sync_session_factory() as session:
                with session.begin():
                    session.add_all(instances)

def _update(query_builder, **values):
    """Handles bulk updates for a query."""
    active_session = active_session_var.get(None)
    update_stmt = sa_update(query_builder._model_cls).values(**values)
    where_clause = query_builder._statement.whereclause
    if where_clause is not None:
        update_stmt = update_stmt.where(where_clause)

    if is_async_context():
        async def _execute_async():
            if active_session:
                await active_session.execute(update_stmt)
                await active_session.flush()
            else:
                db = _get_db_from_query(query_builder)
                async with db.async_session_factory() as session:
                    async with session.begin():
                        await session.execute(update_stmt)
        return _execute_async()
    else:
        if active_session:
            active_session.execute(update_stmt)
            active_session.flush()
        else:
            db = _get_db_from_query(query_builder)
            with db.sync_session_factory() as session:
                with session.begin():
                    session.execute(update_stmt)

def _delete(query_builder):
    """Handles bulk deletes for a query."""
    active_session = active_session_var.get(None)
    delete_stmt = sa_delete(query_builder._model_cls)
    where_clause = query_builder._statement.whereclause
    if where_clause is not None:
        delete_stmt = delete_stmt.where(where_clause)

    if is_async_context():
        async def _execute_async():
            if active_session:
                await active_session.execute(delete_stmt)
                await active_session.flush()
            else:
                db = _get_db_from_query(query_builder)
                async with db.async_session_factory() as session:
                    async with session.begin():
                        await session.execute(delete_stmt)
        return _execute_async()
    else:
        if active_session:
            active_session.execute(delete_stmt)
            active_session.flush()
        else:
            db = _get_db_from_query(query_builder)
            with db.sync_session_factory() as session:
                with session.begin():
                    session.execute(delete_stmt)
