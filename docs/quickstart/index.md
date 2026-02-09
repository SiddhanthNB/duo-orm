# Quickstart

This guide walks through setup and the two core usage modes: standalone (default) and transactions for related graphs.

## Concepts at a glance

- **Standalone (statement-driven)**: Each call (`save`, `first`, `create`) uses its own short-lived session/statement. Great for simple CRUD and scripts.
- **Transaction-driven**: Wrap work in `db.transaction()` to share one session across steps; needed for related writes, cascades, or multi-step flows.
- **Sync vs async**: Same API; async is used when an event loop is running. Set `derive_async=False` if you only want sync engines.
- **Payloads**: All helpers accept plain dicts; Pydantic is optional validation/serialization sugar.
- **Escape hatch**: Call `.alchemize()` on any query to get the raw SQLAlchemy `Select` when you need advanced SQL (CTEs, window functions, hints). See [The Escape Hatch](../guides/escape-hatch.md).

## Troubleshooting / FAQ

- **“Do not include a driver in the URL”** - Use driverless URLs (`postgresql://...`, not `postgresql+psycopg://...`). DuoORM injects drivers automatically.
- **Dialect mismatch** - If you pass `dialect=...`, it must match the URL’s dialect; otherwise a `ConfigurationError` is raised.
- **Async-only errors** - If you created `Database(..., derive_async=False)`, async helpers (`await Model.create(...)`, `db.async_engine`) will raise; use sync calls instead.
- **require_filter guard** - Bulk helpers default to `require_filter=True` to block table-wide writes. Set to `False` only when you intend to affect every row.

## Setup

### Install

```bash
pip install duo-orm
```

Use driverless URLs (e.g., `postgresql://...`, `sqlite:///...`); the ORM injects the right drivers. Optionally add `dialect="postgresql"` (or `mysql`, `mssql`, `oracle`, `sqlite`) to `Database(...)` if you want the URL validated against a declared dialect.

### Scaffold the project

Create the recommended layout (database entrypoint, models package, schemas package, migrations).

```bash
duo-orm init
```

Result:

```
.
├── db/
│   ├── database.py
│   ├── schemas/
│   │   └── __init__.py
│   ├── models/
│   │   └── __init__.py
│   └── migrations/
│       ├── alembic.ini
│       ├── env.py
│       └── ...
└── pyproject.toml
```

Need a different location? Run:

```bash
duo-orm init --dir path/to/db
```

This creates or updates `pyproject.toml` so future migration commands find your db stack:

```toml title="pyproject.toml"
[tool.duo-orm]
duo_orm_dir = "path/to/db"
```

### Configure the database

Edit `db/database.py` to set your connection.

```python title="db/database.py"
from duo_orm import Database

db = Database("sqlite:///./test.db")  # driverless URL; drivers managed for you
```

!!! note
    If you pass `derive_async=False`, DuoORM will not build an async URL/engine. You can still use the synchronous API, but any async calls (or `db.async_engine`) will raise.

!!! tip "Fast demo setup"
    For quick demos or tests (not production), you can create tables directly without migrations:
    ```python
    await db.create_all()  # async context
    # or: db.create_all()  # sync context
    ```

### Define models

Create `db/models/user.py` and `db/models/post.py`.

```python title="db/models/user.py"
from __future__ import annotations
from typing import List
from duo_orm import Mapped, mapped_column, relationship
from ..database import db

class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    age: Mapped[int]

    posts: Mapped[List["Post"]] = relationship(back_populates="author")
```

```python title="db/models/post.py"
from __future__ import annotations
from duo_orm import Mapped, mapped_column, relationship, ForeignKey
from ..database import db
from .user import User

class Post(db.Model):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    author: Mapped["User"] = relationship(back_populates="posts")
```

Expose them in `db/models/__init__.py`:

```python title="db/models/__init__.py"
from .user import User
from .post import Post
```

### Define Pydantic schemas

`duo-orm init` also creates `db/schemas/`. Keep your Pydantic models here, mirroring your ORM models. DuoORM treats Pydantic as a core dependency, so no extra install flags are needed.

