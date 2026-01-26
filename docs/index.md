# Get Started with Duo ORM

<div class="grid cards" markdown>
- :material-database-search:{ .lg .middle } **Symmetrical API**

    ---
    One API for sync and async. Add `await` in async code and use the same calls in sync code.

- :material-lightning-bolt:{ .lg .middle } **Opinionated & Simple**

    ---
    Default is single-statement, standalone calls. Use transactions when you need related graphs or cascades.

- :material-rocket-launch:{ .lg .middle } **SQLAlchemy + Alembic, built in**

    ---
    SQLAlchemy Core foundation with Alembic scaffolding included, so migrations and ORM stay in one place alongside explicit unit-of-work modes, driver management, ergonomic helpers, and a ready-to-go CLI.
</div>

Duo ORM is an opinionated yet straightforward ORM: you control when stateful work happens, you get symmetrical sync/async APIs, and you don’t manage drivers. Provide **driverless URLs** and the ORM injects the right sync/async drivers for you.

## Why Duo ORM (quickly)

- Powered by SQLAlchemy Core with Alembic migrations scaffolded for you, so you avoid glue code.
- Symmetrical sync/async APIs and CLI tooling so you can ship fast in services, scripts, or workers.
- Driver management built in: use `postgresql://...`, `mysql://...`, `mssql://...`, `oracle://...`, or `sqlite:///...`; no `+driver` suffixes needed.
- Opinionated defaults that stay simple until you opt into transactions for related graphs.

## Install

```bash
pip install duo-orm  # core + SQLite
# Or pick your drivers
pip install "duo-orm[postgresql]"
pip install "duo-orm[mysql]"
pip install "duo-orm[mssql]"
pip install "duo-orm[oracle]"
pip install "duo-orm[all]"
```

## Hello Duo ORM

### Standalone (default)

Each call is a single statement with its own short-lived session. This is great for simple reads/writes and scripts.

```python
from duo_orm import Database, Mapped, mapped_column

db = Database("sqlite:///./app.db")  # driverless URL; drivers managed for you

class User(db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

# One-shot read (single statement/session)
user = User.where(User.name == "Ada").first()
```

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

app = FastAPI()

async def db_session():
    async with db.transaction():
        yield

@app.post("/users")
async def create_user(data: dict, _=Depends(db_session)):
    user = User(**data)
    await user.save()
    return user.to_dict()
```

## Project scaffold

Use the CLI to create the recommended layout (database entrypoint, models package, migrations).

```bash
duo-orm init
```

## Next steps

- Define models: [User Guides: Defining Models](guides/defining-models.md)
- Query data: [User Guides: Querying Data](guides/querying-data.md)
- Full walkthrough: [Quickstart](quickstart.md)

!!! note "Need a SQLite fallback?"
    Only if your Python lacks stdlib `sqlite3` (e.g., minimal runtimes). Install `pysqlite3-binary` and alias `sqlite3` once at startup as shown in the README.
