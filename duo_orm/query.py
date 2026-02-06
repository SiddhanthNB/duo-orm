# duo_orm/query.py

from __future__ import annotations
from dataclasses import dataclass, replace
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
)

from sqlalchemy import (
    select,
    func,
    and_,
    inspect as sa_inspect,
    Boolean,
    Float,
    Integer,
    Text,
    cast,
    ARRAY as SQLAlchemyARRAY,
)
from sqlalchemy.orm import RelationshipProperty, joinedload, selectinload
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.operators import ColumnOperators
from sqlalchemy.sql.elements import ClauseElement
from sqlalchemy.types import JSON as SQLAlchemyJSON

try:  # Optional dependency – present on Postgres dialects.
    from sqlalchemy.dialects.postgresql import JSONB, ARRAY as PG_ARRAY
except ImportError:  # pragma: no cover
    JSONB = None  # type: ignore[misc,assignment]
    PG_ARRAY = None  # type: ignore[misc,assignment]

from .executor import _all, _count, _delete_bulk, _exists, _first, _one, _update_bulk
from .exceptions import InvalidQueryError
from .session import active_session_var, is_async_context

if TYPE_CHECKING:
    from .db import Database

# This helps with type hinting for the model class itself.
T = TypeVar("T")

# Maximum relationship depth allowed in a path to avoid runaway eager chains.
_MAX_RELATED_DEPTH = 3


@dataclass(frozen=True)
class RelationshipPath:
    """
    Typed representation of a relationship traversal for `related()`.

    Attributes:
        hops: Tuple of InstrumentedAttribute describing the path.
        loader_override: Optional loader hint for this path.
    """

    hops: Tuple[InstrumentedAttribute, ...]
    loader_override: Optional[str] = None


def path(*relationships: InstrumentedAttribute, loader: Optional[str] = None) -> RelationshipPath:
    """
    Build a typed multi-hop relationship path for `related()`.

    Example:
        path(User.posts, Post.comments, loader="selectin")

    Args:
        *relationships: One or more relationship attributes forming the traversal.
        loader: Optional loader hint ("selectin" or "joined") applied to this path.
    """
    if not relationships:
        raise ValueError("path() requires at least one relationship attribute.")
    for rel in relationships:
        if not hasattr(rel, "property") or not isinstance(rel.property, RelationshipProperty):
            raise TypeError("path() accepts only SQLAlchemy relationship attributes.")
    if loader not in {None, "selectin", "joined"}:
        raise ValueError("loader must be None, 'selectin', or 'joined'.")
    return RelationshipPath(tuple(relationships), loader)

JSON_TYPES: Tuple[type, ...] = (SQLAlchemyJSON,)
if JSONB is not None:
    JSON_TYPES = JSON_TYPES + (JSONB,)

ARRAY_TYPES: Tuple[type, ...] = (SQLAlchemyARRAY,)
if PG_ARRAY is not None and PG_ARRAY not in ARRAY_TYPES:
    ARRAY_TYPES = ARRAY_TYPES + (PG_ARRAY,)


def _is_json_column(attr: InstrumentedAttribute) -> bool:
    column_type = getattr(attr, "type", None)
    return isinstance(column_type, JSON_TYPES) if column_type is not None else False


def _is_array_column(attr: InstrumentedAttribute) -> bool:
    column_type = getattr(attr, "type", None)
    if column_type is None:
        return False
    if isinstance(column_type, ARRAY_TYPES):
        return True
    return bool(getattr(column_type, "_is_array", False))


