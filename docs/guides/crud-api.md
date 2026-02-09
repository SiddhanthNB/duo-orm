# User Guides: CRUD API

These helpers are the core DuoORM surface. They work with plain dictionaries and also accept Pydantic models (field filtering and validation come from Pydantic when you pass one).

## Instance helpers

- `instance.save()` - Insert or update the current instance. Runs `validate()` and timestamp hooks.
- `instance.update(payload)` - Apply a partial payload (dict or schema) then `save()`. Missing/`None` fields are skipped for Pydantic payloads; dicts keep explicit `None`.
- `instance.delete()` - Delete this row; cascades depend on your relationship config.

## Class helpers

- `Model.create(payload)` - Build and save in one call.
- `Model.create_bulk(payloads, return_models=False, with_hooks=False, batch_size=200)` - Bulk insert; optional per-row hooks/validation with `with_hooks=True`.
- `Model.get(*pk, **pk_parts)` - Primary-key lookup; returns `None` instead of raising.
- `Model.where(...)` - Start a query; see below for query helpers.

## Query helpers (bulk and streaming)

- `Query.update_bulk(payload, with_hooks=False, batch_size=200, require_filter=True, per_batch_transaction=True)` - Bulk update. Safety guard blocks full-table writes unless `require_filter=False`. `with_hooks=True` loads rows in batches, runs `validate()` + timestamp hooks per row. `per_batch_transaction` controls whether each batch commits independently.
- `Query.delete_bulk(with_hooks=False, batch_size=200, require_filter=True, per_batch_transaction=True)` - Bulk delete with the same guard/hook semantics and transaction scope control.
- `Query.count()` / `Query.exists()` - Lightweight read-only checks.
- `Query.iterate(batch_size=200, batch=False)` - Stream rows (or batches). Auto-orders by primary key when no explicit `order_by` is set. Use `paginate(limit, offset)` for page/offset slices.
- `Query.first()` / `Query.one()` / `Query.all()` - Terminal fetches.

## Examples (async)

```python
# Create (dict payload)
u = await User.create({"name": "Ada", "age": 30})

# Partial update
await u.update({"name": "Ada Lovelace"})

# Bulk update with hooks + guard
await User.where(User.age >= 18).update_bulk({"age": User.age + 1}, with_hooks=True)

# Stream in batches of 500
async for batch in User.order_by("id").iterate(batch=True, batch_size=500):
    ...
```

## Examples (sync)

```python
u = User.create({"name": "Syncy", "age": 40})
u.update({"age": 41})
User.where(User.age > 20).delete_bulk(require_filter=False)  # intentional full-table delete
for user in User.iterate(batch=False, batch_size=100):
    print(user.id)
```

## Hooks, safety, and batching

- `with_hooks=True` → loads rows, runs `validate()` and timestamp hooks per row, then flushes in batches.
- `require_filter=True` → prevents accidental table-wide updates/deletes. Set to `False` only when you truly want to touch every row.
- `batch_size` applies to hook-enabled paths and streaming; must be positive.
- `per_batch_transaction=True` → for hook-enabled bulk ops (`with_hooks=True`), commits each batch independently (default). This keeps locks short and reduces deadlock risk in busy systems. Set it to `False` if you need a single all-or-nothing transaction across every batch (at the cost of longer locks).

!!! warning "Bulk deletes and cascades: `with_hooks` changes behavior"
    - `with_hooks=False` (default) executes a direct SQL `DELETE`/`UPDATE`. It is fast, but **bypasses all Python-level logic**, including ORM cascades (like `cascade="all, delete-orphan"`), `validate()`, and event listeners. It only respects **database-level** cascades (`ON DELETE CASCADE`).
    - `with_hooks=True` loads each row and deletes/updates through the ORM session, so **ORM cascades and hooks run**.

    Example: ensure child rows are deleted when using ORM cascades.

    ```python
    from duo_orm import Mapped, mapped_column, relationship, ForeignKey
    from db.database import db

    class Parent(db.Model):
        __tablename__ = "parents"
        id: Mapped[int] = mapped_column(primary_key=True)
        children = relationship("Child", cascade="all, delete-orphan")

    class Child(db.Model):
        __tablename__ = "children"
        id: Mapped[int] = mapped_column(primary_key=True)
        parent_id: Mapped[int] = mapped_column(ForeignKey("parents.id"))

    # This is a direct SQL delete; ORM cascades do NOT run.
    await Parent.where(Parent.id == 1).delete_bulk()

    # This loads rows and runs ORM cascades/hooks.
    await Parent.where(Parent.id == 1).delete_bulk(with_hooks=True)
    ```

!!! warning "with_hooks=True is slower"
    Enabling `with_hooks=True` for bulk ops loads every matched row into memory to run hooks and ORM cascades. This can be significantly slower and more memory intensive than the default set-based path. Use it only when you need per-row validation/timestamp logic or ORM cascades, and keep the matched set small.

!!! note "SQL Server and composite primary keys"
    Hook-enabled bulk ops (`with_hooks=True`) batch rows using row-value comparisons on primary keys. SQL Server does not support that syntax for composite primary keys, so these paths are not available there. This is a SQL Server and SQLAlchemy dialect limitation, not a DuoORM one.

## Quick reference

| Task | Helper | Sync | Async |
| --- | --- | --- | --- |
| Build + save | `Model.create(payload)` | `User.create({...})` | `await User.create({...})` |
| Bulk insert | `Model.create_bulk(payloads, return_models=False, with_hooks=False)` | `User.create_bulk([...])` | `await User.create_bulk([...])` |
| Save existing instance | `instance.save()` | `u.save()` | `await u.save()` |
| Partial update (instance) | `instance.update(payload)` | `u.update({...})` | `await u.update({...})` |
| Bulk update | `Query.update_bulk(payload, with_hooks=False, require_filter=True)` | `User.where(...).update_bulk({...})` | `await User.where(...).update_bulk({...})` |
| Delete instance | `instance.delete()` | `u.delete()` | `await u.delete()` |
| Bulk delete | `Query.delete_bulk(with_hooks=False, require_filter=True)` | `User.where(...).delete_bulk()` | `await User.where(...).delete_bulk()` |
| Primary-key lookup | `Model.get(pk)` | `User.get(1)` | `await User.get(1)` |
| Count / existence | `Query.count()` / `Query.exists()` | sync/async | sync/async |
| Stream rows | `Query.iterate(batch_size=..., batch=False)` | generator | async generator |

!!! note "Bulk transaction scope"
    `update_bulk` and `delete_bulk` accept `per_batch_transaction=True|False` for hook-enabled bulk ops (`with_hooks=True`) to control whether each batch commits independently.

## Pydantic?

Passing a Pydantic model to any payload parameter is allowed; DuoORM strips non-column keys and uses Pydantic’s validation/field exclusion. Pydantic-specific helpers (`from_schema`, `apply_schema`, `to_schema`) are covered in the [Pydantic Integration](pydantic-integration.md) guide.

## See also
- Query construction patterns: [Querying Data](querying-data.md)
- Transactions and context: [Sessions and Transactions](sessions-and-transactions.md)
- Schema validation/serialization: [Pydantic Integration](pydantic-integration.md)
