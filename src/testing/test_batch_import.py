import tempfile
import pickle
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.gui.app import ModelDeepenerApp
from src.importers import importer_for
from src.object_database.folder import DatabaseFolder
from src.testing.test_xmi_importer import HEAD, TAIL


class BatchImportTests(unittest.TestCase):
    """Test batch import."""
    def test_five_formats_saved_and_reloaded(self):
        """Check five formats saved and reloaded."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv = root / 'sample.csv'
            csv.write_text('name,age,city\nAlice,22,Berlin\n', encoding='utf-8')
            plant = root / 'sample.puml'
            plant.write_text('@startuml\ninterface Contract\n@enduml\n', encoding='utf-8')
            xmi = root / 'sample.xmi'
            xmi.write_text(HEAD + '<packagedElement xsi:type="uml:Class" xmi:id="c" name="C"><ownedAttribute xmi:id="a" name="missing" type="missing"/></packagedElement>' + TAIL, encoding='utf-8')
            paths = [csv, Path('models/fmmlx/Portaview_with_Objects.xml'), plant, xmi,
                     Path('models/ecore/accounting__Fakturama.ecore')]
            candidates = []
            for path in paths:
                importer = importer_for(str(path))
                model, report = importer.import_file(str(path))
                candidates.append((str(path), importer, model, report))
            folder = DatabaseFolder(str(root / 'db'))
            database = folder.create_database('batch')
            ui = SimpleNamespace(_database=database, loaded_models=[], batch_models=[],
                                 _current_timestamp_text=Mock(return_value='now'),
                                 ACTION_TITLES={2: 'Imported'})
            ModelDeepenerApp._store_batch(ui, candidates)
            restored = folder.open_database('batch').get_all()
            self.assertEqual(len(restored), 5)
            self.assertEqual(ui.batch_models, ui.loaded_models)
            self.assertEqual(len(restored[0].model.get_all_flat_classes()[0].get_regular_attributes()), 3)
            for saved, (_, _, original, report) in zip(restored, candidates):
                self.assertEqual(saved.model.get_is_adapted(), original.get_is_adapted())
                self.assertEqual(saved.model.get_is_adapted(), report.has_serious_problems())
                self.assertEqual([o.get_import_notes() for o in saved.model.get_objects()],
                                 [o.get_import_notes() for o in original.get_objects()])
            self.assertTrue(restored[3].model.get_is_adapted())

    def test_batch_updates_autosave_snapshot_and_saves_later_changes(self):
        """Check batch updates autosave snapshot and saves later changes."""
        from src.basemlm.basemlm_model import BaseMlmModel
        from src.object_database.database import Database
        from src.object_database.storage import FileStorage
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "batch.pkl")
            storage = FileStorage(path)
            database = Database(storage)
            ui = SimpleNamespace(_database=database, loaded_models=[], batch_models=[],
                                 _current_timestamp_text=lambda: "now", ACTION_TITLES={2: "Imported"},
                                 _model_task_active=False, _is_closing=True,
                                 _autosave_snapshot=pickle.dumps(database.get_all()), _show_error=Mock())
            importer = SimpleNamespace(FORMAT_NAME="XMI")
            candidates = [(f"{i}.xmi", importer, BaseMlmModel(), None) for i in range(20)]
            progress = Mock()
            with patch.object(storage, "save_serialized", wraps=storage.save_serialized) as save:
                ModelDeepenerApp._store_batch(ui, candidates, progress)
                self.assertEqual(save.call_count, 1)
                self.assertEqual(len(Database(storage).get_all()), 20)
                self.assertEqual(progress.call_count, 22)
                self.assertEqual(progress.call_args.args, (20, 20, "Writing database...", 1.0))
                self.assertFalse(database.save_if_changed())
                self.assertEqual(save.call_count, 1)
                ui.loaded_models[0].name = "Changed"
                self.assertTrue(database.save_if_changed())
                self.assertEqual(save.call_count, 2)

    def test_failed_commit_removes_all_staged_models(self):
        """Check failed commit removes all staged models."""
        database = Mock()
        database.get_all.return_value = []
        database.store.side_effect = lambda obj: obj.assign_oid(database.store.call_count)
        database.commit.side_effect = OSError('failed')
        ui = SimpleNamespace(_database=database, loaded_models=[], batch_models=[],
                             _current_timestamp_text=Mock(return_value='now'), ACTION_TITLES={2: 'Imported'})
        from src.basemlm.basemlm_model import BaseMlmModel
        importer = SimpleNamespace(FORMAT_NAME='CSV')
        candidates = [('a.csv', importer, BaseMlmModel(), None), ('b.csv', importer, BaseMlmModel(), None)]
        with self.assertRaises(OSError):
            ModelDeepenerApp._store_batch(ui, candidates)
        self.assertEqual(database.delete.call_count, 2)
        self.assertEqual(ui.loaded_models, [])


if __name__ == '__main__':
    unittest.main()
