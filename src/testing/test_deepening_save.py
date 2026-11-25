import csv
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from types import SimpleNamespace

from src.basemlm.basemlm_model import BaseMlmModel
from src.gui.app import LoadedModel, ModelDeepenerApp
from src.gui.deepening import (DeepeningOutcome, export_tell_table, perform_deepening_transformation,
                               save_deepened_models)
from src.basemlm.model_part import ModelPart
from src.importers.fmmlx_xml_import.xml_importer import XmlImporter
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
                return DeepeningOutcome(copy.deepcopy(model), len(selected), 0)
            with patch('src.gui.deepening.perform_deepening_transformation', side_effect=transform):
                saved, unavailable, total = save_deepened_models(db, existing, [a, b], rows, True, LoadedModel)
            self.assertEqual((unavailable, total), (0, 2))
            self.assertEqual([m.name for m in saved], ['A_deepened', 'B_deepened'])
            self.assertIsNot(saved[0].model, a.model)
            self.assertTrue(saved[0].model.get_is_deepened())
            self.assertFalse(a.model.get_is_deepened())
            self.assertEqual([row.affected_parts for row in calls[0][1]], ['a1'])
            self.assertEqual([row.affected_parts for row in calls[1][1]], ['b1'])
            with patch('src.gui.deepening.perform_deepening_transformation', side_effect=transform):
                again, _, _ = save_deepened_models(db, existing, [a], [(TellResultRow('a1', 'i', 'A'), 'Yes')], False, LoadedModel)
            self.assertEqual(again[0].name, 'A_deepened (2)')
            self.assertEqual(len(folder.open_database('test').get_all()), 5)

    def test_only_selected_models_are_saved(self):
        db = Mock()
        a = LoadedModel(name='A', source_file='a', file_type='CSV', model=BaseMlmModel())
        b = LoadedModel(name='B', source_file='b', file_type='XML', model=BaseMlmModel())
        rows = [(TellResultRow('a1', 'OC1', 'A'), 'Yes'), (TellResultRow('b1', 'OC1', 'B'), 'No')]
        with patch('src.gui.deepening.perform_deepening_transformation', side_effect=lambda model, rows: DeepeningOutcome(copy.deepcopy(model), len(rows), 0)):
            saved, _, _ = save_deepened_models(db, [a, b], [a, b], rows, True, LoadedModel)
        self.assertEqual([item.name for item in saved], ['A_deepened'])
        db.store.assert_called_once()

    def test_unimplemented_transformation_does_not_save_a_copy(self):
        db = Mock()
        a = LoadedModel(name='A', source_file='a', file_type='CSV', model=BaseMlmModel())
        saved, unavailable, total = save_deepened_models(db, [a], [a], [(TellResultRow('a', 'OC1', 'A'), 'Yes')], True, LoadedModel)
        self.assertEqual((saved, unavailable, total), ([], 1, 1))
        db.store.assert_not_called()
        db.commit.assert_not_called()

    def test_dispatch_changes_only_copy_and_skips_unavailable_rows(self):
        model, _ = XmlImporter().import_file('models/fmmlx/c13_inst_level_not_lower.xml')
        element = model.get_all_flat_classes()[0]
        rows = [TellResultRow('Class', 'OC5', 'A', model_part=ModelPart(element)),
                TellResultRow('Class', 'TO1', 'A', model_part=ModelPart(element))]
        observed = []
        def apply(engine, part):
            target = part.get_model_elements()[0]
            observed.append(target is engine.fmmlx_model.get_all_flat_classes()[0])
            target.name = 'Changed'
        with patch.dict('src.gui.deepening.TELL_OPERATIONS', {'OC5': apply}, clear=True), \
                patch('src.gui.deepening.ALLOWED_TELLS', {'OC5'}):
            outcome = perform_deepening_transformation(model, rows)
        self.assertEqual((outcome.applied, outcome.unavailable), (1, 1))
        self.assertEqual(observed, [True])
        self.assertEqual(outcome.model.get_all_flat_classes()[0].name, 'Changed')
        self.assertEqual(element.name, 'Class')

    def test_not_implemented_is_counted_and_partial_changes_are_discarded(self):
        model, _ = XmlImporter().import_file('models/fmmlx/c13_inst_level_not_lower.xml')
        element = model.get_all_flat_classes()[0]
        row = TellResultRow('Class', 'OC5', 'A', model_part=ModelPart(element))
        def unfinished(engine, part):
            part.get_model_elements()[0].name = 'Partial'
            raise NotImplementedError()
        with patch.dict('src.gui.deepening.TELL_OPERATIONS', {'OC5': unfinished}, clear=True), \
                patch('src.gui.deepening.ALLOWED_TELLS', {'OC5'}):
            outcome = perform_deepening_transformation(model, [row])
        self.assertEqual((outcome.applied, outcome.unavailable), (0, 1))
        self.assertEqual(outcome.model.get_all_flat_classes()[0].name, 'Class')
        self.assertEqual(element.name, 'Class')

    def test_oc5_is_not_called_until_enabled(self):
        model, _ = XmlImporter().import_file('models/fmmlx/c13_inst_level_not_lower.xml')
        element = model.get_all_flat_classes()[0]
        row = TellResultRow('Class', 'OC5', 'A', model_part=ModelPart(element))
        with patch('src.gui.deepening._apply_property_precedence') as operation, \
                patch.dict('src.gui.deepening.TELL_OPERATIONS', {'OC5': operation}, clear=True):
            outcome = perform_deepening_transformation(model, [row])
        operation.assert_not_called()
        self.assertEqual((outcome.applied, outcome.unavailable), (0, 1))
        self.assertEqual(element.level, 1)

    def test_failure_rolls_back_staged_records(self):
        """Check failure rolls back staged records."""
        db = Mock()
        db.store.side_effect = lambda item: item.assign_oid(db.store.call_count)
        db.commit.side_effect = OSError('cannot save')
        original = LoadedModel(name='A', source_file='a', file_type='XML', model=BaseMlmModel())
        loaded = [original]
        with self.assertRaises(OSError):
            with patch('src.gui.deepening.perform_deepening_transformation', side_effect=lambda model, rows: DeepeningOutcome(copy.deepcopy(model), len(rows), 0)):
                save_deepened_models(db, loaded, [original], [(TellResultRow('a', 'i', 'A'), 'Yes')], False, LoadedModel)
        self.assertEqual(loaded, [original])
        db.delete.assert_called_once_with(1)

    def test_csv_matches_table_for_single_and_batch(self):
        """Check csv matches table for single and batch."""
        rows = [(TellResultRow('A, B', 'i1', 'Model', model_format='FMMLx'), 'Yes'), (TellResultRow('C', 'i2', 'Model'), 'No')]
        with tempfile.TemporaryDirectory() as directory:
            for batch in (False, True):
                path = Path(directory, 'results.csv')
                export_tell_table(path, rows, batch)
                self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
                with path.open(encoding='utf-8-sig', newline='') as file:
                    result = list(csv.reader(file, delimiter=";"))
                self.assertEqual(result[0], ['Model Name', 'Format', 'Affected Parts', 'Tell', 'Transform?'])
                self.assertEqual(result[1], ['Model', 'FMMLx', 'A, B', 'i1', 'Yes'])
                self.assertEqual(result[2][-1], 'No')

    def test_transform_with_no_selection_shows_requested_message(self):
        model = BaseMlmModel()
        loaded = LoadedModel(name='A', source_file='a', file_type='CSV', model=model)
        ui = SimpleNamespace(batch_models=[loaded], _show_information=Mock(), _show_error=Mock(),
                             _run_model_task=Mock())
        panel = SimpleNamespace(_tell_rows=[(TellResultRow('X', 'OC1', 'A'), SimpleNamespace(get=lambda: 'No'))])
        ModelDeepenerApp._transform_tell_results(ui, panel, True)
        ui._show_information.assert_called_once_with('Deepening', 'Nothing to transform: all rows are set to No.')
        ui._run_model_task.assert_not_called()

    def test_failed_check_is_exported_with_reason(self):
        row = TellResultRow('TO2 failed: ValueError: problem', 'TO2', 'Model', model_format='XMI', is_placeholder=True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'results.csv')
            export_tell_table(path, [(row, 'No')], True)
            with path.open(encoding='utf-8-sig', newline='') as file:
                values = list(csv.reader(file, delimiter=';'))
        self.assertEqual(values[1], ['Model', 'XMI', 'TO2 failed: ValueError: problem', 'TO2', 'No'])

    def test_placeholder_export_keeps_model_and_no_decision(self):
        row = TellResultRow('No affected parts found.', '', 'Empty', model_format='Ecore', is_placeholder=True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'results.csv')
            export_tell_table(path, [(row, 'No')], True)
            with path.open(encoding='utf-8-sig', newline='') as file:
                values = list(csv.reader(file, delimiter=';'))
        self.assertEqual(values[1], ['Empty', 'Ecore', 'No affected parts found.', '', 'No'])


if __name__ == '__main__':
    unittest.main()
