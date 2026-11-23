"""Integration tests for example selection and relocated model folders."""
import os
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.gui.app import ModelDeepenerApp
from src.importers.model_importer import importer_for


class ExampleFolderTests(unittest.TestCase):
    """Select relocated examples and import them through the dialog callback."""

    def test_select_and_import_csv_and_fmmlx_examples(self) -> None:
        for filename, expected_folder in [('smartphone.csv', 'csv'), ('Portaview_with_Objects.xml', 'fmmlx')]:
            with self.subTest(filename=filename):
                tree = MagicMock()
                items: dict[str, str] = {}
                roots: list[tuple[str, bool, str]] = []
                callbacks = {}
                def insert(parent, _position, **kwargs):
                    item = str(len(items))
                    items[item] = kwargs['text']
                    if parent == '':
                        roots.append((kwargs['text'], kwargs['open'], item))
                    return item
                tree.insert.side_effect = insert
                tree.bind.side_effect = lambda event, callback: callbacks.update({event: callback})
                results = []
                ui = SimpleNamespace(
                    _collect_example_files=ModelDeepenerApp._collect_example_files,
                    _tree=lambda *args, **kwargs: tree,
                    _overlay=MagicMock(), file_path_var=MagicMock(), current_file_path='',
                    colors={'text': '#000000', 'border': '#000000', 'primary': '#000000', 'primary_hover': '#000000'},
                    _show_information=MagicMock(), _set_file_input_mode=MagicMock(), wait_window=MagicMock(),
                )
                def validate() -> None:
                    results.append(importer_for(ui.current_file_path).import_file(ui.current_file_path))
                ui._validate_current_file = validate
                with patch.multiple('src.gui.app.ctk', CTkToplevel=MagicMock(), CTkLabel=MagicMock(),
                                    CTkFrame=MagicMock(), CTkScrollbar=MagicMock(), CTkButton=MagicMock(),
                                    CTkFont=MagicMock()):
                    ModelDeepenerApp._select_example_file(ui)
                    self.assertEqual([(label, opened) for label, opened, _item in roots],
                                     [('CSV', False), ('FMMLx', False), ('PlantUML', False),
                                      ('XMI', False), ('Ecore', False)])
                    tree.identify_row.return_value = roots[0][2]
                    tree.identify.return_value = 'text'
                    tree.item.return_value = False
                    callbacks['<ButtonRelease-1>'](SimpleNamespace(x=30, y=10))
                    tree.item.assert_any_call(roots[0][2], open=True)
                    matches = [item for item, text in items.items() if text == filename]
                    self.assertEqual(len(matches), 1)
                    tree.selection.return_value = [matches[0]]
                    callbacks['<Double-1>'](None)
                self.assertEqual(os.path.basename(os.path.dirname(ui.current_file_path)), expected_folder)
                self.assertEqual(len(results), 1)
                self.assertTrue(results[0][0].get_objects())


    def test_unsupported_files_are_not_listed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'notes.txt').write_text('not a diagram', encoding='utf-8')
            (root / 'diagram.txt').write_text('@startuml\nclass A\n@enduml', encoding='utf-8')
            (root / 'photo.png').write_bytes(b'not a model')
            self.assertEqual(ModelDeepenerApp._collect_example_files(directory),
                             [(directory, ['diagram.txt'])])


if __name__ == '__main__':
    unittest.main()
