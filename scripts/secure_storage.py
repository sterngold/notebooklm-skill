"""
Owner-only filesystem helpers for local NotebookLM state.

The skill stores browser cookies and notebook metadata on disk. Keep those files
readable only by the current OS user whenever the platform supports chmod.
"""

import json
import os
from pathlib import Path
from typing import Any

PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def _chmod(path: Path, mode: int) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(mode)
    except OSError:
        # Best-effort hardening: writing should not fail on filesystems that
        # reject chmod, but the caller can still inspect the path.
        pass


def ensure_private_dir(path: Path) -> Path:
    """Create a directory and restrict it to the current OS user."""
    path.mkdir(parents=True, exist_ok=True)
    _chmod(path, PRIVATE_DIR_MODE)
    return path


def harden_private_file(path: Path) -> Path:
    """Restrict an existing file to the current OS user."""
    if path.exists():
        _chmod(path, PRIVATE_FILE_MODE)
    return path


def write_private_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically-ish with owner-only file permissions."""
    ensure_private_dir(path.parent)
    tmp_path = path.with_name(f".{path.name}.tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    _chmod(tmp_path, PRIVATE_FILE_MODE)
    tmp_path.replace(path)
    harden_private_file(path)
