import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

from src.gui.app import ModelDeepenerApp, ask_import_problems
from src.gui.batch_reports import batch_problem_summary, write_batch_problem_list, visible_import_report, visible_import_notes
from src.importers.import_report import ImportAdaptation, ImportReport, StructureProblem, UNKNOWN_PARENT
from src.basemlm.basemlm_model import BaseMlmModel


class BatchReportsTests(unittest.TestCase):
    """Test batch reports."""
    def test_summary_counts_models_once_per_kind(self):
        """Check summary counts models once per kind."""
        first = ImportReport()
        first.add_adaptation(ImportAdaptation('Duplicate class', 'A', 'A renamed'))
        first.add_adaptation(ImportAdaptation('Duplicate class', 'B', 'B renamed'))
        first.add_structure_problem(StructureProblem(UNKNOWN_PARENT, 'A', '', 'missing'))
        second = ImportReport()
        second.add_adaptation(ImportAdaptation('Duplicate class', 'C', 'C renamed'))
        self.assertEqual(batch_problem_summary([('one', first), ('two', second)]),
                         ['Duplicate class: 2 models', 'Unknown parent: 1 model'])

    def test_summary_explains_and_merges_equivalent_categories(self):
        """Check summary explains and merges equivalent categories."""
        report = ImportReport()
        report.add_adaptation(ImportAdaptation("DataType", "A", "Replaced"))
        report.add_adaptation(ImportAdaptation("EDataType", "B", "Replaced"))
        report.add_adaptation(ImportAdaptation("Composition whole end", "C", "Changed"))
        self.assertEqual(batch_problem_summary([("one.xmi", report)]),
                         ["Composition multiplicity corrected: 1 model", "Data type replaced by String: 1 model"])

    def test_operation_hints_are_hidden_without_changing_the_report(self):
        """Check operation hints are hidden without changing the report."""
        report = ImportReport()
        report.add_adaptation(ImportAdaptation("Operation skipped", "A", "Operation A.f skipped."))
        report.add_adaptation(ImportAdaptation("Line not understood", "A", "Operation not understood and skipped: f()"))
        report.add_adaptation(ImportAdaptation("Unknown type", "A", "Unknown type replaced by String."))
        visible = visible_import_report(report)
        self.assertEqual(len(report.get_adaptations()), 3)
        self.assertEqual([item.get_problem_type() for item in visible.get_adaptations()], ["Unknown type"])
        self.assertEqual(batch_problem_summary([("x", report)]), ["Unknown type replaced by String: 1 model"])
        self.assertEqual(visible_import_notes([("Operation skipped: f()", False), ("Renamed A", False)]),
                         [("Renamed A", False)])
        self.assertEqual(ModelDeepenerApp._import_note_tag(SimpleNamespace(get_import_notes=lambda: [("Operation skipped: f()", False)])), "")

    def test_report_with_only_operation_hints_needs_no_dialog(self):
        """Check report with only operation hints needs no dialog."""
        report = ImportReport()
        report.add_adaptation(ImportAdaptation("Operations skipped", "", "Operations are skipped during import."))
        with patch("src.gui.app.ImportProblemDialog") as dialog:
            self.assertTrue(ask_import_problems(Mock(), report, Mock()))
            dialog.assert_not_called()
        self.assertEqual(len(report.get_adaptations()), 1)

    def test_export_contains_model_and_each_original_problem(self):
        """Check export contains model and each original problem."""
        report = ImportReport()
        report.add_adaptation(ImportAdaptation('Duplicate class', 'A', 'Renamed'))
        report.add_adaptation(ImportAdaptation('Duplicate class', 'B', 'Renamed'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'report.csv')
            write_batch_problem_list(path, [('model.xml', report)])
            with path.open(encoding='utf-8-sig', newline='') as file:
                rows = list(csv.reader(file))
        self.assertEqual(rows[0], ['Model Name'] + ImportReport.PROBLEM_LIST_HEADER)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1], ['model.xml', 'Duplicate class', 'A', '', '', 'Renamed', ''])
        self.assertEqual(rows[2][2], 'B')

    def test_failed_files_are_in_summary_and_csv(self):
        """Check failed files are in summary and csv."""
        failures = [("bad.csv", "Wrong number of columns"), ("bad.xmi", "Invalid XML")]
        self.assertEqual(batch_problem_summary([], failures), [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "problems.csv"
            write_batch_problem_list(path, [], failures)
            with path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.reader(file))
        self.assertEqual(rows[1], ["bad.csv", "Could not be imported", "", "", "", "Wrong number of columns", ""])
        self.assertEqual(rows[2][0], "bad.xmi")

    def test_storage_updates_progress_for_each_model(self):
        """Check storage updates progress for each model."""
        db = Mock()
        db.get_all.return_value = []
        db.store.side_effect = lambda item: item.assign_oid(db.store.call_count)
        ui = SimpleNamespace(_database=db, loaded_models=[], batch_models=[],
                             _current_timestamp_text=Mock(return_value='now'), ACTION_TITLES={2: 'Imported'})
        importer = SimpleNamespace(FORMAT_NAME='XML')
        candidates = [('a.xml', importer, BaseMlmModel(), None), ('b.xml', importer, BaseMlmModel(), None)]
        progress = Mock()
        ModelDeepenerApp._store_batch(ui, candidates, progress)
        self.assertEqual([call.args for call in progress.call_args_list], [(1, 2, "Preparing models...", 0.25), (2, 2, "Preparing models...", 0.5),
                          (2, 2, "Writing database...", 0.5), (2, 2, "Writing database...", 1.0)])
        db.commit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
