"""
Owner-only filesystem helpers for local NotebookLM state.

The skill stores browser cookies and notebook metadata on disk. Keep those files
readable only by the current OS user whenever the platform supports chmod.
"""

import json
import os
import tempfile
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
    """Atomically replace JSON using an owner-only same-directory temp file."""
    ensure_private_dir(path.parent)
    fd, raw_tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    tmp_path = Path(raw_tmp_path)

    try:
        if os.name != "nt":
            os.fchmod(fd, PRIVATE_FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(tmp_path, path)
        harden_private_file(path)
    finally:
        if fd >= 0:
            os.close(fd)
        tmp_path.unlink(missing_ok=True)
