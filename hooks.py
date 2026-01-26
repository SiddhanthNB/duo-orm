"""
MkDocs hook to ensure the project root is importable during doc builds.

This helps mkdocstrings locate the `duo_orm` package without relying on the
environment's PYTHONPATH.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping


def on_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    """Add the repository root to sys.path for mkdocstrings imports."""
    repo_root = Path(__file__).parent.resolve()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return config
