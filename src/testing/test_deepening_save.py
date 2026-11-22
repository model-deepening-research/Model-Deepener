import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from src.basemlm.basemlm_model import BaseMlmModel
from src.gui.app import LoadedModel
from src.gui.deepening import export_tell_table, save_deepened_models
from src.gui.tell_results import TellResultRow
from src.object_database.folder import DatabaseFolder


class DeepeningTests(unittest.TestCase):
    """Test deepening."""
    def test_batch_save_copies_models_selects_rows_and_resolves_names(self):
        """Check batch save copies models selects rows and resolves names."""
        with tempfile.TemporaryDirectory() as directory:
            folder = DatabaseFolder(directory)
            db = folder.create_database('test')
            a = LoadedModel(name='A', source_file='a.csv', file_type='CSV', model=BaseMlmModel())
            b = LoadedModel(name='B', source_file='b.xml', file_type='XML', model=BaseMlmModel())
            for item in [a, b]:
                db.store(item)
            db.commit()
            existing = [a, b]
            rows = [(TellResultRow('a1', 'i', 'A'), 'Yes'), (TellResultRow('a2', 'i', 'A'), 'No'),
                    (TellResultRow('b1', 'i', 'B'), 'Yes')]
            calls = []
            def transform(model, selected):
                calls.append((model, selected))
                return model
            with patch('src.gui.deepening.perform_deepening_transformation', side_effect=transform):
                saved = save_deepened_models(db, existing, [a, b], rows, True, LoadedModel)
            self.assertEqual([m.name for m in saved], ['A_deepened', 'B_deepened'])
            self.assertIsNot(saved[0].model, a.model)
            self.assertEqual([row.affected_parts for row in calls[0][1]], ['a1'])
            self.assertEqual([row.affected_parts for row in calls[1][1]], ['b1'])
            again = save_deepened_models(db, existing, [a], [], False, LoadedModel)
            self.assertEqual(again[0].name, 'A_deepened (2)')
            self.assertEqual(len(folder.open_database('test').get_all()), 5)

    def test_failure_rolls_back_staged_records(self):
        """Check failure rolls back staged records."""
        db = Mock()
        db.store.side_effect = lambda item: item.assign_oid(db.store.call_count)
        db.commit.side_effect = OSError('cannot save')
        original = LoadedModel(name='A', source_file='a', file_type='XML', model=BaseMlmModel())
        loaded = [original]
        with self.assertRaises(OSError):
            save_deepened_models(db, loaded, [original], [], False, LoadedModel)
        self.assertEqual(loaded, [original])
        db.delete.assert_called_once_with(1)

    def test_csv_matches_table_for_single_and_batch(self):
        """Check csv matches table for single and batch."""
        rows = [(TellResultRow('A, B', 'i1', 'Model'), 'Yes'), (TellResultRow('C', 'i2', 'Model'), 'No')]
        with tempfile.TemporaryDirectory() as directory:
            for batch in (False, True):
                path = Path(directory, 'results.csv')
                export_tell_table(path, rows, batch)
                with path.open(encoding='utf-8-sig', newline='') as file:
                    result = list(csv.reader(file))
                self.assertEqual(result[0], (['Model Name'] if batch else []) + ['Affected Parts', 'Indicators', 'Transform?'])
                self.assertEqual(result[1], (['Model'] if batch else []) + ['A, B', 'i1', 'Yes'])
                self.assertEqual(result[2][-1], 'No')


if __name__ == '__main__':
    unittest.main()
