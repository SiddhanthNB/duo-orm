# Installation

Primary install guidance now lives on the **Get Started** page; this copy remains for direct links and extra detail.

Duo ORM is available on PyPI. Use driverless URLs; the ORM manages drivers, and add extras only when you need them.

## Core Installation

To install Duo ORM with its default (SQLite async) dependencies, run:

```bash
pip install duo-orm  # core + SQLite
```

## Installing Database Drivers

Duo ORM automatically manages which SQLAlchemy driver to use (`psycopg` for PostgreSQL, `asyncmy` for MySQL, etc.) based on your database URL. You only need to ensure the appropriate driver library is installed in your environment.

You can install support for specific databases using extras:

```bash
# For PostgreSQL (includes both sync and async drivers)
pip install "duo-orm[postgresql]"

# For MySQL (includes pymysql for sync, asyncmy for async)
pip install "duo-orm[mysql]"

# For MSSQL (includes pyodbc for sync, aioodbc for async)
pip install "duo-orm[mssql]"

# For Oracle (includes oracledb for sync and async)
pip install "duo-orm[oracle]"
```

To install all available drivers at once:

```bash
pip install "duo-orm[all]"
```

!!! tip "Database URL Format"
    When configuring your `Database` instance, provide only the base dialect URL. Do **not** include the driver in the scheme. Duo ORM selects the correct, tested driver for you.

    - **Correct:** `postgresql://user:pass@host/db`
    - **Incorrect:** `postgresql+psycopg://user:pass@host/db`

## Initializing Your Project

After installation, the `duo-orm` command-line tool will be available. The first step is to initialize your project structure. This command creates your database directory, migrations environment, and configuration.

```bash
duo-orm init
```

By default, this creates a `db/` directory in your project root. You can customize this location:

```bash
duo-orm init --dir src/app/database
```

The `init` command will save your chosen directory to your `pyproject.toml` file, so you don't need to specify it again for other migration commands.

[Learn more about migrations in the Database Migrations guide &raquo;](guides/database-migrations.md)

!!! note "SQLite fallback (rare)"
    Only if your Python lacks stdlib `sqlite3` (e.g., minimal runtimes) do you need `pysqlite3-binary`; alias it to `sqlite3` once at startup as shown in the README.
