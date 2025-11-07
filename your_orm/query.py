# your_orm/query.py

from __future__ import annotations
from typing import TYPE_CHECKING, Type, TypeVar, List, Optional, Sequence, Callable, Any

from sqlalchemy import select, func, and_, true, inspect as sa_inspect
from sqlalchemy.orm import RelationshipProperty, joinedload, selectinload

from .executor import _first, _all, _update, _delete, _count, _one, _exists

# This helps with type hinting for the model class itself.
T = TypeVar("T")

if TYPE_CHECKING:
    from .db import Database


class QueryBuilder:
    """
    A chainable, fluent query builder.

    This class is the core of the ORM's query-building API. It constructs
    a SQLAlchemy statement internally and provides terminal methods
    (like .first(), .all()) to execute it.
    """

    def __init__(self, model_cls: Type[T], db: "Database"):
        """
        Initializes the QueryBuilder.

        Args:
            model_cls: The user's model class (e.g., User).
            db: The configured Database instance.
        """
        if not db:
            raise RuntimeError(
                "QueryBuilder cannot be initialized without a Database instance. "
                "Ensure your BaseModel is correctly associated with your db object."
            )
        self._model_cls = model_cls
        self.db = db
        # The internal state: a SQLAlchemy Select object.
        self._statement = select(self._model_cls)
        self._related_used = False

    def where(self, *args) -> "QueryBuilder[T]":
        """
        Adds a WHERE clause to the query.

        Accepts one or more SQLAlchemy expressions.

        Example:
            User.where(User.name == "Alice", User.age > 30)
        """
        self._statement = self._statement.where(*args)
        return self

    def order_by(self, *args: str) -> "QueryBuilder[T]":
        """
        Adds an ORDER BY clause to the query.

        Accepts multiple field names. A '-' prefix indicates
        descending order.

        Example:
            User.order_by("-id", "name")
        """
        for field in args:
            if not field:
                continue
            desc = field.startswith("-")
            field_name = field.lstrip("-")

            if not hasattr(self._model_cls, field_name):
                raise AttributeError(
                    f"'{self._model_cls.__name__}' has no attribute '{field_name}'"
                )
            column = getattr(self._model_cls, field_name)

            if desc:
                self._statement = self._statement.order_by(column.desc())
            else:
                self._statement = self._statement.order_by(column.asc())
        return self

    def limit(self, number: int) -> "QueryBuilder[T]":
        """
        Adds a LIMIT clause to the query.
        """
        self._statement = self._statement.limit(number)
        return self

    def offset(self, number: int) -> "QueryBuilder[T]":
        """
        Adds an OFFSET clause to the query.
        """
        self._statement = self._statement.offset(number)
        return self

    def paginate(self, limit: int, offset: int = 0) -> "QueryBuilder[T]":
        """
        Convenience helper that applies both LIMIT and OFFSET in one call.
        """
        self._statement = self._statement.limit(limit).offset(offset)
        return self

    def related(
        self,
        relationship_attr,
        *,
        where=None,
        aggregate: Optional[str] = None,
        having=None,
        order_by=None,
        loader: str = "selectin",
    ) -> "QueryBuilder[T]":
        """
        Adds filters/order/eager loading based on a relationship.

        Args:
            relationship_attr: A SQLAlchemy relationship attribute (e.g., User.posts).
            where: Clause or list of clauses applied to the related entity.
            aggregate: One of {"exists", "all", "count"}.
            having: Clause or list evaluated against aggregate expressions (only for "count").
            order_by: Ordering directives (only for "count").
            eager: False, True (defaults to selectinload), "selectin", or "joined".
        """
        if self._related_used:
            raise ValueError("related() can only be invoked once per query.")

        path = self._resolve_relationship_path(relationship_attr)
        agg = (aggregate or "exists").lower()
        where_clauses = self._ensure_sequence(where)
        having_clauses = self._ensure_sequence(having)
        order_clauses = self._ensure_sequence(order_by)

        loader_choice = self._determine_loader(path, loader)
        self._apply_eager_option(path, loader_choice)

        if agg == "exists":
            if where_clauses:
                predicate = self._combine_clauses(where_clauses)
                expr = self._build_exists_expression(path, predicate)
                self._statement = self._statement.where(expr)
        elif agg == "all":
            if not where_clauses:
                raise ValueError("aggregate='all' requires at least one WHERE predicate.")
            predicate = self._combine_clauses(where_clauses)
            expr = self._build_all_expression(path, predicate)
            self._statement = self._statement.where(expr)
        elif agg == "count":
            count_expr = self._build_count_expression(path, where_clauses)
            if not having_clauses and not order_clauses:
                # If callers omit having/order, default to no-op filter but allow chaining.
                pass
            for clause in having_clauses:
                rendered = clause(count_expr) if callable(clause) else clause
                self._statement = self._statement.where(rendered)
            for clause in order_clauses:
                self._statement = self._statement.order_by(
                    self._build_order_clause(clause, count_expr)
                )
        else:
            raise ValueError("aggregate must be one of {'exists', 'all', 'count'}.")

        self._related_used = True
        return self

    def alchemize(self):
        """
        The "escape hatch".

        Transmutes the current high-level query into a raw
        SQLAlchemy Select object for advanced customization.

        Returns:
            sqlalchemy.sql.Select: The underlying query object.
        """
        return self._statement

    # --- Terminal Methods ---

    def first(self) -> Optional[T]:
        """
        Fetches the first record matched by the query.
        This is a terminal method.

        Returns:
            A model instance or None if no record is found.
        """
        return _first(self)

    def all(self) -> List[T]:
        """
        Fetches all records matched by the query.
        This is a terminal method.

        Returns:
            A list of model instances.
        """
        return _all(self)

    def one(self) -> T:
        """
        Fetches exactly one record matched by the query.
        Raises ObjectNotFoundError or MultipleObjectsFoundError as appropriate.
        """
        return _one(self)

    def count(self) -> int:
        """
        Returns the total number of records matched by the query.
        This is a terminal method.
        """
        return _count(self)

    def exists(self) -> bool:
        """
        Returns True if the query matches at least one record.
        """
        return _exists(self)

    def update(self, **values) -> None:
        """
        Performs a bulk update on the records matched by the query.
        This is a terminal method and does not return any records.
        """
        return _update(self, **values)

    def delete(self) -> None:
        """
        Performs a bulk delete on the records matched by the query.
        This is a terminal method and does not return any records.
        """
        return _delete(self)

    # --- Internal helpers ---

    def _resolve_relationship_path(self, relationship_attr) -> List:
        """Validates and returns a single-step relationship path."""
        if not hasattr(relationship_attr, "property"):
            raise TypeError("related() expects a SQLAlchemy relationship attribute.")
        prop = relationship_attr.property
        if not isinstance(prop, RelationshipProperty):
            raise TypeError("related() expects a relationship attribute, not a column.")

        parent_cls = relationship_attr.parent.class_
        if parent_cls is not self._model_cls:
            raise ValueError(
                "related() currently supports only direct relationships from the root model."
            )
        return [relationship_attr]

    def _ensure_sequence(self, value) -> List:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def _combine_clauses(self, clauses: Sequence) -> Any:
        if not clauses:
            return true()
        return and_(*clauses)

    def _build_exists_expression(self, path: List, predicate) -> Any:
        expr = predicate
        for attr in reversed(path):
            expr = attr.any(expr)
        return expr

    def _build_all_expression(self, path: List, predicate) -> Any:
        expr = predicate
        for attr in reversed(path):
            expr = ~attr.any(~expr)
        return expr

    def _build_count_expression(self, path: List, where_clauses: Sequence) -> Any:
        target_cls = path[-1].property.entity.class_
        mapper = sa_inspect(target_cls)
        target_table = mapper.selectable
        pk_cols = mapper.primary_key
        if pk_cols:
            count_target = pk_cols[0]
        else:
            count_target = next(iter(target_table.c.values()))

        stmt = select(func.count(func.distinct(count_target))).select_from(target_table)
        if where_clauses:
            stmt = stmt.where(*where_clauses)

        from_clause = target_table
        reversed_path = list(reversed(path))

        for attr in reversed_path:
            rel = attr.property
            parent_cls = rel.parent.class_
            parent_table = sa_inspect(parent_cls).selectable

            if rel.secondary is not None:
                from_clause = from_clause.join(rel.secondary, rel.secondaryjoin)

            if parent_cls is self._model_cls:
                stmt = stmt.where(rel.primaryjoin)
                stmt = stmt.correlate(parent_table)
            else:
                from_clause = from_clause.join(parent_table, rel.primaryjoin)

        stmt = stmt.select_from(from_clause)
        return stmt.scalar_subquery()

    def _build_order_clause(self, clause, aggregate_expr):
        if isinstance(clause, str):
            key = clause.lstrip("-").lower()
            if key != "count":
                raise ValueError("order_by only supports 'count' when aggregate='count'.")
            return aggregate_expr.desc() if clause.startswith("-") else aggregate_expr.asc()
        if callable(clause):
            return clause(aggregate_expr)
        return clause

    def _determine_loader(self, path: List, loader_option) -> str:
        if loader_option not in {"selectin", "joined"}:
            raise ValueError("loader must be 'selectin' or 'joined'.")
        if loader_option == "selectin" and not path[0].property.uselist:
            return "joined"
        return loader_option

    def _apply_eager_option(self, path: List, loader_type: str):
        loader = selectinload(path[0]) if loader_type == "selectin" else joinedload(path[0])
        for attr in path[1:]:
            loader = (
                loader.selectinload(attr) if loader_type == "selectin" else loader.joinedload(attr)
            )

        self._statement = self._statement.options(loader)
