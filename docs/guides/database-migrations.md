# User Guides: Database Migrations

Duo ORM provides a command-line tool, `duo-orm`, to manage your database schema evolution. This tool is a wrapper around the powerful [Alembic](https://alembic.sqlalchemy.org/) library, providing an opinionated and streamlined workflow.

## The Migration Workflow

The core workflow for database migrations consists of three steps:

1.  **Initialize**: Set up the migration environment in your project. You only need to do this once.
2.  **Create**: After you change your models, you generate a new migration script that contains the Python code to apply those changes to your database schema.
3.  **Upgrade/Downgrade**: You apply (or revert) these migration scripts to your database to bring its schema up-to-date.

## 1. Initializing Your Project (`init`)

The `duo-orm init` command bootstraps your entire database setup.

```bash
duo-orm init
```

This command does several things:

1.  **Creates a directory structure**: By default, it creates a `db/` directory with subdirectories for `models` and `migrations`.
2.  **Generates configuration**: It creates an `alembic.ini` and `env.py` file inside `db/migrations/` that are pre-configured to work with Duo ORM.
3.  **Creates a database entrypoint**: It generates a `db/database.py` file where you will configure your `Database` instance.
4.  **Updates `pyproject.toml`**: It saves your configuration to your project's `pyproject.toml` file, so you don't have to specify it again.

```toml title="pyproject.toml"
[tool.duo-orm]
duo_orm_dir = "db"
```

You can customize the directory using the `--dir` option:
```bash
duo-orm init --dir src/app/core/database
```

## 2. Creating Migrations (`migration create`)

After you have created or modified your models in the `db/models/` directory, you can generate a migration script.

```bash
duo-orm migration create "add user and post tables"
```

This command will:
1.  Connect to your database to inspect its current schema.
2.  Inspect your `db.Model` classes to determine the desired schema.
3.  Compare the two and generate a new Python script in the `db/migrations/versions/` directory containing the `upgrade()` and `downgrade()` functions to bridge the difference.

It's good practice to give your migrations a short, descriptive message.

!!! important
    For `migration create` to work, it needs to be able to connect to your database. Make sure the URL in your `db/database.py` file is valid and points to a running database instance.

## 3. Applying and Reverting Migrations

Once you have a migration script, you can apply it to your database.

### `upgrade`

The `upgrade` command applies migrations.

```bash
# Apply all pending migrations up to the latest version
duo-orm migration upgrade
```

You can also specify a target revision:
```bash
# Upgrade to a specific revision
duo-orm migration upgrade <revision_hash>
```
The special keyword `head` refers to the latest migration.

### `downgrade`

The `downgrade` command reverts migrations.

```bash
# Revert the most recent migration
duo-orm migration downgrade
```

By default, this reverts a single level. You can also specify a target revision to revert to.

```bash
# Downgrade to a specific revision
duo-orm migration downgrade <revision_hash>
```

### `history`

To see a list of all migrations and their status, use the `history` command.

```bash
duo-orm migration history
```
This will show you the migration history, indicating which revision is currently applied to the database.
