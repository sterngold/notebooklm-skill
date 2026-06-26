import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from secure_storage import ensure_private_dir, harden_private_file, write_private_json


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


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

    def test_harden_private_file_tightens_existing_file_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text("{}")
            state_file.chmod(0o644)

            harden_private_file(state_file)

            self.assertEqual(mode(state_file), 0o600)


if __name__ == "__main__":
    unittest.main()
