from __future__ import annotations

import toml
from pathlib import Path

import pytest

from your_orm.migrations.config import get_alembic_config, DB_OBJECT_NAME, _get_config, _persist_pyproject_config
from your_orm.exceptions import ConfigurationError


def _write_pyproject(root: Path, your_orm_dir: str = "db"):
    (root / "pyproject.toml").write_text(toml.dumps({"tool": {"your-orm": {"your_orm_dir": your_orm_dir}}}))


def test_missing_db_object_raises_configuration_error(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    _write_pyproject(project)

    db_dir = project / "db"
    db_dir.mkdir()
    (db_dir / "__init__.py").write_text("")
    (db_dir / "database.py").write_text("# no db object here\n")

    monkeypatch.chdir(project)
    monkeypatch.syspath_prepend(str(project))

    with pytest.raises(ConfigurationError):
        get_alembic_config()


def test_invalid_db_object_type_raises_configuration_error(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    _write_pyproject(project)

    db_dir = project / "db"
    db_dir.mkdir()
    (db_dir / "__init__.py").write_text("")
    (db_dir / "database.py").write_text(f"{DB_OBJECT_NAME} = 123\n")

    monkeypatch.chdir(project)
    monkeypatch.syspath_prepend(str(project))

    with pytest.raises(ConfigurationError):
        get_alembic_config()


def test_version_table_defaults_to_repo_name(tmp_path, monkeypatch):
    project = tmp_path / "my-fancy_repo"
    project.mkdir()
    _write_pyproject(project)

    db_dir = project / "db"
    db_dir.mkdir()
    (db_dir / "__init__.py").write_text("")
    (db_dir / "database.py").write_text(
        "from your_orm import Database\n"
        f"db = Database('sqlite:///{project / 'default.sqlite'}')\n"
    )

    monkeypatch.chdir(project)
    monkeypatch.syspath_prepend(str(project))

    _, config = _get_config()
    assert config["version_table"] == "alembic_version"

    cfg = get_alembic_config()
    assert cfg.get_main_option("version_table") == "alembic_version"


def test_version_table_can_be_overridden_in_pyproject(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        toml.dumps({"tool": {"your-orm": {"your_orm_dir": "db", "version_table": "custom_table"}}})
    )

    db_dir = project / "db"
    db_dir.mkdir()
    (db_dir / "__init__.py").write_text("")
    (db_dir / "database.py").write_text(
        "from your_orm import Database\n"
        f"db = Database('sqlite:///{project / 'override.sqlite'}')\n"
    )

    monkeypatch.chdir(project)
    monkeypatch.syspath_prepend(str(project))

    cfg = get_alembic_config()
    assert cfg.get_main_option("version_table") == "custom_table"


def test_persist_pyproject_preserves_version_table(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    pyproject = project / "pyproject.toml"
    pyproject.write_text(toml.dumps({"tool": {"your-orm": {"version_table": "keep_me"}}}))

    _persist_pyproject_config(project, "db/path", "keep_me")
    loaded = toml.load(pyproject)
    assert loaded["tool"]["your-orm"]["your_orm_dir"] == "db/path"
    assert loaded["tool"]["your-orm"]["version_table"] == "keep_me"
