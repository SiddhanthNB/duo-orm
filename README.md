# your-orm

An opinionated, modern ORM for Python combining the power of SQLAlchemy 2.0 with a clean, symmetrical API for sync and async operations.

## ⚙️ Core Philosophy

your-orm is built on a simple idea: you are in explicit control of the 'Unit of Work'. The API has two predictable modes:

*   **Default Mode ("Statement-Driven"):** By default, every call (`.save()`, `.first()`) is its own "micro-transaction." The ORM creates a short-lived session that only knows about the single object you are operating on. It will predictably not see related objects, guaranteeing a simple, single-statement operation.

*   **Transaction Mode ("State-Driven"):** When you use `async with db.transaction():`, you "opt-in" to a full-power, state-tracking Unit of Work. The ORM will use a single shared session for the entire block, allowing you to work with multiple objects, relationships, and cascades, all of which will be committed or rolled back together.

**Philosophy:** Clarity over cleverness. The 'magic' of state-tracking only happens when you explicitly ask for it.

## 🧩 Session & Transaction Model

There is no autosession detection logic. By default each ORM call opens a connection, runs exactly one SQL statement, commits (for writes), and closes. When you need multi-step or related work to behave atomically, you wrap it in an explicit transaction block:

```python
async with db.transaction():
    user = await User.where(User.id == 1).first()
    post = Post(title="Hello", author_id=user.id)
    await post.save()
```

Inside the block your code automatically shares a single session. The block commits when it exits successfully and rolls back on error, giving you predictable Unit-of-Work semantics only when you opt-in.

## 🚀 Getting Started

### 1. Installation

```bash
pip install your-orm
# Install the required database driver
pip install your-orm[postgres]
```

### 2. Initialization

Run the `init` command to create the basic structure:

```bash
your-orm init
# or seed a stub models package that re-exports your models
your-orm init --stub-models-init
```

This will create:

*   A `database.py` file to configure your database connection.
*   A `models` directory to define your ORM models.
*   A `migrations` directory for your database schema migrations.

### 3. Defining Models

Define your models in the `models` directory, inheriting from `db.Model`:

```python
# models/user.py
from ..database import db
from your_orm import Mapped, mapped_column

class User(db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    age: Mapped[int]
```

### 4. Creating Migrations

Once you have defined your models, create a migration to apply the schema to your database:

```bash
your-orm migrate create "initial models"
your-orm migrate upgrade
```

### 5. Basic Usage

```python
import asyncio
from .database import db
from .models import User

async def main():
    # Simple writes
    user = User(name="Alice", age=30)
    await user.save() # INSERT

    # Simple reads with Pythonic operators
    users = await User.where(User.age > 25).all()
    alice = await User.where(User.name == "Alice").first()
    
    # More complex queries
    users = await User.where(
        (User.age > 30) & (User.name.startswith_('A'))
    ).all()

    # Updates
    alice.age = 31
    await alice.save() # UPDATE

    # Deletes
    await alice.delete() # DELETE

if __name__ == "__main__":
    asyncio.run(main())
```

## 🔁 Framework Integration

your-orm plays well with FastAPI (and any async framework) by wrapping each request in a dependency that opens a transaction block:

```python
from fastapi import Depends, FastAPI
from .database import db

app = FastAPI()

async def db_session():
    async with db.transaction():
        yield

@app.get("/users/{user_id}")
async def read_user(user_id: int, _=Depends(db_session)):
    return await User.where(User.id == user_id).first()
```

All queries issued inside the request share the same session; pending writes persist until the response and exceptions roll the block back automatically.

## 🧰 Power User Access

When you need raw SQLAlchemy control, opt into a standalone session:

```python
async with db.standalone_session() as session:
    stmt = User.where(User.age > 30).alchemize()
    rows = (await session.scalars(stmt)).all()
```

`db.standalone_session()` returns a plain `AsyncSession`, so you can use Core queries, streaming, or bulk inserts without leaving the your-orm ecosystem.