@dataclass(frozen=True)
class JSONExpression:
    """
    A helper object for building JSON-aware query expressions.

    Instances of this class are created by the `json()` helper function.
    It provides a fluent, Pythonic interface for creating SQLAlchemy clauses
    that operate on `JSON` or `JSONB` columns.
    """
    column: InstrumentedAttribute
    path: Tuple[Any, ...] = ()
    cast_as: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.column, InstrumentedAttribute):
            raise TypeError("json() expects a SQLAlchemy model attribute.")
        if not _is_json_column(self.column):
            raise TypeError("json() can only be used on JSON-supported column types.")

    def __getitem__(self, key: Any) -> "JSONExpression":
        """Navigates to a nested key or index within the JSON object."""
        if not isinstance(key, (str, int)):
            raise TypeError("JSON path keys must be strings or integers.")
        return replace(self, path=self.path + (key,))

    def as_text(self) -> "JSONExpression":
        """Casts the JSON value to text for comparison."""
        return replace(self, cast_as="text")

    def as_integer(self) -> "JSONExpression":
        """Casts the JSON value to an integer for comparison."""
        return replace(self, cast_as="integer")

    def as_float(self) -> "JSONExpression":
        """Casts the JSON value to a float for comparison."""
        return replace(self, cast_as="float")

    def as_boolean(self) -> "JSONExpression":
        """Casts the JSON value to a boolean for comparison."""
        return replace(self, cast_as="boolean")

    def equals(self, value: Any) -> ClauseElement:
        """Creates an equality comparison clause (`==`)."""
        if value is None:
            return self.is_null()
        left = self._json_expr() if isinstance(value, (dict, list)) else _cast_scalar_expr(self, value)
        return left == value

    def not_equals(self, value: Any) -> ClauseElement:
        """Creates an inequality comparison clause (`!=`)."""
        if value is None:
            return self.is_not_null()
        left = self._json_expr() if isinstance(value, (dict, list)) else _cast_scalar_expr(self, value)
        return left != value

    def is_null(self) -> ClauseElement:
        """Creates a clause to check if the JSON value is null."""
        return self._json_expr().is_(None)

    def is_not_null(self) -> ClauseElement:
        """Creates a clause to check if the JSON value is not null."""
        return self._json_expr().is_not(None)

    def is_true(self) -> ClauseElement:
        """Creates a clause to check if the JSON value is the boolean `true`."""
        return self.as_boolean()._scalar_expr().is_(True)

    def is_false(self) -> ClauseElement:
        """Creates a clause to check if the JSON value is the boolean `false`."""
        return self.as_boolean()._scalar_expr().is_(False)

    def contains(self, fragment: Any) -> ClauseElement:
        """Creates a clause to check if the JSON value contains the given fragment."""
        return self._json_expr().contains(fragment)

    def has_key(self, key: Any) -> ClauseElement:
        """Creates a clause to check if the JSON object has a specific key."""
        expr = self._json_expr()
        if not hasattr(expr, "has_key"):
            raise TypeError("The current dialect does not expose a JSON `has_key` operator.")
        return expr.has_key(key)  # type: ignore[attr-defined]

    def expression(self, *, as_text: bool = False) -> ClauseElement:
        """
        Returns the raw underlying SQLAlchemy expression.

        Args:
            as_text: When True, coerce the expression to text even if no cast is set.
        """
        if as_text:
            return self._as_text(self._json_expr())
        return self._scalar_expr() if self.cast_as else self._json_expr()

    def __eq__(self, other: Any) -> ClauseElement:
        return self.equals(other)

    def __ne__(self, other: Any) -> ClauseElement:
        return self.not_equals(other)

    def _json_expr(self) -> ColumnOperators:
        """Builds the SQLAlchemy JSON path expression."""
        expr: ColumnOperators = self.column
        for key in self.path:
            expr = expr[key]  # type: ignore[index]
        return expr

    def _scalar_expr(self) -> ClauseElement:
        """Builds a scalar version of the expression, with optional casting."""
        expr = self._json_expr()
        caster = {
            "integer": Integer,
            "float": Float,
            "boolean": Boolean,
        }.get(self.cast_as or "")
        return cast(self._as_text(expr), caster) if caster else self._as_text(expr)

    @staticmethod
    def _as_text(expr: ColumnOperators) -> ClauseElement:
        """Coerces a JSON expression to text for scalar operations."""
        text_expr = getattr(expr, "astext", None)
        return text_expr if text_expr is not None else cast(expr, Text)


def json(column: InstrumentedAttribute) -> JSONExpression:
    """
    Entry point for building JSON-aware query expressions.

    Wraps a model's JSON column attribute to provide a fluent API for
    path navigation and comparison operators.

    Args:
        column: The SQLAlchemy model attribute representing a JSON column.

    Returns:
        A `JSONExpression` object to build the query clause.
    """
    return JSONExpression(column)


def _cast_scalar_expr(expr: JSONExpression, value: Any) -> ClauseElement:
    """Choose an appropriate cast for scalar comparisons based on the Python value."""
    if isinstance(value, bool):
        return expr.as_boolean()._scalar_expr()
    if isinstance(value, int):
        return expr.as_integer()._scalar_expr()
    if isinstance(value, float):
        return expr.as_float()._scalar_expr()
    return expr._scalar_expr()


