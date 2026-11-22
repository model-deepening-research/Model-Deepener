import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from src.gui.app import ModelDeepenerApp


class BatchSelectionTests(unittest.TestCase):
    """Test batch selection."""
    def test_cancelled_input_chooser_does_not_change_mode(self):
        """Check cancelled input chooser does not change mode."""
        ui = SimpleNamespace(_file_input_mode="upload", _set_file_input_mode=Mock(), _reset_file_input_hover=Mock())
        for mode in ("example", "batch", "upload"):
            callback = Mock(return_value=None)
            ModelDeepenerApp._activate_file_input(ui, mode, callback)
            callback.assert_called_once()
        self.assertEqual(ui._file_input_mode, "upload")
        ui._set_file_input_mode.assert_not_called()
        self.assertEqual(ui._reset_file_input_hover.call_count, 3)

    def test_selection_displays_paths_and_enables_create(self):
        """Check selection displays paths and enables create."""
        ui = SimpleNamespace(current_batch_paths=[], current_file_path='old.csv', csv_preview=object(),
                             xml_preview=object(), selected_csv_columns={'old': True}, file_entry=Mock(),
                             batch_file_list=Mock(), batch_folder_panel=Mock(), column_selection_description=Mock(),
                             _render_empty_preview=Mock(), _set_column_selection_enabled=Mock(), _set_validation_badge_visible=Mock(),
                             _importer_for_file=Mock(return_value=object()), _set_validation_rows=Mock(),
                             _set_create_button_enabled=Mock())
        ModelDeepenerApp._select_batch_files(ui, ['one.csv', 'two.xml'])
        self.assertEqual(ui.current_batch_paths, ['one.csv', 'two.xml'])
        self.assertIsNone(ui.current_file_path)
        ui.batch_file_list.insert.assert_called_once_with('1.0', 'one.csv\ntwo.xml')
        ui._render_empty_preview.assert_called_once_with('Column selection is only available when importing a single file.')
        ui._set_create_button_enabled.assert_called_once_with(True)
        self.assertEqual(ui.selected_csv_columns, {})

    def test_unsupported_file_disables_create(self):
        """Check unsupported file disables create."""
        ui = SimpleNamespace(selected_csv_columns={}, file_entry=Mock(), batch_file_list=Mock(), batch_folder_panel=Mock(),
                             column_selection_description=Mock(), _render_empty_preview=Mock(),
                             _set_validation_badge_visible=Mock(), _set_column_selection_enabled=Mock(), _importer_for_file=Mock(side_effect=[object(), None]),
                             _set_validation_rows=Mock(), _set_create_button_enabled=Mock())
        ModelDeepenerApp._select_batch_files(ui, ['one.csv', 'invalid.bin'])
        ui._set_create_button_enabled.assert_called_once_with(False)

    def test_create_dispatches_to_batch(self):
        """Check create dispatches to batch."""
        ui = SimpleNamespace(current_batch_paths=['one.csv', 'two.xml'], _start_batch_import=Mock())
        ModelDeepenerApp._create_model(ui)
        ui._start_batch_import.assert_called_once_with()

    def test_folder_collection_includes_nested_supported_files_only(self):
        """Check folder collection includes nested supported files only."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "one.XMI").write_text("", encoding="utf-8")
            (root / "nested" / "two.ecore").write_text("", encoding="utf-8")
            (root / "nested" / "ignore.png").write_text("", encoding="utf-8")
            with patch("builtins.open", side_effect=AssertionError("Folder scanning must not read files")):
                paths = ModelDeepenerApp._collect_batch_folder(directory)
            self.assertEqual({Path(path).name for path in paths}, {"one.XMI", "two.ecore"})

    def test_folder_selection_shows_folder_and_count(self):
        """Check folder selection shows folder and count."""
        ui = SimpleNamespace(current_batch_paths=[], selected_csv_columns={}, file_entry=Mock(),
                             batch_file_list=Mock(), batch_folder_panel=Mock(), _set_column_selection_enabled=Mock(),
                             _render_empty_preview=Mock(), _set_validation_badge_visible=Mock(),
                             _set_validation_rows=Mock(), _set_create_button_enabled=Mock())
        ModelDeepenerApp._select_batch_files(ui, ["one.xmi", "two.xmi"], folder="some folder")
        ui.batch_file_list.insert.assert_called_once_with("1.0", "some folder\n2 files found")
        ui._set_create_button_enabled.assert_called_once_with(True)

    def test_folder_choice_passes_all_selected_directories_to_background_scan(self):
        """Check folder choice passes all selected directories to background scan."""
        ui = SimpleNamespace(_overlay=Mock(), _ask_batch_source=Mock(return_value="folder"),
                             _choose_batch_folders=Mock(return_value=["A", "B"]), _scan_batch_folders=Mock(), _set_file_input_mode=Mock())
        ModelDeepenerApp._browse_batch(ui)
        ui._scan_batch_folders.assert_called_once_with(["A", "B"], replace=True)

    def test_scanning_multiple_folders_replaces_after_success_and_preserves_each_count(self):
        """Check scanning multiple folders replaces after success and preserves each count."""
        def run(_total, _message, work, success, _failure):
            success(work(lambda *_: None))
        ui = SimpleNamespace(current_batch_folders={"old": ("old", ["old.xmi"])},
                             _run_model_task=run, _collect_batch_folder=lambda folder: [folder + "/a.xmi"],
                             _show_batch_folders=Mock(), _show_information=Mock(), _show_error=Mock())
        ModelDeepenerApp._scan_batch_folders(ui, ["A", "B"], replace=True)
        self.assertEqual([value[0] for value in ui.current_batch_folders.values()], ["A", "B"])
        self.assertEqual([len(value[1]) for value in ui.current_batch_folders.values()], [1, 1])
        ui._show_batch_folders.assert_called_once()

    def test_empty_folder_remains_listed_with_zero_files(self):
        """Check empty folder remains listed with zero files."""
        def run(_total, _message, work, success, _failure):
            success(work(lambda *_: None))
        ui = SimpleNamespace(current_batch_folders={}, _run_model_task=run,
                             _collect_batch_folder=lambda _folder: [], _show_batch_folders=Mock(),
                             _show_information=Mock(), _show_error=Mock())
        ModelDeepenerApp._scan_batch_folders(ui, ["Empty"], replace=True)
        self.assertEqual(list(ui.current_batch_folders.values()), [("Empty", [])])
        ui._show_batch_folders.assert_called_once()
        ui._show_information.assert_called_once()

    def test_other_systems_use_single_folder_dialog(self):
        """Check other systems use single folder dialog."""
        ui = SimpleNamespace()
        with patch("src.gui.app.sys.platform", "linux"), patch("src.gui.app.filedialog.askdirectory", return_value="A"):
            self.assertEqual(ModelDeepenerApp._choose_batch_folders(ui, "Select Folder"), ["A"])
        with patch("src.gui.app.sys.platform", "linux"), patch("src.gui.app.filedialog.askdirectory", return_value=""):
            self.assertEqual(ModelDeepenerApp._choose_batch_folders(ui, "Select Folder"), [])

    def test_single_selection_uses_single_upload_validation(self):
        """Check single selection uses single upload validation."""
        ui = SimpleNamespace(_overlay=Mock(), _ask_batch_source=Mock(return_value="files"), _import_file_types=Mock(return_value=[]), file_path_var=Mock(),
                             _validate_current_file=Mock(), _select_batch_files=Mock(), _set_file_input_mode=Mock())
        with patch('src.gui.app.filedialog.askopenfilenames', return_value=('one.csv',)):
            ModelDeepenerApp._browse_batch(ui)
        ui.file_path_var.set.assert_called_once_with('one.csv')
        ui._validate_current_file.assert_called_once_with()
        ui._select_batch_files.assert_not_called()


if __name__ == '__main__':
    unittest.main()