## 🧭 Behaviour Summary

| Context | Session lifetime | Commit model | Typical use |
| --- | --- | --- | --- |
| Default call (`await User.where(...).first()`) | Short-lived per call | Auto-commit / auto-close | Scripts, simple reads & writes |
| `db.transaction()` block | Shared for the block | Commit on exit, rollback on error | Web requests, multi-step workflows |
| `db.standalone_session()` | Manual | You commit / rollback | Power users, raw SQLAlchemy |

## 🎯 Developer Experience Principles

* **Simple:** `await Model.query()` just works—no session juggling for one-off calls.
* **Safe:** One statement per operation unless you explicitly opt into a transaction.
* **Symmetric:** Sync and async APIs mirror each other (drop `await` for sync code).
* **Predictable:** No hidden flushes, dirty graphs, or autosession guessing.
* **Framework-agnostic:** Works the same in FastAPI, CLIs, scripts, or the REPL.

## 🧪 Validation & Model Flags

* `Model.validate()` – override this hook to enforce business rules; raise `ValidationError(field="age", message)` to block `save()`/`bulk_create()`.
* `Model.fields()` – returns the tuple of column names defined on the model so you can introspect schemas at runtime.
* `Model.to_dict()` – serializes the instance into a plain dictionary of column values for JSON responses, logging, etc.
* `ValidationError` – now part of the public API and carries optional `field` and `detail` metadata so you can surface meaningful errors to clients.
* `info={"set_on": "create"}` / `info={"set_on": {"create","update"}}` – declaratively control when a column is stamped (insert only vs. insert + every save). For compatibility we still honor `auto_now_add` / `auto_now` flags.
  ```python
  created_at = mapped_column(DateTime(timezone=True), info={"set_on": "create"})
  updated_at = mapped_column(DateTime(timezone=True), info={"set_on": {"create", "update"}})
  ```

## 🔍 Query Enhancements

* `QueryBuilder.one()` – fetch exactly one record (raises `ObjectNotFoundError` / `MultipleObjectsFoundError` like SQLAlchemy).
* `QueryBuilder.exists()` – returns `True/False` without materializing rows.
* `QueryBuilder.paginate(limit, offset=0)` – oneliner to apply both LIMIT and OFFSET.
* `QueryBuilder.related(User.posts, where=[...], aggregate="exists", loader="selectin")` – single entry point for filtering/aggregating/eager-loading across one relationship. Eager loading always happens (use `"selectin"` for collections, `"joined"` for scalars via the `loader` option).
* `json(User.profile)["flags"]["beta"].is_null()` – Pythonic JSON-path helper that compiles to regular SQLAlchemy expressions, so you can write complex JSON predicates inside `.where(...)` without juggling driver-specific operators.
* `array(User.tags).includes_any(["python", "orm"])` – expressive ARRAY helper for membership / superset / overlap checks without memorizing dialect-specific operators.
* All helpers work in sync and async contexts just like `.first()` and `.all()`.

## 🧠 Why SQLAlchemy Underneath?

your-orm stands on SQLAlchemy Core for query generation, schema metadata, type handling, and async engines. It deliberately avoids SQLAlchemy’s ORM layer so it stays lightweight, async-first, and free from invisible Unit-of-Work behavior. When you need to drop down, you already have a real `AsyncSession` in hand.

## 📖 Query Operators

### Basic Comparison

| Operator | Example |
| --- | --- |
| `==` | `User.name == "Alice"` |
| `!=` | `User.status != "inactive"` |
| `>` | `User.age > 25` |
| `<` | `User.age < 60` |
| `>=` | `User.salary >= 50000` |
| `<=` | `User.created_at <= date` |

### Membership & Pattern Matching

