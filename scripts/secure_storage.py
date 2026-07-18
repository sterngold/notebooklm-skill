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

    operation_error = None
    operation_traceback = None
    close_error = None
    close_traceback = None
    try:
        if os.name != "nt":
            try:
                os.fchmod(fd, PRIVATE_FILE_MODE)
            except OSError:
                # mkstemp creates an owner-only file on POSIX; fchmod is
                # additional best-effort hardening for supporting filesystems.
                pass
        # Retain ownership of the raw descriptor so a handle.close() failure
        # cannot leak it or force us to guess whether the handle already closed
        # it. The descriptor is closed exactly once below before replacement.
        handle = os.fdopen(fd, "w", encoding="utf-8", closefd=False)
        try:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException as error:
            operation_error = error
            operation_traceback = error.__traceback__

        try:
            handle.close()
        except BaseException as error:
            close_error = error
            close_traceback = error.__traceback__
    except BaseException as error:
        if operation_error is None:
            operation_error = error
            operation_traceback = error.__traceback__

    # Cleanup steps are independent: a failed handle close must not prevent
    # descriptor close, and neither close failure may prevent unlink.
    cleanup_error = close_error
    cleanup_traceback = close_traceback
    if fd >= 0:
        descriptor = fd
        fd = -1
        try:
            os.close(descriptor)
        except BaseException as error:
            if cleanup_error is not None:
                error.__cause__ = cleanup_error.with_traceback(cleanup_traceback)
                error.__suppress_context__ = True
            cleanup_error = error
            cleanup_traceback = error.__traceback__

    if operation_error is None and cleanup_error is None:
        try:
            os.replace(tmp_path, path)
            harden_private_file(path)
        except BaseException as error:
            operation_error = error
            operation_traceback = error.__traceback__

    try:
        tmp_path.unlink(missing_ok=True)
    except BaseException as error:
        if cleanup_error is not None:
            error.__cause__ = cleanup_error.with_traceback(cleanup_traceback)
            error.__suppress_context__ = True
        cleanup_error = error
        cleanup_traceback = error.__traceback__

    if operation_error is not None:
        if cleanup_error is not None:
            # Preserve the operation failure as top-level while retaining every
            # cleanup failure in its explicit cause chain.
            raise operation_error.with_traceback(operation_traceback) from cleanup_error
        raise operation_error.with_traceback(operation_traceback)

    if cleanup_error is not None:
        raise cleanup_error.with_traceback(cleanup_traceback)
