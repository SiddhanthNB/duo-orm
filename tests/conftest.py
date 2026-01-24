import os
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
import pytest_asyncio
import subprocess
import textwrap
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import NoSuchModuleError

from duo_orm import Database
from duo_orm.db import _DIALECT_ALIASES


def pytest_addoption(parser):
    """
    Require a single database URL for the suite:
      pytest --db-url sqlite:///./db.sqlite
    """
    parser.addoption(
        "--db-url",
        action="store",
        default=None,
        help="Database URL for sync/async tests. Optional dialect=url label is allowed (e.g., postgres=postgresql+psycopg://...).",
    )


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
    base = parsed.get_backend_name() or drivername.split("+", 1)[0]
    canonical = _DIALECT_ALIASES.get(base, base)
    dialect = canonical
    try:
        driver = parsed.get_driver_name()
    except NoSuchModuleError:
        driver = None
    driver = driver or canonical

    async_tokens = ("async", "aiomysql", "aiosqlite", "asyncpg", "oracledb_async")
    is_async = any(token in driver for token in async_tokens) or "+aiosqlite" in drivername

    # Only mark dialects with well-tested JSON operator support.
    supports_json = dialect in {"postgresql"}
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
    eq_pos = entry.find("=")
    scheme_pos = entry.find("://")
    # Only treat as labeled (dialect=url) if the '=' appears before any scheme delimiter.
    if eq_pos != -1 and (scheme_pos == -1 or eq_pos < scheme_pos):
        key, value = entry.split("=", 1)
        return key.strip() or None, value.strip()
    return None, entry.strip()


def _collect_targets(
    *,
    cli_value: str | None,
) -> List[DbTarget]:
    raw_entries = []
    if cli_value:
        raw_entries.append(cli_value)

    targets: Dict[str, DbTarget] = {}

    for entry in raw_entries:
        _, url = _parse_kv(entry)
        target = _infer_capabilities(url)
        targets[target.label] = target

    if not targets:
        raise pytest.UsageError("Missing required --db-url. Example: pytest --db-url sqlite:///./test.sqlite")

    return list(targets.values())


def pytest_generate_tests(metafunc):
    """
    Dynamically parametrize tests that ask for db_url or async_db_url.
    This keeps the core tests database-agnostic while enabling matrix runs via CLI flags.
    """
    if "db_target" in metafunc.fixturenames:
        targets = _collect_targets(
            cli_value=metafunc.config.getoption("--db-url"),
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
        [tool.duo-orm]
        duo_orm_dir = "appdb"
        """,
    )

    # 2) database.py (driverless URL; async derived internally)
    _write(
        app_dir / "database.py",
        f'''
        from duo_orm import Database
        db = Database("{db_target.url}")
        from . import models  # populate metadata
        ''',
    )

    # 3) models.py
    _write(
        app_dir / "models.py",
        """
        from datetime import datetime, timezone
        from duo_orm import Mapped, mapped_column, relationship
        from sqlalchemy import DateTime, ForeignKey, String, Integer, Identity
        from .database import db

        USER_TABLE = "duo_users"
        POST_TABLE = "duo_posts"

        class User(db.Model):
            __tablename__ = USER_TABLE
            id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
            name: Mapped[str] = mapped_column(String(255), nullable=False)
            age: Mapped[int] = mapped_column(nullable=False)
            created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), info={"set_on": "create"}, nullable=True)
            updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), info={"set_on": {"create", "update"}}, nullable=True)
            posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")

        class Post(db.Model):
            __tablename__ = POST_TABLE
            id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
            title: Mapped[str] = mapped_column(String(255), nullable=False)
            author_id: Mapped[int] = mapped_column(ForeignKey(f"{USER_TABLE}.id"), nullable=False)
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
    _run_cmd(["python", "-m", "duo_orm.migrations.cli", "init", "--dir", "appdb"])
    _run_cmd(["python", "-m", "duo_orm.migrations.cli", "migration", "create", "test schema", "--dir", "appdb"])
    _run_cmd(["python", "-m", "duo_orm.migrations.cli", "migration", "upgrade", "--dir", "appdb"])

    def _teardown():
        subprocess.run(
            ["python", "-m", "duo_orm.migrations.cli", "migration", "downgrade", "base", "--dir", "appdb"],
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
    return Database(db_target.url)


@pytest_asyncio.fixture
async def async_db(db_target, cli_schema):
    """Async Database instance for tests."""
    try:
        database = Database(db_target.url, derive_async=True)
    except ValueError as exc:
        pytest.skip(f"Async not available for this URL: {exc}")
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
