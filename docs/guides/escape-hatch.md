# User Guide: The Escape Hatch

Some senior engineers worry that an ORM wrapper will get them 80% of the way and then block them when they need real power. DuoORM is designed with that concern in mind.

## The 80/20 philosophy

DuoORM aims to make the common path frictionless: CRUD, filters, ordering, pagination, eager loading, and bulk updates/deletes with guards and hooks. That covers the bulk (≈80%) of day‑to‑day data work with minimal boilerplate and a consistent sync/async API.

## The “glass ceiling” problem

Many wrappers crumble when you need window functions, recursive CTEs, vendor hints, or finely tuned aggregations. Hitting that ceiling shouldn’t force a rewrite or a separate query layer.

## The solution: `.alchemize()`

Every DuoORM query can “eject” to raw SQLAlchemy 2.0 by calling `.alchemize()`. It returns the underlying `sqlalchemy.sql.Select` object immediately—no adapters, no translation layer. From there you use standard SQLAlchemy methods and expressions.

## Interoperability workflow

1. Start with DuoORM for readability and model-aware convenience.
2. Call `.alchemize()` to get the SQLAlchemy `Select`.
3. Keep extending with any SQLAlchemy feature (CTEs, window functions, vendor-specific constructs).
4. Execute using the same DuoORM sessions (`db.transaction()`, `standalone_session()`, etc.).

## Example: start in DuoORM, finish in SQLAlchemy

```python
from duo_orm import func
from db.database import db
from db.models import Order

# DuoORM side: readable filters and ordering
qb = (
    Order.where(Order.status == "completed")
         .order_by("-created_at")
         .limit(100)
)

# Escape hatch: raw SQLAlchemy Select
stmt = qb.alchemize()

# Add advanced SQLAlchemy-only bits
stmt = (
    stmt.group_by(Order.customer_id)
        .having(func.sum(Order.total_amount) > 10_000)
        .with_hint(Order.__table__, "INDEX(order_customer_idx)", dialect_name="mysql")
)

# Execute with full SQLAlchemy control (standalone session)
async with db.standalone_session() as session:
    async with session.begin():
        result = await session.execute(stmt)
        top_customers = result.scalars().all()

# Sync variant:
# with db.sync_standalone_session() as session:
#     with session.begin():
#         result = session.execute(stmt)
#         top_customers = result.scalars().all()

```

Choose your session:

```python
# Managed (reuse DuoORM transaction/session)
async with db.transaction() as session:
    result = await session.execute(stmt)
    rows = result.scalars().all()

# Unmanaged (full SQLAlchemy control)
async with db.standalone_session() as session:
    async with session.begin():
        result = await session.execute(stmt)
        rows = result.scalars().all()
```

- **Managed**: DuoORM handles commit/rollback and contextvars; good when you just need an advanced clause or two.
- **Unmanaged**: You own commits and lifecycle; use when you want total control or to keep this work isolated from ORM-managed state.
```

Use DuoORM for the fast path, and drop to raw SQLAlchemy the moment you need more. There’s no glass ceiling: `.alchemize()` keeps the full SQLAlchemy surface area one call away.
