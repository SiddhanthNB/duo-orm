# duo_orm/migrations/config.py

import importlib
import importlib.resources
import sys
from importlib.util import module_from_spec, spec_from_file_location
import re
from pathlib import Path
from typing import Any, Dict, Tuple, Optional

import toml
from alembic.config import Config

from duo_orm.exceptions import ConfigurationError
from duo_orm.db import Database

DEFAULT_ORM_DIR = "db"
DB_OBJECT_NAME = "db"
DEFAULT_VERSION_TABLE = "alembic_version"
_ENV_VERSION_TABLE_REGEX = re.compile(
    r'version_table\s*=\s*config\.get_main_option\("version_table",\s*"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"\)'
)


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
        raise ConfigurationError("duo_orm_dir must be a relative path within the project.")
    parts = [part for part in rel_path.parts if part not in ("", ".")]
    if not parts:
        parts = [DEFAULT_ORM_DIR]
    for part in parts:
        if not part.isidentifier():
            raise ConfigurationError(
                f"Invalid path segment '{part}' in duo_orm_dir. Use valid Python identifiers."
            )
    return "/".join(parts)


def _slugify_repo_name(path: Path) -> str:
    """Convert a repository directory name to a snake_case-ish slug."""
    name = path.name
    slug = re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_").lower()
    return slug or "duo_orm"


def _normalize_version_table(value: Optional[str], project_root: Path) -> str:
    raw = (value or "").strip()
    if not raw:
        return DEFAULT_VERSION_TABLE
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", raw):
        raise ConfigurationError(
            "version_table must be a valid SQL identifier (letters, digits, underscore, not starting with a digit)."
        )
    return raw


def _detect_version_table_from_env(migrations_dir: Path) -> Optional[str]:
    env_path = migrations_dir / "env.py"
    if not env_path.exists():
        return None
    match = _ENV_VERSION_TABLE_REGEX.search(env_path.read_text())
    if match:
        return match.group("name")
    return None


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
        orm_config = config_data.get("tool", {}).get("duo-orm") or {}
    if raw_dir is None:
        raw_dir = orm_config.get("duo_orm_dir")
    normalized_dir = _normalize_dir(raw_dir)
    orm_config["duo_orm_dir"] = normalized_dir
    orm_config["version_table"] = _normalize_version_table(orm_config.get("version_table"), root)
    return root, orm_config


def _persist_pyproject_config(project_root: Path, relative_dir: str, version_table: Optional[str] = None):
    pyproject_path = project_root / "pyproject.toml"
    data: Dict[str, Any] = {}
    if pyproject_path.exists():
        data = toml.load(pyproject_path)
    tool_section = data.setdefault("tool", {})
    orm_section = tool_section.setdefault("duo-orm", {})
    orm_section["duo_orm_dir"] = relative_dir
    if version_table:
        orm_section["version_table"] = version_table
    pyproject_path.write_text(toml.dumps(data))


def load_template(filename: str) -> str:
    template_path = importlib.resources.files("duo_orm.migrations").joinpath("templates", filename)
    return template_path.read_text()


def _generate_files(base_dir: Path, module_path: str, db_object_name: str, version_table: str):
    """Creates the directories and files for the migration environment."""
    migrations_dir = base_dir / "migrations"
    versions_dir = migrations_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    # 1. Read our internal templates
    template_path = importlib.resources.files("duo_orm.migrations").joinpath(
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
        version_table=version_table,
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
    base_dir, migrations_dir, module_path = _resolve_layout(project_root, user_config["duo_orm_dir"])

    # If the user didn't specify a version_table, try to infer the default from an existing env.py
    if user_config.get("version_table") == DEFAULT_VERSION_TABLE:
        detected = _detect_version_table_from_env(migrations_dir)
        if detected:
            user_config["version_table"] = detected

    # This is the path to the INI file inside the user's project
    config_file_path = str(migrations_dir / "alembic.ini")

    # Ensure project root is importable so db package can be found
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    # Alembic's Config object reads the INI file as a base
    config = Config(config_file_path)

    # Dynamically import the user's configured database object (fresh each time)
    db_object = None
    try:
        module_name = f"{module_path}.database"
        importlib.invalidate_caches()
        if module_name in sys.modules:
            sys.modules.pop(module_name)
        module = importlib.import_module(module_name)
        sys.modules[module_name] = module
        db_object = getattr(module, DB_OBJECT_NAME)
    except (ImportError, AttributeError):
        db_file = base_dir / "database.py"
        module_name = f"{module_path}.database"
        spec = spec_from_file_location(module_name, db_file)
        if spec and spec.loader:
            module = module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
            db_object = getattr(module, DB_OBJECT_NAME, None)

    if not isinstance(db_object, Database):
        raise ConfigurationError(
            f"Could not import Database instance from '{module_path}.database'."
        )

    if not isinstance(db_object, Database):
        raise ConfigurationError(
            f"The object '{DB_OBJECT_NAME}' in '{module_path}.database' is not a duo_orm.Database instance."
        )

    # Programmatically set the URL and metadata for Alembic's environment
    config.set_main_option("sqlalchemy.url", str(db_object.url))
    config.set_main_option("version_table", user_config["version_table"])
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
