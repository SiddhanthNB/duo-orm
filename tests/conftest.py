import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pytest
import subprocess
import textwrap
from sqlalchemy import event, text
from sqlalchemy.engine import make_url

from your_orm import Database


def pytest_addoption(parser):
    """
    Allow users to supply multiple database URLs when running the suite:
      pytest --db-url sqlite:///./db.sqlite --db-url mysql+aiomysql://user:pass@localhost/db
    Defaults fall back to temporary SQLite files so the suite is runnable out of the box.
    """
    parser.addoption(
        "--db-url",
        action="append",
        default=[],
        help="Database URL(s) for sync tests. Use dialect=url to label (e.g., postgres=postgresql+psycopg://...). Can be passed multiple times.",
    )


def _default_sqlite_url(prefix: str) -> str:
    tmp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    return f"sqlite:///{tmp_dir / 'test.sqlite'}"


@dataclass(frozen=True)
class DbTarget:
    url: str
    dialect: str
    driver: str
    is_async: bool
    supports_json: bool
    supports_array: bool
    supports_has_key: bool

    @property
    def label(self) -> str:
        return self.dialect


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


def _infer_capabilities(url: str) -> DbTarget:
    parsed = make_url(url)
    drivername = parsed.drivername.lower()
    dialect = parsed.get_backend_name() or drivername.split("+", 1)[0]
    driver = parsed.get_driver_name() or drivername

    async_tokens = ("async", "aiomysql", "aiosqlite", "asyncpg", "oracledb_async")
    is_async = any(token in driver for token in async_tokens) or "+aiosqlite" in drivername

    supports_json = dialect in {"postgresql", "mysql", "mariadb", "oracle"}
    supports_array = dialect in {"postgresql"}
    supports_has_key = dialect in {"postgresql"}

    return DbTarget(
        url=url,
        dialect=dialect,
        driver=driver,
        is_async=is_async,
        supports_json=supports_json,
        supports_array=supports_array,
        supports_has_key=supports_has_key,
    )


def _parse_kv(entry: str) -> Tuple[str | None, str]:
    if "=" in entry:
        key, value = entry.split("=", 1)
        return key.strip() or None, value.strip()
    return None, entry.strip()


def _collect_targets(
    *,
    cli_values: List[str],
    env_value: str,
    default_urls: Iterable[str],
) -> List[DbTarget]:
    raw_entries = [entry for entry in cli_values if entry.strip()]
    env_entries = [entry for entry in env_value.split(",") if entry.strip()]
    raw_entries.extend(env_entries)

    targets: Dict[str, DbTarget] = {}

    for entry in raw_entries:
        _, url = _parse_kv(entry)
        target = _infer_capabilities(url)
        targets[target.label] = target

    if not targets:
        for url in default_urls:
            target = _infer_capabilities(url)
            targets[target.label] = target

    return list(targets.values())


def pytest_generate_tests(metafunc):
    """
    Dynamically parametrize tests that ask for db_url or async_db_url.
    This keeps the core tests database-agnostic while enabling matrix runs via CLI flags.
    """
    if "db_target" in metafunc.fixturenames:
        targets = _collect_targets(
            cli_values=metafunc.config.getoption("--db-url"),
            env_value=os.getenv("YOUR_ORM_TEST_DBS", ""),
            default_urls=[_default_sqlite_url("your-orm-sync-")],
        )
        metafunc.parametrize("db_target", targets, scope="session")


@pytest.fixture(scope="session")
def db_target(request) -> DbTarget:
    return request.param


