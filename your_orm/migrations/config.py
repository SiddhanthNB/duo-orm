# your_orm/migrations/config.py

import importlib
import importlib.resources
from pathlib import Path
from typing import Any, Dict, Tuple

import toml
from alembic.config import Config

from your_orm.exceptions import ConfigurationError


def _get_project_root() -> Path:
    """Finds the project root by looking for pyproject.toml."""
    current_dir = Path.cwd()
    for parent in [current_dir] + list(current_dir.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    raise FileNotFoundError("Could not find project root (pyproject.toml).")


def _get_config() -> Tuple[Path, Dict[str, Any]]:
    """
    Finds and parses the user's configuration from pyproject.toml.
    """
    try:
        root = _get_project_root()
        pyproject_path = root / "pyproject.toml"
        config_data = toml.load(pyproject_path)
        orm_config = config_data.get("tool", {}).get("your-orm")

        if not orm_config:
            raise ConfigurationError(
                "Configuration for 'your-orm' not found in pyproject.toml under [tool.your-orm]."
            )

        # Validate required keys
        required_keys = ["migrations_dir", "db_object_path"]
        for key in required_keys:
            if key not in orm_config:
                raise ConfigurationError(f"Missing required config key: '{key}'")

        return root, orm_config
    except FileNotFoundError:
        raise ConfigurationError(
            "pyproject.toml not found in the current directory or any parent directories."
        )


def _generate_files(migrations_dir: Path, db_object_path: str):
    """Creates the directories and files for the migration environment."""
    versions_dir = migrations_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    # 1. Read our internal templates
    template_path = importlib.resources.files("your_orm.migrations").joinpath(
        "templates"
    )
    ini_template = (template_path / "alembic.ini.tpl").read_text()
    env_template = (template_path / "env.py.tpl").read_text()

    try:
        module_path, obj_name = db_object_path.rsplit(".", 1)
    except ValueError as exc:
        raise ConfigurationError(
            "db_object_path must include a module and attribute (e.g. 'my_app.database.db')."
        ) from exc

    # 2. Write the managed alembic.ini
    (migrations_dir / "alembic.ini").write_text(ini_template)

    # 3. Customize and write the smart env.py
    env_py_content = env_template.format(
        db_object_module=module_path,
        db_object_name=obj_name,
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


def get_alembic_config() -> Config:
    """
    Creates a complete Alembic Config object programmatically.
    This is used by all CLI commands to run Alembic.
    """
    project_root, user_config = _get_config()
    migrations_dir = (project_root / user_config["migrations_dir"]).resolve()
    db_object_path = user_config["db_object_path"]

    # This is the path to the INI file inside the user's project
    config_file_path = str(migrations_dir / "alembic.ini")
    
    # Alembic's Config object reads the INI file as a base
    config = Config(config_file_path)

    # Dynamically import the user's configured database object
    try:
        module_path, obj_name = db_object_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        db_object = getattr(module, obj_name)
    except (ImportError, AttributeError):
        raise ConfigurationError(
            f"Could not import 'db_object_path': '{db_object_path}'"
        )
    
    # Programmatically set the URL and metadata for Alembic's environment
    config.set_main_option("sqlalchemy.url", str(db_object.url))
    config.attributes["target_metadata"] = db_object.metadata

    return config