@dataclass(frozen=True)
class ArrayExpression:
    """

    A helper object for building ARRAY-aware query expressions.

    Instances of this class are created by the `array()` helper function.
    It provides a fluent, Pythonic interface for creating SQLAlchemy clauses
    that operate on `ARRAY` columns.
    """
    column: InstrumentedAttribute

    def __post_init__(self):
        if not isinstance(self.column, InstrumentedAttribute):
            raise TypeError("array() expects a SQLAlchemy model attribute.")
        if not _is_array_column(self.column):
            raise TypeError("array() can only be used on ARRAY-supported column types.")

    def includes(self, value: Any) -> ClauseElement:
        """Creates a clause to check if the array contains a single value."""
        expr = self._array_expr()
        if not hasattr(expr, "any"):
            raise TypeError("The current dialect does not support array `any()` checks.")
        return expr.any(value)  # type: ignore[attr-defined]

    def includes_all(self, values: Iterable[Any]) -> ClauseElement:
        """Creates a clause to check if the array contains all of the given values."""
        prepared = self._prepare_values(values)
        if not prepared:
            raise ValueError("includes_all() requires at least one value.")
        comparator = getattr(self._array_expr().comparator, "contains", None)
        return comparator(prepared) if comparator else self._array_expr().contains(prepared)

    def includes_any(self, values: Iterable[Any]) -> ClauseElement:
        """Creates a clause to check if the array contains any of the given values (overlap)."""
        prepared = self._prepare_values(values)
        if not hasattr(self._array_expr(), "overlap"):
            raise TypeError("The current dialect does not support array `overlap` checks.")
        return self._array_expr().overlap(prepared)  # type: ignore[attr-defined]

    def equals(self, values: Iterable[Any]) -> ClauseElement:
        """Creates a clause to check for exact array equality."""
        return self._array_expr() == self._prepare_values(values)

    def not_equals(self, values: Iterable[Any]) -> ClauseElement:
        """Creates a clause to check for array inequality."""
        return self._array_expr() != self._prepare_values(values)

    def length(self) -> ClauseElement:
        """Returns an expression representing the length of the array."""
        expr = self._array_expr()
        return func.cardinality(expr) if hasattr(func, "cardinality") else func.array_length(expr, 1)

    def expression(self) -> ColumnOperators:
        """Returns the raw underlying SQLAlchemy expression."""
        return self._array_expr()

    def _array_expr(self) -> ColumnOperators:
        return self.column

    @staticmethod
    def _prepare_values(values: Iterable[Any]) -> List[Any]:
        if values is None:
            raise ValueError("Array helpers require a non-null iterable of values.")
        return list(values)


def array(column: InstrumentedAttribute) -> ArrayExpression:
    """
    Entry point for building ARRAY-aware query expressions.

    Wraps a model's ARRAY column attribute to provide a fluent API for
    membership and comparison operators.

    Args:
        column: The SQLAlchemy model attribute representing an ARRAY column.

    Returns:
        An `ArrayExpression` object to build the query clause.
    """
    return ArrayExpression(column)


