from unittest.mock import Mock, patch

from auth_manager import AuthManager


def test_save_browser_state_uses_private_atomic_writer(tmp_path):
    manager = AuthManager.__new__(AuthManager)
    manager.state_file = tmp_path / "state.json"
    context = Mock()
    state = {"cookies": [], "origins": []}
    context.storage_state.return_value = state

    with patch("auth_manager.write_private_json") as writer:
        manager._save_browser_state(context)

    context.storage_state.assert_called_once_with()
    writer.assert_called_once_with(manager.state_file, state)
