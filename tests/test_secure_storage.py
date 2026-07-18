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
    return list(parent.glob(f".{name}.*.tmp"))


@unittest.skipIf(os.name == "nt", "POSIX file mode checks do not apply on Windows")
class SecureStorageTests(unittest.TestCase):
    def test_ensure_private_dir_creates_directory_with_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"

            ensure_private_dir(data_dir)

            self.assertTrue(data_dir.is_dir())
            self.assertEqual(mode(data_dir), 0o700)

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

    def test_harden_private_file_tightens_existing_file_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text("{}")
            state_file.chmod(0o644)

            harden_private_file(state_file)

            self.assertEqual(mode(state_file), 0o600)


if __name__ == "__main__":
    unittest.main()