class QueryBuilder:
    """
    A chainable, fluent query builder.

    This class is the core of the ORM's query-building API. It constructs
    a SQLAlchemy statement internally and provides terminal methods
    (like `.first()`, `.all()`) to execute it.

    Instances of this class are created by calling class-level methods on a
    DuoORM model (e.g., `User.where(...)`).
    """

    def __init__(self, model_cls: Type[T], db: "Database") -> None:
        if not db:
            raise RuntimeError("QueryBuilder must be initialized with a Database instance.")
        self._model_cls = model_cls
        self.db = db
        self._statement = select(self._model_cls)
        # Track related paths added to this query to deduplicate and detect conflicts.
        self._related_paths: dict[Tuple[InstrumentedAttribute, ...], dict[str, Any]] = {}

    def where(self, *args: ClauseElement) -> "QueryBuilder[T]":
        """
        Adds one or more WHERE clauses to the query, joined by `AND`.

        Args:
            *args: SQLAlchemy column expressions (e.g., `User.age > 18`).

        Returns:
            The `QueryBuilder` instance for further chaining.
        """
        self._statement = self._statement.where(*args)
        return self

    def order_by(self, *args: str) -> "QueryBuilder[T]":
        """
        Adds an ORDER BY clause to the query.

        Args:
            *args: Field names to order by. Prefix a name with `-` for
                descending order (e.g., `"-id"`).

        Returns:
            The `QueryBuilder` instance for further chaining.
        """
        for field in args:
            if not isinstance(field, str) or not field:
                raise InvalidQueryError("order_by() expects non-empty string arguments.")
            desc = field.startswith("-")
            field_name = field.lstrip("-")

            if not hasattr(self._model_cls, field_name):
                raise AttributeError(f"'{self._model_cls.__name__}' has no attribute '{field_name}'")
            column = getattr(self._model_cls, field_name)
            self._statement = self._statement.order_by(column.desc() if desc else column.asc())
        return self

    def limit(self, number: int) -> "QueryBuilder[T]":
        """Adds a LIMIT clause to the query."""
        self._statement = self._statement.limit(number)
        return self

    def offset(self, number: int) -> "QueryBuilder[T]":
        """Adds an OFFSET clause to the query."""
        self._statement = self._statement.offset(number)
        return self

    def paginate(self, limit: int, offset: int = 0) -> "QueryBuilder[T]":
        """
        Applies LIMIT and OFFSET clauses for pagination.

        Args:
            limit: The number of records to return per page.
            offset: The number of records to skip. Defaults to 0.

        Returns:
            The `QueryBuilder` instance for further chaining.
        """
        self._statement = self._statement.limit(limit).offset(offset)
        return self

    def related(
        self,
        relationship_attr: InstrumentedAttribute | RelationshipPath,
        *,
        where: Optional[Sequence[ClauseElement]] = None,
        aggregate: Optional[str] = None,
        having: Optional[Sequence[Callable[[Any], ClauseElement]]] = None,
        order_by: Optional[Sequence[str]] = None,
        loader: Optional[str] = None,
    ) -> "QueryBuilder[T]":
        """
        Configures eager loading and/or filtering based on a relationship.
        One path per call; chain multiple `related()` calls for siblings.

        This is the primary tool for solving N+1 query problems and for
        filtering a model based on its related data.

        Args:
            relationship_attr: The relationship attribute on the model (e.g., `User.posts`)
                or a `path()` object for multi-hop relationships.
            where: A list of filter clauses to apply to the related model.
            aggregate: The aggregation mode. Can be "exists" (default), "all", or "count".
            having: A list of filter clauses to apply to the result of a "count" aggregate.
            order_by: A list of ordering clauses for a "count" aggregate.
            loader: Optional eager loading strategy override for this path.
                When omitted, heuristics pick joined for scalar hops and selectin for collections.

        Returns:
            The `QueryBuilder` instance for further chaining.
        """
        hops, loader_override = self._normalize_path(relationship_attr, loader)
        agg = (aggregate or "exists").lower()
        where_clauses, having_clauses, order_clauses = map(
            self._ensure_sequence, (where, having, order_by)
        )

        path_key = tuple(hops)
        existing = self._related_paths.get(path_key)
        if existing:
            # Reject conflicts on loader/aggregate/settings.
            if (existing["aggregate"], existing["loader_override"]) != (agg, loader_override):
                raise InvalidQueryError("Conflicting related() configuration for the same path.")
            # Merge where/having/order_by if provided anew.
            if where_clauses:
                existing["where"].extend(where_clauses)
            if having_clauses:
                existing["having"].extend(having_clauses)
            if order_clauses:
                existing["order"].extend(order_clauses)
            return self

        loader_choice = self._determine_loader(hops, loader_override)
        self._apply_eager_option(hops, loader_choice)

        self._related_paths[path_key] = {
            "aggregate": agg,
            "where": list(where_clauses),
            "having": list(having_clauses),
            "order": list(order_clauses),
            "loader_override": loader_override,
        }

        if agg == "exists":
            self._apply_exists(hops, where_clauses)
        elif agg == "all":
            self._apply_all(hops, where_clauses)
        elif agg == "count":
            self._apply_count(hops, where_clauses, having_clauses, order_clauses)
        else:
            raise ValueError(f"Invalid aggregate option '{agg}'. Must be 'exists', 'all', or 'count'.")
        return self

    def alchemize(self) -> select:
        """
        Returns the underlying SQLAlchemy `Select` object.

        This "escape hatch" allows for advanced customization of the query
        using the full power of SQLAlchemy Core.

        Returns:
            A SQLAlchemy `select` construct.
        """
        return self._statement

    # --- Terminal Methods ---

    def first(self) -> Optional[T] | Awaitable[Optional[T]]:
        """
        Executes the query and returns the first matching record or `None`.
        """
        return _first(self)

    def all(self) -> List[T] | Awaitable[List[T]]:
        """
        Executes the query and returns a list of all matching records.
        """
        return _all(self)

    def one(self) -> T | Awaitable[T]:
        """
        Executes the query and returns exactly one record.

        Raises:
            ObjectNotFoundError: If no records are found.
            MultipleObjectsFoundError: If more than one record is found.
        """
        return _one(self)

    def count(self) -> int | Awaitable[int]:
        """Executes the query and returns the total number of matching records."""
        return _count(self)

    def exists(self) -> bool | Awaitable[bool]:
        """Executes the query and returns `True` if at least one record exists."""
        return _exists(self)

    def update(self, **values) -> None | Awaitable[None]:
        raise InvalidQueryError("update() has been renamed to update_bulk(). Use update_bulk instead.")

    def update_bulk(
        self,
        values: dict[str, Any],
        *,
        with_hooks: bool = False,
        batch_size: int = 200,
        require_filter: bool = True,
    ) -> None | Awaitable[None]:
        """
        Performs a bulk update on all records matched by the query.

        Args:
            values: mapping of columns to new values.
            with_hooks: when True, loads instances and runs per-row validation/hooks.
            batch_size: batch size for the hooked path.
            require_filter: guard against accidental full-table updates.
        """
        return _update_bulk(
            self,
            values,
            with_hooks=with_hooks,
            batch_size=batch_size,
            require_filter=require_filter,
        )

    def delete(self) -> None | Awaitable[None]:
        raise InvalidQueryError("delete() has been renamed to delete_bulk(). Use delete_bulk instead.")

    def delete_bulk(
        self,
        *,
        with_hooks: bool = False,
        batch_size: int = 200,
        require_filter: bool = True,
    ) -> None | Awaitable[None]:
        """
        Performs a bulk delete on all records matched by the query.

        Args:
            with_hooks: when True, loads instances and runs per-row delete hooks.
            batch_size: batch size for the hooked path.
            require_filter: guard against accidental full-table deletes.
        """
        return _delete_bulk(
            self,
            with_hooks=with_hooks,
            batch_size=batch_size,
            require_filter=require_filter,
        )

    def find_in_batches(self, *args, **kwargs):
        raise InvalidQueryError("find_in_batches() has been replaced by iterate(batch=True).")

    def find_each(self, *args, **kwargs):
        raise InvalidQueryError("find_each() has been replaced by iterate().")

    # --- Internal helpers ---

    def _resolve_relationship_path(self, attr: Any) -> List[InstrumentedAttribute]:
        if not hasattr(attr, "property") or not isinstance(attr.property, RelationshipProperty):
            raise TypeError("related() expects a SQLAlchemy relationship attribute.")
        if attr.parent.class_ is not self._model_cls:
            raise InvalidQueryError("related() only supports direct relationships from the root model.")
        return [attr]

    @staticmethod
    def _ensure_sequence(value: Any) -> List[Any]:
        if value is None:
            return []
        return list(value) if isinstance(value, (list, tuple)) else [value]

    def _normalize_path(
        self, rel_or_path: InstrumentedAttribute | RelationshipPath, loader_opt: Optional[str]
    ) -> Tuple[List[InstrumentedAttribute], Optional[str]]:
        if isinstance(rel_or_path, RelationshipPath):
            hops = list(rel_or_path.hops)
            loader_override = rel_or_path.loader_override if loader_opt is None else loader_opt
        else:
            hops = self._resolve_relationship_path(rel_or_path)
            loader_override = loader_opt

        if len(hops) > _MAX_RELATED_DEPTH:
            raise InvalidQueryError(f"related() paths may not exceed depth {_MAX_RELATED_DEPTH}.")

        if loader_override not in {None, "selectin", "joined"}:
            raise ValueError("loader must be None, 'selectin', or 'joined'.")

        # Validate hop chain
        if hops[0].parent.class_ is not self._model_cls:
            raise InvalidQueryError("related() paths must start from the root model.")
        for idx in range(1, len(hops)):
            prev = hops[idx - 1].property.entity.class_
            curr_parent = hops[idx].parent.class_
            if prev is not curr_parent:
                raise InvalidQueryError("Each hop in path() must follow from the previous relationship.")

        return hops, loader_override

    @staticmethod
    def _build_order_clause(clause: Any, agg_expr: Any) -> Any:
        if isinstance(clause, str):
            key = clause.lstrip("-").lower()
            if key != "count":
                raise ValueError("When using aggregate='count', order_by only supports 'count' or '-count'.")
            return agg_expr.desc() if clause.startswith("-") else agg_expr.asc()
        return clause(agg_expr) if callable(clause) else clause

    def iterate(
        self,
        *,
        batch_size: int = 200,
        batch: bool = False,
    ):
        """
        Streams results using batched queries. When `batch=False` (default), yields
        one model at a time. When `batch=True`, yields lists of models.

        If no explicit ORDER BY is present on the query, primary key ordering is applied
        for deterministic paging.
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")

        mapper = sa_inspect(self._model_cls)
        pk_cols = list(mapper.primary_key)
        if not pk_cols:
            raise InvalidQueryError(f"{self._model_cls.__name__} has no primary key.")

        base_stmt = self._statement
        orig_limit_clause = getattr(base_stmt, "_limit_clause", None)
        orig_offset_clause = getattr(base_stmt, "_offset_clause", None)
        orig_limit_value = orig_limit_clause if orig_limit_clause is not None else None
        orig_offset_value = orig_offset_clause if orig_offset_clause is not None else None
        walked = 0
        has_order = bool(getattr(base_stmt, "_order_by_clauses", None))
        if not has_order:
            base_stmt = base_stmt.order_by(*[col.asc() for col in pk_cols])

        active_session = active_session_var.get(None)
        db = self.db

        def _sync_iter():
            nonlocal walked
            # If the original query already has LIMIT/OFFSET, fetch once respecting that slice.
            if orig_limit_clause is not None or orig_offset_clause is not None:
                if active_session is not None:
                    session = active_session
                    result = session.execute(base_stmt)
                    rows = result.unique().scalars().all()
                else:
                    with db.sync_session_factory() as session:
                        result = session.execute(base_stmt)
                        rows = result.unique().scalars().all()
                if batch:
                    if rows:
                        yield rows
                else:
                    for row in rows:
                        yield row
                return

            offset = 0
            while True:
                effective_offset = offset
                remaining = None
                current_limit = batch_size if remaining is None else min(batch_size, remaining)
                if active_session is not None:
                    session = active_session
                    result = session.execute(base_stmt.limit(current_limit).offset(effective_offset))
                    rows = result.unique().scalars().all()
                else:
                    with db.sync_session_factory() as session:
                        result = session.execute(base_stmt.limit(current_limit).offset(effective_offset))
                        rows = result.unique().scalars().all()
                if not rows:
                    break
                if batch:
                    yield rows
                else:
                    for row in rows:
                        yield row
                walked += len(rows)
                if len(rows) < current_limit:
                    break
                offset += batch_size

        async def _async_iter():
            nonlocal walked
            if orig_limit_clause is not None or orig_offset_clause is not None:
                if active_session is not None:
                    session = active_session
                    result = await session.execute(base_stmt)
                    rows = result.unique().scalars().all()
                else:
                    async with db.async_session_factory() as session:
                        result = await session.execute(base_stmt)
                        rows = result.unique().scalars().all()
                if batch:
                    if rows:
                        yield rows
                else:
                    for row in rows:
                        yield row
                return

            offset = 0
            while True:
                effective_offset = offset
                remaining = None
                current_limit = batch_size if remaining is None else min(batch_size, remaining)
                if active_session is not None:
                    session = active_session
                    result = await session.execute(base_stmt.limit(current_limit).offset(effective_offset))
                    rows = result.unique().scalars().all()
                else:
                    async with db.async_session_factory() as session:
                        result = await session.execute(base_stmt.limit(current_limit).offset(effective_offset))
                        rows = result.unique().scalars().all()
                if not rows:
                    break
                if batch:
                    yield rows
                else:
                    for row in rows:
                        yield row
                walked += len(rows)
                if len(rows) < current_limit:
                    break
                offset += batch_size

        return _async_iter() if is_async_context() else _sync_iter()

    def _determine_loader(self, path: List[InstrumentedAttribute], loader_opt: Optional[str]) -> Optional[str]:
        if loader_opt not in {None, "selectin", "joined"}:
            raise ValueError("loader must be None, 'selectin', or 'joined'.")
        # Explicit joined on deep collections can explode row counts; block unless single hop or scalar.
        if loader_opt == "joined" and any(hop.property.uselist for hop in path) and len(path) > 1:
            raise InvalidQueryError("joined loader on multi-hop collection paths is not allowed by default.")
        if loader_opt == "selectin" and not path[0].property.uselist:
            return "joined"
        # Preserve None to allow per-hop heuristics in _apply_eager_option
        return loader_opt

    def _apply_eager_option(self, path: List[InstrumentedAttribute], loader_type: str):
        """
        Build a chained loader option per hop. Loader heuristics may be overridden
        at the path level via loader_type.
        """

        def _loader_for_hop(hop: InstrumentedAttribute) -> Callable:
            choice = loader_type if loader_type else ("joined" if not hop.property.uselist else "selectin")
            return selectinload if choice == "selectin" else joinedload

        option = None
        for hop in path:
            loader_fn = _loader_for_hop(hop)
            option = loader_fn(hop) if option is None else option.selectinload(hop) if loader_fn is selectinload else option.joinedload(hop)
        if option is not None:
            self._statement = self._statement.options(option)

    def _apply_exists(self, path: List[InstrumentedAttribute], wheres: List[ClauseElement]):
        if not wheres:
            return
        predicate = self._build_relationship_predicate(path, and_(*wheres))
        self._statement = self._statement.where(predicate)

    def _apply_all(self, path: List[InstrumentedAttribute], wheres: List[ClauseElement]):
        if not wheres:
            raise ValueError("aggregate='all' requires at least one WHERE clause.")
        failing = self._build_relationship_predicate(path, ~and_(*wheres))
        self._statement = self._statement.where(~failing)

    def _apply_count(
        self,
        path: List[InstrumentedAttribute],
        wheres: List[ClauseElement],
        havings: List[Callable],
        orders: List[Any],
    ):
        count_expr = self._build_count_expression(path, wheres)

        for clause in havings:
            self._statement = self._statement.where(clause(count_expr))
        for clause in orders:
            self._statement = self._statement.order_by(self._build_order_clause(clause, count_expr))

    def _build_relationship_predicate(self, path: List[InstrumentedAttribute], terminal_clause: ClauseElement) -> ClauseElement:
        """
        Recursively build an any()/has() predicate that targets the terminal hop.
        """
        if not path:
            raise ValueError("Path cannot be empty.")
        current = path[0]
        remaining = path[1:]
        if not remaining:
            if current.property.uselist:
                return current.any(terminal_clause)
            return current.has(terminal_clause)
        inner = self._build_relationship_predicate(remaining, terminal_clause)
        if current.property.uselist:
            return current.any(inner)
        return current.has(inner)

    def _build_count_expression(self, path: List[InstrumentedAttribute], wheres: List[ClauseElement]):
        """
        Build a correlated COUNT subquery over the terminal entity of the path.
        """
        root_table = sa_inspect(self._model_cls).local_table

        # Work with base tables (no aliases) to build a correlated subquery.
        target_table = path[-1].property.entity.class_.__table__
        from_clause = target_table
        joins: List[Tuple[Any, ClauseElement]] = []

        # Traverse path backwards to accumulate join targets/conditions.
        current_table = target_table
        for rel in reversed(path):
            parent_table = rel.parent.class_.__table__
            join_cond = rel.property.primaryjoin
            joins.append((parent_table, join_cond))
            current_table = parent_table

        # The first join in the reversed traversal connects to the root table.
        # Build the select with explicit joins.
        count_stmt = select(func.count()).select_from(from_clause)
        for table, cond in joins[:-1]:  # skip the last because it's the root table; handle correlation separately
            count_stmt = count_stmt.join(table, cond)

        # Correlate to the root by applying the final join condition against the outer table.
        root_join_cond = joins[-1][1]
        count_stmt = count_stmt.where(root_join_cond)

        if wheres:
            count_stmt = count_stmt.where(and_(*wheres))

        count_stmt = count_stmt.correlate(self._model_cls)
        return count_stmt.scalar_subquery()
