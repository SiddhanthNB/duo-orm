<p align="center">
  <a href="https://duo-orm.readthedocs.io/">
    <img src="docs/assets/logo.svg" width="200" alt="DuoORM Logo">
  </a>
</p>
<p align="center">
    <a href="https://pypi.org/project/duo-orm/">
        <img src="https://img.shields.io/pypi/v/duo-orm.svg?cacheSeconds=300" alt="PyPI version">
    </a>
    <a href="https://pypi.org/project/duo-orm/">
        <img src="https://img.shields.io/pypi/pyversions/duo-orm.svg?cacheSeconds=300" alt="Python versions">
    </a>
    <a href="https://duo-orm.readthedocs.io/">
        <img src="https://img.shields.io/badge/docs-readthedocs-blue.svg" alt="Docs">
    </a>
</p>

# DuoORM

DuoORM is a modern ORM built on SQLAlchemy 2.0 that empowers your data models, turning them into a powerful and expressive query interface. It's designed for developers who love clean, symmetrical sync/async APIs and explicit control over their unit of work, without sacrificing the power of the underlying SQLAlchemy Core.

## Key Features

- **Symmetrical Sync & Async API:** Write your queries once. Use `await` in an async context or call directly in a sync context. The API is identical.
- **Fluent, Model-Centric API:** Chainable methods like `.where()`, `.order_by()`, and `.limit()` flow directly from your models. CRUD is intuitive with methods like `Model.create()` and `instance.save()`.
- **Explicit Unit of Work:** By default, every operation is a single, isolated statement. For complex workflows, use the `db.transaction()` context manager to share a single session and guarantee atomicity.
- **Automated Driver Management:** Use clean, driverless database URLs (e.g., `postgresql://...`). DuoORM automatically injects the correct, high-performance sync and async drivers for you.
- **First-Class Pydantic Integration:** Use Pydantic models for validated data creation and updates right out of the box, or use plain dictionaries. The choice is yours.
- **Powerful Escape Hatch:** Never get blocked. Drop down to raw SQLAlchemy at any time by calling `.alchemize()` on any query to get the underlying `Select` object for advanced SQL needs.

## Installation

```bash
# Core library with SQLite support
pip install duo-orm

# Or install with a specific database driver
pip install "duo-orm[postgresql]"
pip install "duo-orm[mysql]"
```

## Quickstart

Getting started with DuoORM is a simple four-step process.

### 0. Initialize your Project

DuoORM includes a handy CLI to set up a recommended project structure for your database code.

```bash
# This creates a `db/` directory with models, schemas, and migrations.
$ duo-orm init
```

### 1. Define your Models

First, configure your database and define your ORM models in a Python file (e.g., `db/models.py`).

```python
from duo_orm import Database, Mapped, mapped_column

# Configure the database with a clean, driverless URL
db = Database("sqlite:///app.db")

# Define an ORM model
class User(db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    age: Mapped[int]
```

### 2. Create Database Tables

Next, use the `duo-orm` CLI in your terminal to create the database tables from your models. This provides a safe, version-controlled schema for your application.

```bash
# First, generate a migration script from your models
$ duo-orm migration create "Initial user schema"

# Then, apply the migration to the database
$ duo-orm migration upgrade
```

### 3. Query your Data

With your tables created, you can now use DuoORM's fluent API to interact with your database in any Python script.

```python
import asyncio
from db.models import User # Import your model from the file you created

async def query_users():
    # Create a user (in an async context)
    ada = await User.create({"name": "Ada Lovelace", "age": 35})
    print(f"Created: {ada.name}")

    # Find a user (the API is the same in sync contexts, just without `await`)
    found_user = await User.where(User.name == "Ada Lovelace").first()
    print(f"Found: {found_user.name}")

# Run the async function
asyncio.run(query_users())
```

## Full Documentation

For detailed guides on all features, including transactions, Pydantic integration, database migrations, and advanced queries, please see the full documentation on **[ReadTheDocs](https://duo-orm.readthedocs.io/)**.

## Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request.

## License

This project is licensed under the MIT License.
