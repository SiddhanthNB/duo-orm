# Get Started with DuoORM

<div class="grid cards" markdown>
- **Symmetrical API**

    ---
    One API for sync and async. Add `await` in async code and use the same calls in sync code.

- **Opinionated & Simple**

    ---
    Default is single-statement, standalone calls. Use transactions when you need related graphs or cascades.

- **SQLAlchemy & Alembic ready**

    ---
    SQLAlchemy Core base with Alembic scaffolding included, keeping queries and migrations together.

- **Pydantic built in**

    ---
    Pydantic ships by default: validate inputs, pass schemas to create/update, and serialize results to schemas with no extra wiring.

</div>

DuoORM is an opinionated yet straightforward ORM: you control when stateful work happens, you get symmetrical sync/async APIs, and you don’t manage drivers. Provide driverless URLs and the ORM injects the right sync/async drivers for you. Pydantic ships in the box, so request/response schemas plug in directly.

## Why DuoORM

- Powered by SQLAlchemy Core with Alembic migrations scaffolded for you, so you avoid glue code.
- Symmetrical sync/async APIs and CLI tooling so you can ship fast in services, scripts, or workers.
- Driver management built in: use `postgresql://...`, `mysql://...`, `mssql://...`, `oracle://...`, or `sqlite:///...`; no `+driver` suffixes needed.
- Opinionated defaults that stay simple until you opt into transactions for related graphs.

## Install

```bash
pip install duo-orm  # core + SQLite

# Or pick your dialect
pip install "duo-orm[postgresql]"
pip install "duo-orm[mysql]"
pip install "duo-orm[mssql]"
pip install "duo-orm[oracle]"
pip install "duo-orm[all]"
```

## Hello DuoORM

### Standalone (default)

Each call is a single statement with its own short-lived session. This is great for simple reads/writes and scripts.

```python
from duo_orm import Database, Mapped, mapped_column

db = Database("sqlite:///./app.db")  # driverless URL

class User(db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

# Quick demo setup (use migrations in real projects)
db.create_all()

# One-shot read (single statement/session)
user = User.where(User.name == "Ada").first()
```

!!! tip "Use driverless URLs (load from env)"
    Provide only the base dialect in your URL (for example `postgresql://app@host/db`, `sqlite:///./app.db`). Do not include driver suffixes like `+psycopg`; DuoORM injects the correct sync/async drivers for you. Prefer loading the URL from an environment variable, e.g.:
    ```python
    import os
    from duo_orm import Database
    db = Database(os.environ.get("DATABASE_URL", "sqlite:///./app.db"))
    ```
    If you want an extra guardrail, pass `dialect="postgresql"` (or `mysql`, `mssql`, `oracle`, `sqlite`) to `Database(...)` and it will error if the URL and declared dialect disagree.

### When to use transactions

Use a transaction block when you need related graphs, cascades, or multi-step consistency.

```python
# Script-friendly: ensure related writes stay consistent
from db.database import db
from db.models import User, Post

async def main():
    async with db.transaction():
        alice = User(name="Alice")
        await alice.save()
        await Post(title="Hello", author=alice).save()
        await Post(title="More", author=alice).save()
        # all writes commit together, or roll back together on error
```

`db.transaction()` also plugs cleanly into popular frameworks like FastAPI by wrapping each request in a transaction-bound dependency.

```python
from fastapi import Depends, FastAPI
from db.database import db
from db.models import User
from db.schemas import User as UserSchema

app = FastAPI()

async def db_session():
    async with db.transaction():
        yield

@app.post("/users")
async def create_user(data: UserSchema.Create, _=Depends(db_session)):
    return await User.create(data)
```

## Project scaffold

Use the CLI to create the recommended layout (database entrypoint, models package, schemas package, migrations).

```bash
duo-orm init
```

## Next steps

- Define models: [User Guides: Defining Models](guides/defining-models.md)
- Wire schemas: [Pydantic Integration](guides/pydantic-integration.md)
- Query data: [User Guides: Querying Data](guides/querying-data.md)
- Full walkthrough: [Quickstart](quickstart/index.md)
- Advanced recipes: [Cookbook](guides/cookbook.md)

## Troubleshooting / FAQ

!!! note "SQLite fallback (rare)"
    Only if your Python lacks stdlib `sqlite3` (e.g., minimal runtimes). Install `pysqlite3-binary`, then alias it once at startup:
    ```python
    import sys, pysqlite3
    sys.modules["sqlite3"] = pysqlite3
    ```

??? info "Which drivers are used?"
    - PostgreSQL: `psycopg` (sync and async)
    - MySQL/MariaDB: `pymysql` (sync), `asyncmy` (async)
    - MSSQL: `pyodbc` (sync), `aioodbc` (async)
    - Oracle: `oracledb` (sync and async)
    - SQLite: stdlib `sqlite3` (sync), `aiosqlite` (async)