| Method | Example |
| --- | --- |
| `.in_([...])` | `User.country.in_(['IE', 'IN'])` |
| `.notin_([...])` | `User.role.notin_(['banned', 'test'])` |
| `.contains(value)` | `User.email.contains('@example.com')` |
| `.icontains(value)` | `User.email.icontains('@example.com')` |
| `.startswith(prefix)` | `User.name.startswith('Al')` |
| `.istartswith(prefix)` | `User.name.istartswith('al')` |
| `.iendswith(suffix)` | `User.slug.iendswith('-beta')` |

Case-insensitive helpers (`.icontains`, `.istartswith`, `.iendswith`) are provided by your-orm and work on any column whose SQLAlchemy type derives from `String`. For custom wildcard patterns you can still fall back to SQLAlchemy’s `.like()` / `.ilike()`, but the ergonomic helpers cover 80% of real-world use.

### JSON Path Helper

Use the built-in `json()` helper to compose JSON predicates that drop straight into `where()`:

```python
from your_orm import json

await User.where(
    json(User.profile)["flags"]["beta"].is_null() |
    json(User.profile)["flags"]["beta"].equals("")
).all()
```

It mirrors normal Python dict access (`[...]`) and exposes fluent helpers that emit SQLAlchemy clauses:

| Helper | Purpose | Example |
| --- | --- | --- |
| `json(col)["key"]` | Navigate nested keys/indices | `json(User.profile)["flags"]["beta"]` |
| `.equals(value)` / `==` | Compare scalars (auto-casts to text unless you call `.as_integer()` etc.) | `json(User.profile)["plan"] == "pro"` |
| `.contains(fragment)` | JSON containment (`@>`-style) for dict/list fragments | `json(User.profile).contains({"plan": "enterprise"})` |
| `.has_key(key)` | Key existence (dialect-dependent; raises if unsupported) | `json(User.profile)["flags"].has_key("beta")` |
| `.is_null()` / `.is_not_null()` | Null checks on the selected path | `json(User.profile)["expires_at"].is_null()` |
| `.as_integer()` / `.as_float()` / `.as_boolean()` / `.as_text()` | Cast before comparisons | `json(User.profile)["quota"].as_integer() > 10` |

Because the helper returns ordinary SQLAlchemy expressions, you can combine them with `&`, `|`, `not_`, nest them alongside other filters, and even extract the raw expression via `.expression()`. Dialect support is enforced by SQLAlchemy—if the backend lacks a JSON operator (e.g., `has_key` on SQLite), you’ll get a clear error at query construction time.

### Array Helper

For ARRAY columns, reach for the `array()` helper:

```python
from your_orm import array

await User.where(
    array(User.tags).includes("orm") &
    array(User.tags).includes_all(["python", "asyncio"])
).all()
```

Helper methods map directly to common set-style checks:

| Helper | Purpose | Example |
| --- | --- | --- |
| `.includes(value)` | True if the array contains that single value (`value = ANY(column)`). | `array(User.tags).includes("orm")` |
| `.includes_all(values)` | True if the array contains all provided values (`@>`). | `array(User.tags).includes_all(["python","orm"])` |
| `.includes_any(values)` | True if the array overlaps any provided value (`&&`). | `array(User.tags).includes_any(["java","go"])` |
| `.length()` | Number of elements (uses `cardinality()` when available, otherwise `array_length(..., 1)`). | `array(User.tags).length() > 2` |

These helpers return SQLAlchemy expressions, so they compose with the rest of your filters exactly like built-in clauses. SQLAlchemy/dialect support rules still apply—unsupported ARRAY operators raise the driver’s error (or the helper re-raises with a clearer message).

### Relationship Operators

| Method | Example |
| --- | --- |
| `.any_(expr=None)` | `User.posts.any_(Post.views > 1000)` |
| `.all_(expr)` | `User.posts.all_(Post.status == 'draft')` |

### Logical Combinators

| Operator | Example |
| --- | --- |
| `&` | `(User.age > 30) & (User.status == 'active')` |
| `|` | `(User.is_staff == True) | (User.is_admin == True)` |
