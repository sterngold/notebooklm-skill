import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from secure_storage import ensure_private_dir, harden_private_file, write_private_json


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def temp_files(parent: Path, name: str) -> list[Path]:
    candidates = {parent / f".{name}.tmp", *parent.glob(f".{name}.*.tmp")}
    return sorted(path for path in candidates if path.exists())


def traceback_functions(error: BaseException) -> list[str]:
    functions = []
    current = error.__traceback__
    while current is not None:
        functions.append(current.tb_frame.f_code.co_name)
        current = current.tb_next
    return functions


class SecureStorageTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX file mode checks do not apply on Windows")
    def test_ensure_private_dir_creates_directory_with_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"

            ensure_private_dir(data_dir)

            self.assertTrue(data_dir.is_dir())
            self.assertEqual(mode(data_dir), 0o700)

    @unittest.skipIf(os.name == "nt", "POSIX file mode checks do not apply on Windows")
    def test_write_private_json_creates_owner_only_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "browser_state" / "state.json"

            write_private_json(state_file, {"cookies": [{"name": "session"}]})

            self.assertEqual(mode(state_file.parent), 0o700)
            self.assertEqual(mode(state_file), 0o600)
            self.assertEqual(json.loads(state_file.read_text()), {"cookies": [{"name": "session"}]})

    def test_serialization_failure_preserves_destination_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"old": true}\n')

            with self.assertRaises(TypeError):
                write_private_json(path, {"bad": object()})

            self.assertEqual(json.loads(path.read_text()), {"old": True})
            self.assertEqual(temp_files(path.parent, path.name), [])

    def test_replace_failure_preserves_destination_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"old": true}\n')

            with patch("secure_storage.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_private_json(path, {"new": True})

            self.assertEqual(json.loads(path.read_text()), {"old": True})
            self.assertEqual(temp_files(path.parent, path.name), [])

    def test_replace_uses_a_temp_file_in_the_destination_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            sources = []
            real_replace = os.replace

            def capture_replace(source, destination):
                sources.append(Path(source))
                real_replace(source, destination)

            with patch("secure_storage.os.replace", side_effect=capture_replace):
                write_private_json(path, {"value": 1})

            self.assertEqual(sources[0].parent, path.parent)

    def test_sequential_writes_use_distinct_temp_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            sources = []
            real_replace = os.replace

            def capture_replace(source, destination):
                sources.append(Path(source))
                real_replace(source, destination)

            with patch("secure_storage.os.replace", side_effect=capture_replace):
                write_private_json(path, {"value": 1})
                write_private_json(path, {"value": 2})

            self.assertEqual(len(set(sources)), 2)
            self.assertEqual(json.loads(path.read_text()), {"value": 2})

    def test_unlink_is_attempted_after_descriptor_close_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"old": true}\n')
            descriptors = []
            unlink_calls = []
            real_mkstemp = tempfile.mkstemp
            real_close = os.close
            real_unlink = Path.unlink

            def capture_mkstemp(*args, **kwargs):
                descriptor, tmp_path = real_mkstemp(*args, **kwargs)
                descriptors.append(descriptor)
                return descriptor, tmp_path

            def close_then_fail(descriptor):
                real_close(descriptor)
                raise OSError("close failed")

            def record_unlink(tmp_path, *, missing_ok=False):
                unlink_calls.append(tmp_path)
                return real_unlink(tmp_path, missing_ok=missing_ok)

            with patch("secure_storage.tempfile.mkstemp", side_effect=capture_mkstemp):
                with patch("secure_storage.os.fdopen", side_effect=OSError("open failed")):
                    with patch("secure_storage.os.close", side_effect=close_then_fail):
                        with patch.object(Path, "unlink", autospec=True, side_effect=record_unlink):
                            with self.assertRaises(OSError):
                                write_private_json(path, {"new": True})

            self.assertEqual(len(unlink_calls), 1)
            with self.assertRaises(OSError):
                os.fstat(descriptors[0])
            self.assertEqual(temp_files(path.parent, path.name), [])

    def test_primary_error_stays_top_level_when_close_and_unlink_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"old": true}\n')
            descriptors = []
            real_mkstemp = tempfile.mkstemp
            real_close = os.close
            real_unlink = Path.unlink
            primary_error = OSError("open failed")
            close_error = OSError("close failed")
            unlink_error = OSError("unlink failed")

            def capture_mkstemp(*args, **kwargs):
                descriptor, tmp_path = real_mkstemp(*args, **kwargs)
                descriptors.append(descriptor)
                return descriptor, tmp_path

            def close_then_fail(descriptor):
                real_close(descriptor)
                raise close_error

            def unlink_then_fail(tmp_path, *, missing_ok=False):
                real_unlink(tmp_path, missing_ok=missing_ok)
                # Cleanup continues after close fails; preserve the traceback
                # captured at the close site even if the exception is touched.
                close_error.__traceback__ = None
                raise unlink_error

            with patch("secure_storage.tempfile.mkstemp", side_effect=capture_mkstemp):
                with patch("secure_storage.os.fdopen", side_effect=primary_error):
                    with patch("secure_storage.os.close", side_effect=close_then_fail):
                        with patch.object(
                            Path, "unlink", autospec=True, side_effect=unlink_then_fail
                        ):
                            try:
                                write_private_json(path, {"new": True})
                            except OSError as raised_error:
                                caught_error = raised_error
                                unlink_traceback = traceback_functions(unlink_error)
                                close_traceback = traceback_functions(close_error)
                            else:
                                self.fail("write_private_json did not raise")

            self.assertIs(caught_error, primary_error)
            self.assertIs(caught_error.__cause__, unlink_error)
            self.assertIs(unlink_error.__cause__, close_error)
            self.assertEqual(unlink_traceback[-1], "unlink_then_fail")
            self.assertEqual(close_traceback[-1], "close_then_fail")
            with self.assertRaises(OSError):
                os.fstat(descriptors[0])
            self.assertEqual(json.loads(path.read_text()), {"old": True})
            self.assertEqual(temp_files(path.parent, path.name), [])

    def test_serialization_error_stays_top_level_when_unlink_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"old": true}\n')
            descriptors = []
            real_mkstemp = tempfile.mkstemp
            real_unlink = Path.unlink
            primary_error = TypeError("serialization failed")
            unlink_error = OSError("unlink failed")

            def capture_mkstemp(*args, **kwargs):
                descriptor, tmp_path = real_mkstemp(*args, **kwargs)
                descriptors.append(descriptor)
                return descriptor, tmp_path

            def unlink_then_fail(tmp_path, *, missing_ok=False):
                real_unlink(tmp_path, missing_ok=missing_ok)
                raise unlink_error

            with patch("secure_storage.tempfile.mkstemp", side_effect=capture_mkstemp):
                with patch("secure_storage.json.dump", side_effect=primary_error):
                    with patch.object(Path, "unlink", autospec=True, side_effect=unlink_then_fail):
                        with self.assertRaises(TypeError) as raised:
                            write_private_json(path, {"new": True})

            self.assertIs(raised.exception, primary_error)
            self.assertIs(raised.exception.__cause__, unlink_error)
            with self.assertRaises(OSError):
                os.fstat(descriptors[0])
            self.assertEqual(json.loads(path.read_text()), {"old": True})
            self.assertEqual(temp_files(path.parent, path.name), [])

    def test_serialization_error_stays_top_level_for_handle_close_failures(self):
        class CloseFailingHandle:
            def __init__(self, handle, close_error, *, close_first):
                self.handle = handle
                self.close_error = close_error
                self.close_first = close_first

            def __enter__(self):
                self.handle.__enter__()
                return self

            def __exit__(self, *args):
                if self.close_first:
                    self.handle.__exit__(*args)
                raise self.close_error

            def close(self):
                if self.close_first:
                    self.handle.close()
                raise self.close_error

            def write(self, data):
                return self.handle.write(data)

            def flush(self):
                return self.handle.flush()

            def fileno(self):
                return self.handle.fileno()

        for close_first in (False, True):
            with self.subTest(close_first=close_first):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "state.json"
                    path.write_text('{"old": true}\n')
                    descriptors = []
                    opened_handles = []
                    real_mkstemp = tempfile.mkstemp
                    real_fdopen = os.fdopen
                    real_close = os.close
                    close_calls = []
                    primary_error = TypeError("serialization failed")
                    close_error = OSError("close failed")

                    def capture_mkstemp(*args, **kwargs):
                        descriptor, tmp_path = real_mkstemp(*args, **kwargs)
                        descriptors.append(descriptor)
                        return descriptor, tmp_path

                    def close_failing_fdopen(*args, **kwargs):
                        wrapped = CloseFailingHandle(
                            real_fdopen(*args, **kwargs),
                            close_error,
                            close_first=close_first,
                        )
                        opened_handles.append(wrapped)
                        return wrapped

                    def fail_serialization(*_args, **_kwargs):
                        raise primary_error

                    def record_close(descriptor):
                        close_calls.append(descriptor)
                        real_close(descriptor)

                    try:
                        with patch("secure_storage.tempfile.mkstemp", side_effect=capture_mkstemp):
                            with patch(
                                "secure_storage.os.fdopen",
                                side_effect=close_failing_fdopen,
                            ):
                                with patch("secure_storage.os.close", side_effect=record_close):
                                    with patch(
                                        "secure_storage.json.dump",
                                        side_effect=fail_serialization,
                                    ):
                                        try:
                                            write_private_json(path, {"new": True})
                                        except TypeError as raised_error:
                                            caught_error = raised_error
                                            primary_traceback = traceback_functions(primary_error)
                                            close_traceback = traceback_functions(close_error)
                                        else:
                                            self.fail("write_private_json did not raise")

                        self.assertIs(caught_error, primary_error)
                        self.assertIs(caught_error.__cause__, close_error)
                        self.assertEqual(primary_traceback[-1], "fail_serialization")
                        self.assertEqual(close_traceback[-1], "close")
                        self.assertEqual(close_calls, descriptors)
                        with self.assertRaises(OSError):
                            os.fstat(descriptors[0])
                        self.assertEqual(json.loads(path.read_text()), {"old": True})
                        self.assertEqual(temp_files(path.parent, path.name), [])
                    finally:
                        for opened_handle in opened_handles:
                            try:
                                opened_handle.handle.close()
                            except OSError:
                                pass
                        for descriptor in descriptors:
                            try:
                                real_close(descriptor)
                            except OSError:
                                pass

    def test_cleanup_only_unlink_error_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            cleanup_error = OSError("unlink failed")

            def unlink_then_fail(*_args, **_kwargs):
                raise cleanup_error

            with patch.object(Path, "unlink", autospec=True, side_effect=unlink_then_fail):
                try:
                    write_private_json(path, {"new": True})
                except OSError as raised_error:
                    caught_error = raised_error
                    cleanup_traceback = traceback_functions(cleanup_error)
                else:
                    self.fail("write_private_json did not raise")

            self.assertIs(caught_error, cleanup_error)
            self.assertEqual(cleanup_traceback[-1], "unlink_then_fail")
            self.assertEqual(json.loads(path.read_text()), {"new": True})

    @unittest.skipIf(os.name == "nt", "os.fchmod is unavailable on Windows")
    def test_fchmod_failure_still_persists_owner_only_json_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"old": true}\n')
            temp_modes = []
            real_replace = os.replace

            def capture_replace(source, destination):
                temp_modes.append(mode(Path(source)))
                real_replace(source, destination)

            with patch("secure_storage.os.fchmod", side_effect=OSError("chmod failed")):
                with patch("secure_storage.os.replace", side_effect=capture_replace):
                    write_private_json(path, {"new": True})

            # mkstemp itself supplies the non-permissive baseline; fchmod is an
            # additional best-effort hardening step for supporting filesystems.
            self.assertEqual(temp_modes, [0o600])
            self.assertEqual(mode(path), 0o600)
            self.assertEqual(json.loads(path.read_text()), {"new": True})
            self.assertEqual(temp_files(path.parent, path.name), [])

    def test_fdopen_failure_closes_descriptor_preserves_destination_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"old": true}\n')
            descriptors = []
            real_mkstemp = tempfile.mkstemp

            def capture_mkstemp(*args, **kwargs):
                descriptor, tmp_path = real_mkstemp(*args, **kwargs)
                descriptors.append(descriptor)
                return descriptor, tmp_path

            with patch("secure_storage.tempfile.mkstemp", side_effect=capture_mkstemp):
                with patch("secure_storage.os.fdopen", side_effect=OSError("open failed")):
                    with self.assertRaisesRegex(OSError, "open failed"):
                        write_private_json(path, {"new": True})

            with self.assertRaises(OSError):
                os.fstat(descriptors[0])
            self.assertEqual(json.loads(path.read_text()), {"old": True})
            self.assertEqual(temp_files(path.parent, path.name), [])

    def test_flush_failure_preserves_destination_and_cleans_temp(self):
        class FlushFailingHandle:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                self.handle.__enter__()
                return self

            def __exit__(self, *args):
                return self.handle.__exit__(*args)

            def close(self):
                return self.handle.close()

            def write(self, data):
                return self.handle.write(data)

            def flush(self):
                raise OSError("flush failed")

            def fileno(self):
                return self.handle.fileno()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"old": true}\n')
            real_fdopen = os.fdopen

            with patch(
                "secure_storage.os.fdopen",
                side_effect=lambda *args, **kwargs: FlushFailingHandle(
                    real_fdopen(*args, **kwargs)
                ),
            ):
                with self.assertRaisesRegex(OSError, "flush failed"):
                    write_private_json(path, {"new": True})

            self.assertEqual(json.loads(path.read_text()), {"old": True})
            self.assertEqual(temp_files(path.parent, path.name), [])

    def test_fsync_failure_preserves_destination_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"old": true}\n')

            with patch("secure_storage.os.fsync", side_effect=OSError("fsync failed")):
                with self.assertRaisesRegex(OSError, "fsync failed"):
                    write_private_json(path, {"new": True})

            self.assertEqual(json.loads(path.read_text()), {"old": True})
            self.assertEqual(temp_files(path.parent, path.name), [])

    @unittest.skipIf(os.name == "nt", "POSIX file mode checks do not apply on Windows")
    def test_harden_private_file_tightens_existing_file_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text("{}")
            state_file.chmod(0o644)

            harden_private_file(state_file)

            self.assertEqual(mode(state_file), 0o600)


if __name__ == "__main__":
    unittest.main()
