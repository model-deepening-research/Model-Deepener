"""Regression checks for database deletion, autosave and the export constraint gate."""
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.gui.app import ModelDeepenerApp
from src.object_database.folder import DatabaseFolder
from src.object_database.persistent import Persistent


class DatabaseWorkflowTests(unittest.TestCase):
    """Checks how the application works with its database."""

    def test_missing_legacy_classes_are_not_reported_as_file_corruption(self) -> None:
        """Report an unavailable legacy class as incompatibility while keeping the database file listed."""
        with tempfile.TemporaryDirectory() as directory:
            folder = DatabaseFolder(directory)
            folder.create_database("Legacy")
            with patch("src.object_database.folder.Database",
                       side_effect=ModuleNotFoundError("old_model_module")):
                with self.assertRaisesRegex(ValueError, "not compatible with this version"):
                    folder.open_database("Legacy")
            self.assertEqual(folder.get_names(), ["Legacy"])

    def test_cancel_after_active_deletion_offers_application_shutdown(self) -> None:
        """Offer shutdown when database selection is cancelled after deleting the active database."""
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

    def test_failed_background_save_keeps_application_and_database_open(self) -> None:
        """Check failed background save keeps application and database open."""
        def run(_total, _message, work, success, failed):
            try:
                success(work(lambda *_: None))
            except OSError as error:
                failed(error)
        database = SimpleNamespace(commit=Mock(side_effect=OSError("disk full")))
        ui = SimpleNamespace(_database=database, _run_model_task=run, _choose_database=Mock(),
                             _show_error=Mock(), _is_closing=False, _model_task_active=False,
                             _autosave_in_progress=False, _finish_close=Mock())
        ModelDeepenerApp._switch_database(ui)
        ui._choose_database.assert_not_called()
        ui._show_error.assert_called_once()
        with patch("src.gui.app.popup_message", return_value=False):
            ModelDeepenerApp._close_application(ui)
        ui._finish_close.assert_not_called()

    def test_delete_removes_only_selected_database_and_rejects_paths(self) -> None:
        """Delete only the named database and reject an attempted relative path."""
        with tempfile.TemporaryDirectory() as directory:
            folder = DatabaseFolder(directory)
            folder.create_database("Keep")
            folder.create_database("Delete")
            with self.assertRaises(KeyError):
                folder.delete_database("../Keep")
            folder.delete_database("Delete")
            self.assertEqual(folder.get_names(), ["Keep"])

    def test_autosave_preserves_invalid_intermediate_state(self) -> None:
        """Save changed state and avoid another write when it stays unchanged."""
        with tempfile.TemporaryDirectory() as directory:
            folder = DatabaseFolder(directory)
            database = folder.create_database("Work")
            self.assertFalse(database.save_if_changed())
            model = Persistent()
            model.violations = ["Unfinished classification"]
            database.store(model)
            self.assertTrue(database.save_if_changed())
            model.violations.append("Unfinished association")
            self.assertTrue(database.save_if_changed())
            restored = folder.open_database("Work").get_all()[0]
            self.assertEqual(restored.violations, model.violations)
            self.assertFalse(database.save_if_changed())

    def test_outdated_background_snapshot_cannot_overwrite_newer_commit(self) -> None:
        """Check outdated background snapshot cannot overwrite newer commit."""
        with tempfile.TemporaryDirectory() as directory:
            folder = DatabaseFolder(directory)
            database = folder.create_database("Work")
            model = Persistent()
            model.value = "first"
            database.store(model)
            database.commit()
            model.value = "background"
            serialized = threading.Event()
            release = threading.Event()
            main_thread = threading.get_ident()
            original = database._storage.serialize
            def slow_serialize(data):
                encoded = original(data)
                if threading.get_ident() != main_thread:
                    serialized.set()
                    self.assertTrue(release.wait(5))
                return encoded
            result = []
            with patch.object(database._storage, "serialize", side_effect=slow_serialize):
                thread = threading.Thread(target=lambda: result.append(database.save_if_changed()))
                thread.start()
                self.assertTrue(serialized.wait(5))
                model.value = "newer"
                database.commit()
                release.set()
                thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result, [False])
            self.assertEqual(folder.open_database("Work").get_all()[0].value, "newer")

    def test_failed_autosave_retries_without_advancing_saved_digest(self) -> None:
        """Check failed autosave retries without advancing saved digest."""
        with tempfile.TemporaryDirectory() as directory:
            database = DatabaseFolder(directory).create_database("Work")
            model = Persistent()
            database.store(model)
            with patch.object(database._storage, "save_serialized", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    database.save_if_changed()
            self.assertTrue(database.save_if_changed())
            self.assertFalse(database.save_if_changed())

    def test_autosave_does_not_recreate_deleted_active_database(self) -> None:
        """Schedule the next autosave without writing when no active database remains."""
        ui = SimpleNamespace(_database=None, _is_closing=False, after=Mock(),
                             _autosave_models=Mock())
        ModelDeepenerApp._autosave_models(ui)
        ui.after.assert_called_once()

    def test_only_valid_models_can_be_exported(self) -> None:
        """Export a model without violations and warn instead when constraint violations are present."""
        for violations in ([], ["Invalid classification"]):
            with self.subTest(violations=violations):
                model = Mock()
                model.validate_basemlm_integrity.return_value = violations
                ui = SimpleNamespace(
                    current_model=model, current_file_type="XML", current_file_path=None,
                    _show_warning=Mock(), _export_current_xml_model=Mock(),
                )
                ui._run_model_task = lambda _total, _message, work, success, _error: success(work(None))
                ModelDeepenerApp._export_current_model_placeholder(ui)
                self.assertEqual(ui._export_current_xml_model.call_count, int(not violations))
                self.assertEqual(ui._show_warning.call_count, int(bool(violations)))


if __name__ == "__main__":
    unittest.main()
