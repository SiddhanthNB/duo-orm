
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import toml
from click.testing import CliRunner

from duo_orm.migrations.cli import cli
from duo_orm.migrations.config import (
    DB_OBJECT_NAME,
    _generate_files,
    _normalize_dir,
    _persist_pyproject_config,
    _resolve_layout,
    get_alembic_config,
)
from duo_orm.exceptions import ConfigurationError


def test_normalize_dir_rejects_bad_segments():
    with pytest.raises(ConfigurationError):
        _normalize_dir("/absolute/path")
    with pytest.raises(ConfigurationError):
        _normalize_dir("not-valid!")


def test_generate_files_creates_layout(tmp_path):
    base_dir = tmp_path / "db"
    _generate_files(base_dir, "db", DB_OBJECT_NAME, "custom_version")

    migrations_dir = base_dir / "migrations"
    assert (migrations_dir / "alembic.ini").exists()
    assert (migrations_dir / "env.py").exists()
    assert (migrations_dir / "versions").is_dir()

    env_py = (migrations_dir / "env.py").read_text()
    assert "db.database" in env_py
    assert DB_OBJECT_NAME in env_py
    assert "custom_version" in env_py


def test_persist_pyproject_config(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()

    _persist_pyproject_config(project_root, "custom/db")
    contents = toml.load(project_root / "pyproject.toml")
    assert contents["tool"]["duo-orm"]["duo_orm_dir"] == "custom/db"


def test_get_alembic_config_loads_db(monkeypatch, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()

    pyproject_path = project / "pyproject.toml"
    pyproject_path.write_text(toml.dumps({"tool": {"duo-orm": {"duo_orm_dir": "db"}}}))

    db_package = project / "db"
    db_package.mkdir()
    (db_package / "__init__.py").write_text("")

    db_file = db_package / "database.py"
    db_file.write_text(
        "from duo_orm import Database\n"
        f"db = Database('sqlite:///{project / 'config.sqlite'}')\n"
    )

    _generate_files(db_package, "db", DB_OBJECT_NAME, "proj_version")

    monkeypatch.chdir(project)
    monkeypatch.syspath_prepend(str(project))

    cfg = get_alembic_config()

    imported = importlib.import_module("db.database")
    assert cfg.get_main_option("sqlalchemy.url") == str(imported.db.url)
    assert cfg.get_main_option("version_table") == "proj_version"
    assert cfg.attributes["target_metadata"] is imported.db.metadata


def test_cli_init_scaffolds_project(monkeypatch, tmp_path):
    project = tmp_path / "cli_proj"
    project.mkdir()
    monkeypatch.chdir(project)
    runner = CliRunner()

    result = runner.invoke(cli, ["init", "--dir", "data"])
    assert result.exit_code == 0

    base_dir, migrations_dir, module_path = _resolve_layout(project, "data")
    assert (migrations_dir / "alembic.ini").exists()
    assert (base_dir / "database.py").exists()
    assert (base_dir / "models").is_dir()


def test_cli_migration_commands_dispatch(monkeypatch, tmp_path):
    called = {}

    def fake_get_cfg(override_dir=None):
        called["cfg"] = override_dir or "default"
        return object()

    def fake_revision(cfg, message, autogenerate):
        called["revision"] = (cfg, message, autogenerate)

    def fake_upgrade(cfg, revision):
        called["upgrade"] = (cfg, revision)

    def fake_downgrade(cfg, revision):
        called["downgrade"] = (cfg, revision)

    def fake_history(cfg):
        called["history"] = cfg

    monkeypatch.setattr("duo_orm.migrations.cli.get_alembic_config", fake_get_cfg)
    monkeypatch.setattr("duo_orm.migrations.cli.command.revision", fake_revision)
    monkeypatch.setattr("duo_orm.migrations.cli.command.upgrade", fake_upgrade)
    monkeypatch.setattr("duo_orm.migrations.cli.command.downgrade", fake_downgrade)
    monkeypatch.setattr("duo_orm.migrations.cli.command.history", fake_history)

    runner = CliRunner()
    base = tmp_path / "proj"
    base.mkdir()
    monkeypatch.chdir(base)

    result_create = runner.invoke(cli, ["migration", "create", "msg", "--dir", "dbdir"])
    assert result_create.exit_code == 0
    assert called["cfg"] == "dbdir"
    assert called["revision"][1] == "msg"
    assert called["revision"][2] is True

    result_up = runner.invoke(cli, ["migration", "upgrade", "head"])
    assert result_up.exit_code == 0
    assert called["upgrade"][1] == "head"

    result_down = runner.invoke(cli, ["migration", "downgrade", "-1"])
    assert result_down.exit_code == 0
    assert called["downgrade"][1] == "-1"

    result_history = runner.invoke(cli, ["migration", "history"])
    assert result_history.exit_code == 0
    assert "history" in called


def test_cli_commands_error_path(monkeypatch, tmp_path):
    def bad_get_cfg(override_dir=None):
        raise ConfigurationError("boom")

    monkeypatch.setattr("duo_orm.migrations.cli.get_alembic_config", bad_get_cfg)
    runner = CliRunner()
    base = tmp_path / "proj"
    base.mkdir()
    monkeypatch.chdir(base)

    result = runner.invoke(cli, ["migration", "upgrade"])
    assert result.exit_code != 0
