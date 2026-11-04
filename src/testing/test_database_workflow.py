"""Regression checks for database deletion, autosave and the export constraint gate."""
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.gui.app import ModelDeepenerApp
from src.object_database.folder import DatabaseFolder
from src.object_database.persistent import Persistent


class DatabaseWorkflowTests(unittest.TestCase):
    """Checks how the application works with its database."""

    def test_missing_legacy_classes_are_not_reported_as_file_corruption(self) -> None:
        """Check that missing legacy classes are not reported as file corruption."""
        with tempfile.TemporaryDirectory() as directory:
            folder = DatabaseFolder(directory)
            folder.create_database("Legacy")
            with patch("src.object_database.folder.Database",
                       side_effect=ModuleNotFoundError("old_model_module")):
                with self.assertRaisesRegex(ValueError, "not compatible with this version"):
                    folder.open_database("Legacy")
            self.assertEqual(folder.get_names(), ["Legacy"])

    def test_cancel_after_active_deletion_offers_application_shutdown(self) -> None:
        """Check that cancel after active deletion offers application shutdown."""
        ui = SimpleNamespace(
            _database=None, _active_database_deleted=True,
            _database_folder=Mock(), _overlay=Mock(), _is_closing=False,
            _close_application=Mock(),
        )
        with patch("src.gui.app.ask_for_database", return_value=None), patch(
                "src.gui.app.popup_message", return_value=False) as prompt:
            self.assertFalse(ModelDeepenerApp._choose_database(ui, is_startup=False))
            ui._close_application.assert_called_once()
            self.assertEqual(prompt.call_args.kwargs["cancel_text"], "Close application")

    def test_delete_removes_only_selected_database_and_rejects_paths(self) -> None:
        """Check that delete removes only selected database and rejects paths."""
        with tempfile.TemporaryDirectory() as directory:
            folder = DatabaseFolder(directory)
            folder.create_database("Keep")
            folder.create_database("Delete")
            with self.assertRaises(KeyError):
                folder.delete_database("../Keep")
            folder.delete_database("Delete")
            self.assertEqual(folder.get_names(), ["Keep"])

    def test_autosave_preserves_invalid_intermediate_state(self) -> None:
        """Check that autosave preserves invalid intermediate state."""
        with tempfile.TemporaryDirectory() as directory:
            folder = DatabaseFolder(directory)
            database = folder.create_database("Work")
            model = Persistent()
            model.violations = ["Unfinished classification"]
            database.store(model)
            ui = SimpleNamespace(_database=database, _is_closing=False, after=Mock(),
                                 _autosave_models=Mock())
            ModelDeepenerApp._autosave_models(ui)
            model.violations.append("Unfinished association")
            ModelDeepenerApp._autosave_models(ui)
            restored = folder.open_database("Work").get_all()[0]
            self.assertEqual(restored.violations, model.violations)
            with unittest.mock.patch.object(database, "commit") as commit:
                ModelDeepenerApp._autosave_models(ui)
                commit.assert_not_called()

    def test_autosave_does_not_recreate_deleted_active_database(self) -> None:
        """Check that autosave does not recreate deleted active database."""
        ui = SimpleNamespace(_database=None, _is_closing=False, after=Mock(),
                             _autosave_models=Mock())
        ModelDeepenerApp._autosave_models(ui)
        ui.after.assert_called_once()

    def test_only_valid_models_can_be_exported(self) -> None:
        """Check that only valid models can be exported."""
        for violations in ([], ["Invalid classification"]):
            with self.subTest(violations=violations):
                model = Mock()
                model.validate_basemlm_integrity.return_value = violations
                ui = SimpleNamespace(
                    current_model=model, current_file_type="XML", current_file_path=None,
                    _show_warning=Mock(), _export_current_xml_model=Mock(),
                )
                ModelDeepenerApp._export_current_model_placeholder(ui)
                self.assertEqual(ui._export_current_xml_model.call_count, int(not violations))
                self.assertEqual(ui._show_warning.call_count, int(bool(violations)))


if __name__ == "__main__":
    unittest.main()
