# DuoORM

[![PyPI version](https://img.shields.io/pypi/v/duo-orm.svg?cacheSeconds=300)](https://pypi.org/project/duo-orm/)
[![Python versions](https://img.shields.io/pypi/pyversions/duo-orm.svg?cacheSeconds=300)](https://pypi.org/project/duo-orm/)
[![Docs](https://img.shields.io/badge/docs-readthedocs-blue.svg)](https://duo-orm.readthedocs.io/)

An opinionated ORM with symmetrical sync/async APIs, explicit unit-of-work control, and ready-to-use Alembic scaffolding. DuoORM manages drivers for you—use driverless URLs like `postgresql://...` or `sqlite:///app.db` and it wires up the correct sync/async engines under the hood (SQLAlchemy 2.x).

## Highlights

- One API for sync *and* async (add `await` when needed).
- Explicit unit of work: single-statement by default; opt into `db.transaction()` for shared sessions and cascades.
- Driverless URLs; DuoORM injects the right sync/async driver per dialect.
- Import common SQLAlchemy types and helpers directly from `duo_orm` (e.g., `String`, `JSON`, `PG_ARRAY`, `text`, `func`).
- Built-in Alembic CLI scaffolding and migration commands.
- Tested across PostgreSQL, MySQL, MSSQL, Oracle, and SQLite (coverage matrix).

## Install

```bash
pip install duo-orm                  # core + sqlite

# Or pick your dialect
pip install "duo-orm[postgresql]"    # psycopg (sync+async)
pip install "duo-orm[mysql]"         # pymysql + asyncmy
pip install "duo-orm[mssql]"         # pyodbc + aioodbc
pip install "duo-orm[oracle]"        # oracledb (sync+async)
pip install "duo-orm[all]"           # install everything
```

SQLite fallback (only if your Python lacks stdlib `sqlite3`, e.g., minimal Docker/Lambda):

```bash
pip install pysqlite3-binary
python - <<'PY'
import sys, pysqlite3
sys.modules["sqlite3"] = pysqlite3
PY
```

## Quickstart

```python
from duo_orm import Database, Mapped, mapped_column, String

db = Database("sqlite:///./app.db")  # driverless URL

class User(db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))

# One-shot (single statement/session)
user = User.where(User.name == "Ada").first()

# Transactional work (shared session)
async def create_user():
    async with db.transaction():
        u = User(name="New")
        await u.save()

# When you're done (scripts/CLIs), optionally tear down engines
db.disconnect()
```

### Engine lifecycle helpers

- `db.connect()` eagerly initializes sync/async engines so misconfiguration surfaces early (optional; engines still initialize lazily).
- `db.disconnect()` disposes any initialized engines and clears cached factories; use it at the end of scripts/CLIs to release pools explicitly. Context managers (`db.transaction()`, `standalone_session()`, `sync_standalone_session()`) already close sessions on exit.

## Documentation

- Full docs & guides: https://duo-orm.readthedocs.io/
- Quickstart: https://duo-orm.readthedocs.io/en/latest/quickstart/
- API reference: https://duo-orm.readthedocs.io/en/latest/reference/

## License

MIT