```python title="db/schemas/user.py"
from pydantic import BaseModel, ConfigDict

class User:
    class Create(BaseModel):
        email: str
        name: str
        age: int

    class Update(BaseModel):
        email: str | None = None
        name: str | None = None
        age: int | None = None
        model_config = ConfigDict(extra="forbid")

    class Read(BaseModel):
        model_config = ConfigDict(from_attributes=True)
        id: int
        email: str
        name: str
        age: int
```

!!! tip
    Schemas are optional convenience. All CRUD helpers also accept plain dictionaries if you prefer to skip Pydantic for certain code paths or tests.

### Create and apply migrations

Generate and apply a migration to create the tables.

```bash
duo-orm migration create "add user and post models"
duo-orm migration upgrade
```

## Usage

### Standalone calls (default)

Most work uses single-statement calls with short-lived sessions. This is ideal for simple CRUD and scripts.

```python title="main.py"
import asyncio
from db.database import db
from db.models import User
from db.schemas import User as UserSchema

async def main():
    await db.create_all()  # quick demo setup; use migrations in real projects
    # Create from a Pydantic payload (validated) and save
    ada = await User.create(UserSchema.Create(email="ada@example.com", name="Ada", age=30))
    # One-shot read
    ada = await User.where(User.name == "Ada").first()
    print(ada.to_schema(UserSchema.Read))

if __name__ == "__main__":
    asyncio.run(main())
```

Run:

```bash
python main.py
```

### Controlled transactions

Need more control over how work commits or rolls back? Use a transaction block. It becomes important when you work with related graphs, cascades, or multi-step flows that must stay consistent. In frameworks, a common pattern is to wrap each request in a dependency (e.g., FastAPI) that opens a transaction so handlers avoid dirty or partial state.

```python title="main.py"
import asyncio
from db.database import db
from db.models import User, Post
from db.schemas import User as UserSchema

async def main():
    async with db.transaction():  # shared session for the block
        alice = await User.create(UserSchema.Create(email="alice@example.com", name="Alice", age=30))

        await Post(title="DuoORM Quickstart", author=alice).save()
        await Post(title="Advanced Queries", author=alice).save()

        user_with_posts = await User.related("posts").where(User.name == "Alice").first()
        print([p.title for p in user_with_posts.posts])

if __name__ == "__main__":
    asyncio.run(main())
```

### Synchronous?

Drop `await` and use the same API; the ORM chooses sync or async automatically based on context.

```python title="sync_main.py"
from db.database import db
from db.models import User
from db.schemas import User as UserSchema

def main():
    db.create_all()  # quick demo setup; use migrations in real projects
    User.create(UserSchema.Create(email="sync@example.com", name="Syncy", age=45))  # standalone
    with db.transaction():             # shared session for the block
        User.create(UserSchema.Create(email="another@example.com", name="Another", age=50))

if __name__ == "__main__":
    main()
```

## Handy CRUD helpers

- `Model.create(payload)` / `Model.create_bulk(payloads, return_models=False)`: Persist in one step. Accepts dicts (or Pydantic models if you prefer); non-column keys are ignored.
- `instance.save()` vs `Model.create(...)`: `save()` lets you build an instance and then persist; `create()` builds + saves in one call.
- `instance.update(payload)` / `Query.update_bulk(payload, with_hooks=False, require_filter=True)`: Partial apply; missing/`None` fields are skipped when the payload supports that (e.g., Pydantic). The bulk variant guards against table-wide writes unless you set `require_filter=False`.
- `instance.delete()` / `Query.delete_bulk(...)`: Remove a single instance or many. The bulk path supports `with_hooks` and batching.
- `Query.iterate(batch_size=200, batch=False)`: Stream rows (or batches); auto-orders by primary key when no explicit `order_by` is set. Use `paginate(limit, offset)` for page-style slices.

See also:

- Full CRUD coverage and examples: [CRUD API](../guides/crud-api.md)
- Framework example: [Framework Integration](fastapi.md)
- Deeper query patterns: [User Guides: Querying Data](../guides/querying-data.md)
- Raw SQLAlchemy when you need it: [The Escape Hatch](../guides/escape-hatch.md)
