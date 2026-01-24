# duo_orm/query.py

from __future__ import annotations
from dataclasses import dataclass, replace
from typing import (
    TYPE_CHECKING,
    Type,
    TypeVar,
    List,
    Optional,
    Sequence,
    Callable,
    Any,
    Tuple,
    Iterable,
)

from sqlalchemy import (
    select,
    func,
    and_,
    true,
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
except Exception:  # pragma: no cover - dialect may not be installed.
    JSONB = None  # type: ignore[misc,assignment]
    PG_ARRAY = None  # type: ignore[misc,assignment]

from .executor import _first, _all, _update, _delete, _count, _one, _exists

# This helps with type hinting for the model class itself.
T = TypeVar("T")

JSON_TYPES: Tuple[type, ...] = (SQLAlchemyJSON,)
if JSONB is not None:
    JSON_TYPES = JSON_TYPES + (JSONB,)

ARRAY_TYPES: Tuple[type, ...] = (SQLAlchemyARRAY,)
if PG_ARRAY is not None and PG_ARRAY not in ARRAY_TYPES:
    ARRAY_TYPES = ARRAY_TYPES + (PG_ARRAY,)


def _is_json_column(attr: InstrumentedAttribute) -> bool:
    column_type = getattr(attr, "type", None)
    if column_type is None:
        return False
    return isinstance(column_type, JSON_TYPES)


def _is_array_column(attr: InstrumentedAttribute) -> bool:
    column_type = getattr(attr, "type", None)
    if column_type is None:
        return False
    if isinstance(column_type, ARRAY_TYPES):
        return True
    return bool(getattr(column_type, "_is_array", False))


@dataclass(frozen=True)
class JSONExpression:
    column: InstrumentedAttribute
    path: Tuple[Any, ...] = ()
    cast_as: str | None = None

    def __post_init__(self):
        if not isinstance(self.column, InstrumentedAttribute):
            raise TypeError("json() expects an InstrumentedAttribute column.")
        if not _is_json_column(self.column):
            raise TypeError("json() can only target JSON-capable columns.")

    def __getitem__(self, key: Any) -> "JSONExpression":
        if not isinstance(key, (str, int)):
            raise TypeError("JSON paths only accept string or integer keys.")
        return replace(self, path=self.path + (key,))

    # --- Casting helpers -------------------------------------------------

    def as_text(self) -> "JSONExpression":
        return replace(self, cast_as="text")

    def as_integer(self) -> "JSONExpression":
        return replace(self, cast_as="integer")

    def as_float(self) -> "JSONExpression":
        return replace(self, cast_as="float")

    def as_boolean(self) -> "JSONExpression":
        return replace(self, cast_as="boolean")

    # --- Predicates ------------------------------------------------------

    def equals(self, value: Any) -> ClauseElement:
        if value is None:
            return self.is_null()
        left = (
            self._json_expr()
            if isinstance(value, (dict, list))
            else _cast_scalar_expr(self, value)
        )
        return left == value

    def not_equals(self, value: Any) -> ClauseElement:
        if value is None:
            return self.is_not_null()
        left = (
            self._json_expr()
            if isinstance(value, (dict, list))
            else _cast_scalar_expr(self, value)
        )
        return left != value

    def is_null(self) -> ClauseElement:
        return self._json_expr().is_(None)

    def is_not_null(self) -> ClauseElement:
        return self._json_expr().is_not(None)

    def is_true(self) -> ClauseElement:
        return self.as_boolean()._scalar_expr().is_(True)

    def is_false(self) -> ClauseElement:
        return self.as_boolean()._scalar_expr().is_(False)

    def contains(self, fragment: Any) -> ClauseElement:
        return self._json_expr().contains(fragment)

    def has_key(self, key: Any) -> ClauseElement:
        expr = self._json_expr()
        if not hasattr(expr, "has_key"):
            raise TypeError("The current dialect does not expose JSON has_key().")
        return expr.has_key(key)  # type: ignore[attr-defined]

    # Convenience to surface raw SQLAlchemy expression when needed.
    def expression(self, *, as_text: bool = False) -> ClauseElement:
        return self._scalar_expr() if as_text or self.cast_as else self._json_expr()

    # Rich comparisons to keep syntax pythonic.
    def __eq__(self, other: Any) -> ClauseElement:  # type: ignore[override]
        return self.equals(other)

    def __ne__(self, other: Any) -> ClauseElement:  # type: ignore[override]
        return self.not_equals(other)

    # --- Internals -------------------------------------------------------

    def _json_expr(self) -> ColumnOperators:
        expr: ColumnOperators = self.column
        for key in self.path:
            expr = expr[key]  # type: ignore[index]
        return expr

    def _scalar_expr(self) -> ClauseElement:
        expr = self._json_expr()
        match self.cast_as:
            case "integer":
                return cast(self._as_text(expr), Integer)
            case "float":
                return cast(self._as_text(expr), Float)
            case "boolean":
                return cast(self._as_text(expr), Boolean)
            case "text" | None:
                return self._as_text(expr)
            case _:
                return self._as_text(expr)

    def _as_text(self, expr: ColumnOperators) -> ClauseElement:
        text_expr = getattr(expr, "astext", None)
        if text_expr is not None:
            return text_expr
        return cast(expr, Text)


def json(column: InstrumentedAttribute) -> JSONExpression:
    """
    Entry point for building JSON-aware predicates inside QueryBuilder.where.
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
    column: InstrumentedAttribute

    def __post_init__(self):
        if not isinstance(self.column, InstrumentedAttribute):
            raise TypeError("array() expects an InstrumentedAttribute column.")
        if not _is_array_column(self.column):
            raise TypeError("array() can only target ARRAY-capable columns.")

    def includes(self, value: Any) -> ClauseElement:
        expr = self._array_expr()
        contains_member = getattr(expr, "any", None)
        if contains_member is None:
            raise TypeError("The current dialect does not support array membership checks.")
        return contains_member(value)

    def includes_all(self, values: Iterable[Any]) -> ClauseElement:
        prepared = self._prepare_values(values)
        comparator_contains = getattr(self._array_expr().comparator, "contains", None)
        if comparator_contains:
            return comparator_contains(prepared)
        return self._array_expr().contains(prepared)

    def includes_any(self, values: Iterable[Any]) -> ClauseElement:
        prepared = self._prepare_values(values)
        overlap = getattr(self._array_expr(), "overlap", None)
        if overlap is None:
            raise TypeError("The current dialect does not support array overlap checks.")
        return overlap(prepared)

    def equals(self, values: Iterable[Any]) -> ClauseElement:
        return self._array_expr() == list(values)

    def not_equals(self, values: Iterable[Any]) -> ClauseElement:
        return self._array_expr() != list(values)

    def length(self) -> ClauseElement:
        expr = self._array_expr()
        if hasattr(func, "cardinality"):
            return func.cardinality(expr)
        # Fallback: array_length(expr, 1) counts elements in the first dimension.
        return func.array_length(expr, 1)

    def expression(self) -> ColumnOperators:
        return self._array_expr()

    def _array_expr(self) -> ColumnOperators:
        return self.column

    def _prepare_values(self, values: Iterable[Any]) -> List[Any]:
        if values is None:
            raise ValueError("Array helpers require at least one value.")
        if isinstance(values, (list, tuple)):
            seq = list(values)
        else:
            seq = list(values)
        if not seq:
            raise ValueError("Array helpers require at least one value.")
        return seq


def array(column: InstrumentedAttribute) -> ArrayExpression:
    """
    Entry point for building ARRAY-aware predicates inside QueryBuilder.where.
    """
    return ArrayExpression(column)

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

        Note:
            `related()` currently only supports direct (single-hop) relationships off the root model.
            Multi-level paths (e.g., `User.posts.comments`) must be expressed via SQLAlchemy directly or
            broken into multiple queries.
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
            self._apply_exists(path, where_clauses)
        elif agg == "all":
            self._apply_all(path, where_clauses)
        elif agg == "count":
            self._apply_count(path, where_clauses, having_clauses, order_clauses)
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

    def _apply_exists(self, path: List, where_clauses: Sequence) -> None:
        """
        aggregate="exists" uses SQLAlchemy's .any() to test whether at least one related row matches.
        """
        if not where_clauses:
            return
        predicate = self._combine_clauses(where_clauses)
        expr = self._build_exists_expression(path, predicate)
        self._statement = self._statement.where(expr)

    def _apply_all(self, path: List, where_clauses: Sequence) -> None:
        """
        aggregate="all" uses the double-negative trick: ALL(pred) == NOT EXISTS(not pred).
        """
        if not where_clauses:
            raise ValueError("aggregate='all' requires at least one WHERE predicate.")
        predicate = self._combine_clauses(where_clauses)
        expr = self._build_all_expression(path, predicate)
        self._statement = self._statement.where(expr)

    def _apply_count(
        self,
        path: List,
        where_clauses: Sequence,
        having_clauses: Sequence,
        order_clauses: Sequence,
    ) -> None:
        """
        aggregate="count" builds a correlated subquery counting related rows, then allows HAVING/ORDER BY on it.
        """
        count_expr = self._build_count_expression(path, where_clauses)
        for clause in having_clauses:
            rendered = clause(count_expr) if callable(clause) else clause
            self._statement = self._statement.where(rendered)
        for clause in order_clauses:
            self._statement = self._statement.order_by(
                self._build_order_clause(clause, count_expr)
            )

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
        """
        Build a correlated COUNT(*) subquery tied back to the parent entity.

        Steps:
            1. Start from the related entity's selectable, applying any WHERE clauses.
            2. Walk the relationship path backwards to join secondary tables / parent tables.
            3. Use correlate(parent_table) so SQLAlchemy links the inner COUNT to the outer statement.
        """
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
