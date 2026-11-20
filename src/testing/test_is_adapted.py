"""Tests for the import adaptation flag."""
import os
import pickle
import tempfile
import unittest
from pathlib import Path

from src.basemlm.basemlm_model import BaseMlmModel
from src.importers.plantuml_import.plantuml_importer import PlantUmlImporter
from src.object_database.storage import FileStorage
from src.importers.import_report import ImportAdaptation, ImportReport, StructureProblem, UNKNOWN_PARENT


class AdaptationFlagTests(unittest.TestCase):
    """Check report flags and stored models."""

    def test_serious_and_informational_report_entries(self) -> None:
        serious = ["DataType", "Unresolved type", "Unknown type", "Unresolved reference",
                   "Unresolved generalization", "Unresolved association end", "Unresolved association type",
                   "Invalid association", "Invalid multiplicity", "Composition whole end", "Constraint not exported"]
        informational = ["Operation skipped", "Operations skipped", "Interface", "Folder",
                         "Attribute without type", "Missing type", "Datatype mapped to primitive"]
        for kind in serious + informational:
            with self.subTest(kind=kind):
                report = ImportReport()
                report.add_adaptation(ImportAdaptation(kind, "", kind))
                self.assertTrue(report.has_problems())
                self.assertEqual(report.has_serious_problems(), kind in serious)
        for description, expected in [("EDataType represented as String", True),
                                      ("EDataType represented as Integer", False)]:
            report = ImportReport()
            report.add_adaptation(ImportAdaptation("EDataType", "", description))
            self.assertEqual(report.has_serious_problems(), expected)
        report = ImportReport()
        report.add_structure_problem(StructureProblem(UNKNOWN_PARENT, "A", "", "B"))
        self.assertTrue(report.has_serious_problems())

    def test_legacy_model_and_pickle(self) -> None:
        model = BaseMlmModel()
        del model.is_adapted
        self.assertFalse(model.get_is_adapted())
        model.set_is_adapted(True)
        self.assertTrue(pickle.loads(pickle.dumps(model)).get_is_adapted())
        with tempfile.TemporaryDirectory() as directory:
            storage = FileStorage(str(Path(directory, 'database.pkl')))
            storage.save({'model': model})
            self.assertTrue(storage.load()['model'].get_is_adapted())

    def test_renaming_alone_does_not_set_flag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'names.txt')
            path.write_text('@startuml\nclass Person {\nString Name\n}\n@enduml\n', encoding='utf-8')
            model, report = PlantUmlImporter().import_file(str(path))
            self.assertFalse(report.has_problems())
            self.assertFalse(model.get_is_adapted())
            self.assertEqual(model.get_all_flat_classes()[0].get_regular_attributes()[0].get_name(), 'name')

    def test_skipped_operation_is_informational(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'operation.txt')
            path.write_text('@startuml\nclass Person {\n+run()\n}\n@enduml\n', encoding='utf-8')
            model, report = PlantUmlImporter().import_file(str(path))
            self.assertTrue(report.has_problems())
            self.assertFalse(model.get_is_adapted())

    def test_constructor_and_direct_import_set_flag(self) -> None:
        path = os.path.join('models', 'plantuml', 'TransportCompany.txt')
        model = BaseMlmModel(path)
        self.assertTrue(model.get_is_adapted())
        model.set_is_adapted(False)
        report = PlantUmlImporter().import_into(model, path)
        self.assertEqual(model.get_is_adapted(), report.has_serious_problems())
        self.assertTrue(model.get_is_adapted())


if __name__ == '__main__':
    unittest.main()