@pytest.fixture(scope="session")
def cli_schema(tmp_path_factory, db_target):
    """
    Create a temporary project, scaffold migrations via CLI, and apply them once per DB target.
    """
    project_root = tmp_path_factory.mktemp(f"cli_proj_{db_target.dialect}")
    app_dir = project_root / "appdb"

    # 1) pyproject.toml
    _write(
        project_root / "pyproject.toml",
        """
        [tool.your-orm]
        your_orm_dir = "appdb"
        """,
    )

    # 2) database.py (driverless URL; async derived internally)
    _write(
        app_dir / "database.py",
        f'''
        from your_orm import Database
        db = Database("{db_target.url}")
        from . import models  # populate metadata
        ''',
    )

    # 3) models.py
    _write(
        app_dir / "models.py",
        """
        from datetime import datetime, timezone
        from your_orm import Mapped, mapped_column, relationship
        from sqlalchemy import DateTime, ForeignKey
        from .database import db

        class User(db.Model):
            __tablename__ = "users"
            id: Mapped[int] = mapped_column(primary_key=True)
            name: Mapped[str] = mapped_column(nullable=False)
            age: Mapped[int] = mapped_column(nullable=False)
            created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), info={"set_on": "create"}, nullable=True)
            updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), info={"set_on": {"create", "update"}}, nullable=True)
            posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")

        class Post(db.Model):
            __tablename__ = "posts"
            id: Mapped[int] = mapped_column(primary_key=True)
            title: Mapped[str] = mapped_column(nullable=False)
            author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
            author = relationship("User", back_populates="posts")
        """,
    )

    (app_dir / "__init__.py").write_text("from .database import db\nfrom .models import User, Post\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{Path.cwd()}:{env.get('PYTHONPATH','')}"

    def _run_cmd(args):
        subprocess.check_call(
            [*args],
            cwd=project_root,
            env=env,
        )

    # 4) Scaffold and migrate
    _run_cmd(["python", "-m", "your_orm.migrations.cli", "init", "--dir", "appdb"])
    _run_cmd(["python", "-m", "your_orm.migrations.cli", "migration", "create", "test schema", "--dir", "appdb"])
    _run_cmd(["python", "-m", "your_orm.migrations.cli", "migration", "upgrade", "--dir", "appdb"])

    def _teardown():
        subprocess.run(
            ["python", "-m", "your_orm.migrations.cli", "migration", "downgrade", "base", "--dir", "appdb"],
            cwd=project_root,
            env=env,
            check=False,
        )

    yield {"project_root": project_root, "app_dir": app_dir}
    _teardown()


@pytest.fixture
def db(db_target, cli_schema):
    """Sync Database instance for tests."""
    if db_target.is_async:
        pytest.skip("Sync tests expect a synchronous driver URL.")
    database = Database(db_target.url)
    with database.sync_engine.begin() as conn:
        conn.execute(text("DELETE FROM posts"))
        conn.execute(text("DELETE FROM users"))
    return database


@pytest.fixture
async def async_db(db_target, cli_schema):
    """Async Database instance for tests."""
    try:
        database = Database(db_target.url, derive_async=True)
    except ValueError as exc:
        pytest.skip(f"Async not available for this URL: {exc}")
    async with database.async_engine.begin() as conn:
        await conn.execute(text("DELETE FROM posts"))
        await conn.execute(text("DELETE FROM users"))
    return database


class StatementCounter:
    """
    Lightweight helper to capture executed SQL statements for N+1 and hidden-write detection.
    Works with sync engines and the sync_engine of async engines.
    """

    def __init__(self, engine):
        self.engine = getattr(engine, "sync_engine", engine)
        self.statements: list[str] = []

    def _before_cursor_execute(self, conn, cursor, statement, parameters, context, executemany):
        self.statements.append(statement)

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._before_cursor_execute)
        return self

    def __exit__(self, exc_type, exc, tb):
        event.remove(self.engine, "before_cursor_execute", self._before_cursor_execute)

    @property
    def select_count(self) -> int:
        return sum(1 for stmt in self.statements if stmt.lstrip().upper().startswith("SELECT"))

    @property
    def write_count(self) -> int:
        writes = ("INSERT", "UPDATE", "DELETE")
        return sum(1 for stmt in self.statements if stmt.lstrip().upper().startswith(writes))
