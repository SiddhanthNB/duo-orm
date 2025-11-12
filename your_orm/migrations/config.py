# your_orm/migrations/config.py

import importlib
import importlib.resources
from pathlib import Path
from typing import Any, Dict, Tuple, Optional

import toml
from alembic.config import Config

from your_orm.exceptions import ConfigurationError

DEFAULT_ORM_DIR = "db"
DB_OBJECT_NAME = "db"


def _get_project_root() -> Path:
    """Finds the project root by looking for pyproject.toml."""
    current_dir = Path.cwd()
    for parent in [current_dir] + list(current_dir.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    raise FileNotFoundError("Could not find project root (pyproject.toml).")


def _normalize_dir(value: str | None) -> str:
    raw = (value or DEFAULT_ORM_DIR).strip()
    if not raw or raw == ".":
        raw = DEFAULT_ORM_DIR
    rel_path = Path(raw)
    if rel_path.is_absolute():
        raise ConfigurationError("your_orm_dir must be a relative path within the project.")
    parts = [part for part in rel_path.parts if part not in ("", ".")]
    if not parts:
        parts = [DEFAULT_ORM_DIR]
    for part in parts:
        if not part.isidentifier():
            raise ConfigurationError(
                f"Invalid path segment '{part}' in your_orm_dir. Use valid Python identifiers."
            )
    return "/".join(parts)


def _resolve_layout(project_root: Path, relative_dir: str) -> Tuple[Path, Path, str]:
    rel_path = Path(relative_dir)
    base_dir = (project_root / rel_path).resolve()
    module_path = relative_dir.replace("/", ".")
    migrations_dir = base_dir / "migrations"
    return base_dir, migrations_dir, module_path


def _get_config(found_root: Optional[Path] = None, override_dir: Optional[str] = None) -> Tuple[Path, Dict[str, Any]]:
    """
    Finds and parses the user's configuration from pyproject.toml, with optional
    overrides from CLI flags/env vars.
    """
    root = found_root
    raw_dir = override_dir
    if root is None:
        try:
            root = _get_project_root()
        except FileNotFoundError:
            root = Path.cwd()
    pyproject_path = root / "pyproject.toml"
    orm_config: Dict[str, Any] = {}
    if pyproject_path.exists():
        config_data = toml.load(pyproject_path)
        orm_config = config_data.get("tool", {}).get("your-orm") or {}
    if raw_dir is None:
        raw_dir = orm_config.get("your_orm_dir")
    normalized_dir = _normalize_dir(raw_dir)
    orm_config["your_orm_dir"] = normalized_dir
    return root, orm_config


def _persist_pyproject_config(project_root: Path, relative_dir: str):
    pyproject_path = project_root / "pyproject.toml"
    data: Dict[str, Any] = {}
    if pyproject_path.exists():
        data = toml.load(pyproject_path)
    tool_section = data.setdefault("tool", {})
    tool_section["your-orm"] = {"your_orm_dir": relative_dir}
    pyproject_path.write_text(toml.dumps(data))


def load_template(filename: str) -> str:
    template_path = importlib.resources.files("your_orm.migrations").joinpath("templates", filename)
    return template_path.read_text()


def _generate_files(base_dir: Path, module_path: str, db_object_name: str):
    """Creates the directories and files for the migration environment."""
    migrations_dir = base_dir / "migrations"
    versions_dir = migrations_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    # 1. Read our internal templates
    template_path = importlib.resources.files("your_orm.migrations").joinpath(
        "templates"
    )
    ini_template = (template_path / "alembic.ini.tpl").read_text()
    env_template = (template_path / "env.py.tpl").read_text()

    # 2. Write the managed alembic.ini
    (migrations_dir / "alembic.ini").write_text(ini_template)

    # 3. Customize and write the smart env.py
    env_py_content = env_template.format(
        db_object_module=f"{module_path}.database",
        db_object_name=db_object_name,
    )
    (migrations_dir / "env.py").write_text(env_py_content)

    # 4. Copy the script.py.mako template from the installed Alembic package
    try:
        mako_content = (
            importlib.resources.files("alembic")
            .joinpath("templates/generic/script.py.mako")
            .read_text()
        )
        (migrations_dir / "script.py.mako").write_text(mako_content)
    except (ImportError, AttributeError):
        # This is a fallback and should rarely happen.
        raise RuntimeError("Could not locate the alembic package to copy templates.")


def get_alembic_config(override_dir: Optional[str] = None) -> Config:
    """
    Creates a complete Alembic Config object programmatically.
    This is used by all CLI commands to run Alembic.
    """
    project_root, user_config = _get_config(override_dir=override_dir)
    base_dir, migrations_dir, module_path = _resolve_layout(project_root, user_config["your_orm_dir"])

    # This is the path to the INI file inside the user's project
    config_file_path = str(migrations_dir / "alembic.ini")

    # Alembic's Config object reads the INI file as a base
    config = Config(config_file_path)

    # Dynamically import the user's configured database object
    try:
        module = importlib.import_module(f"{module_path}.database")
        db_object = getattr(module, DB_OBJECT_NAME)
    except (ImportError, AttributeError) as exc:
        raise ConfigurationError(
            f"Could not import Database instance from '{module_path}.database'."
        ) from exc

    # Programmatically set the URL and metadata for Alembic's environment
    config.set_main_option("sqlalchemy.url", str(db_object.url))
    config.attributes["target_metadata"] = db_object.metadata

    return config


__all__ = [
    "_get_config",
    "_generate_files",
    "_resolve_layout",
    "_persist_pyproject_config",
    "get_alembic_config",
    "DEFAULT_ORM_DIR",
    "DB_OBJECT_NAME",
]
