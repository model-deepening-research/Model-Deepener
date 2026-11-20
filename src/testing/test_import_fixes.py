"""Regression tests for import fidelity, independent input data and atomic GUI adoption."""
import csv
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from src.basemlm.basemlm_model import BaseMlmModel
from src.basemlm.basemlm_predefined_type import DateType
from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_slot import BaseMlmSlot
from src.gui.app import ModelDeepenerApp
from src.importers import CsvImporter, PlantUmlImporter, XmlImporter
from src.importers.csv_import.csv_reader import CsvReader
from src.importers.import_report import ImportReport
from src.importers.model_importer import register_importer, supported_extensions
from src.importers.class_diagram import UmlOperation, UmlParameter
from src.importers.plantuml_import.plantuml_reader import parse_multiplicity
from src.importers.slot_value_converter import SlotValueConverter
from src.object_database.folder import DatabaseFolder
from src.testing.test_importers import XML_HEAD, XML_TAIL, typed_slot


class ImportFixTests(unittest.TestCase):
    """Use small sources to verify each corrected conversion independently of golden models."""

    def setUp(self) -> None:
        """Keep input and database fixtures in a fresh disposable directory for every test."""
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self._folder = Path(self._directory.name)

    def _write(self, name: str, text: str) -> str:
        """Create a source fixture and return the path accepted by the importers."""
        path = self._folder / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def _plantuml(self, body: str) -> tuple[ElementTree.Element, ImportReport]:
        """Return normalized XML and the model-import report for a small class diagram."""
        path = self._write("diagram.puml", f"@startuml\n{body}\n@enduml\n")
        importer = PlantUmlImporter()
        model, report = importer.import_file(path)
        output = str(self._folder / "out.xml")
        model.export_xml(output, project_name="Root::diagram")
        root = ElementTree.parse(output).getroot()
        return root, report

    def test_class_attributes_remain_attributes(self) -> None:
        """Preserve class typed properties even when a relationship also exists."""
        root, _ = self._plantuml("class Person {\n Person mother\n Person father\n}\nPerson -- Person")
        self.assertEqual([a.get("name") for a in root.findall("Model/addAttribute")], ["mother", "father"])
        self.assertEqual(len(root.findall("Model/addAssociation")), 1)

    def test_association_class_is_navigable_in_both_directions(self) -> None:
        """Both ends of split relationships are navigable regardless of arrowheads."""
        for arrow in ("-->", "<--", "--"):
            root, _ = self._plantuml(f'class A\nclass B\nclass C\nA "1" {arrow} "0..*" B\n(A, B) .. C')
            for association in root.findall("Model/addAssociation"):
                self.assertEqual(association.get("sourceVisibleFromTarget"), "true")
                self.assertEqual(association.get("targetVisibleFromSource"), "true")

    def test_csv_expressions_remain_literal_while_xml_strings_decode(self) -> None:
        """Keep CSV character-list and date text literal while XML still decodes character-list strings."""
        values = ["[65].asString()", "[].asString()", "broken.asString()",
                  "Auxiliary::Date::createDate(2024, 12, 12)", "Root::Other::Person", "null"]
        path = self._folder / "expressions.csv"
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["text"])
            for value in values:
                writer.writerow([value])
        model, report = CsvImporter().import_file(str(path))
        actual = []
        for obj in model.get_objects()[1:]:
            actual.append(obj.get_regular_slots()[0].get_value())
        self.assertEqual(actual, values[:-1] + [None])
        self.assertFalse(report.has_problems())
        xml_path = self._write("expression.xml", XML_HEAD + typed_slot("Root::XCore::String", values[0]) + XML_TAIL)
        model, report = XmlImporter().import_file(xml_path)
        self.assertEqual(model.get_objects()[1].get_regular_slots()[0].get_value(), "A")
        self.assertFalse(report.has_problems())

    def test_csv_date_expression_is_not_a_date_value(self) -> None:
        """Leave an XModeler date literal as text when expression reading is disabled for a Date slot."""
        model = BaseMlmModel()
        report = ImportReport()
        owner = Mock()
        owner.get_name.return_value = "row"
        attribute = BaseMlmAttribute("date", "Root::Auxiliary::Date", 0, DateType())
        attribute.set_owner(owner)
        text = "Auxiliary::Date::createDate(2024, 12, 12)"
        slot = BaseMlmSlot("date", text)
        slot.set_attribute(attribute)
        slot.set_owner_object(owner)
        SlotValueConverter(model, report, read_xml_expressions=False).convert(slot)
        self.assertEqual(slot.get_value(), text)
        self.assertTrue(report.has_conversion_failures())

    def test_invalid_bounds_use_reported_unbounded_fallback(self) -> None:
        """Replace reversed intervals and star lower bounds with 0..* and an explicit adaptation."""
        for value in ("5..2", "*..1", "*..*"):
            with self.subTest(value=value):
                self.assertIsNone(parse_multiplicity(value))
                root, report = self._plantuml(f'class A\nclass B\nA "{value}" -- "1" B')
                association = root.find("Model/addAssociation")
                self.assertEqual(association.get("multTargetToSource"), "Seq{0,-1,false,false}")
                self.assertIn("Invalid multiplicity", report.get_adaptations()[0].get_description())
        for value in ("*", "0..*", "0..1", "2..5", "1"):
            with self.subTest(valid=value):
                self.assertIsNotNone(parse_multiplicity(value))

    def test_lone_star_is_zero_to_many_without_warning(self) -> None:
        """Import a lone star as zero to many without an invalid multiplicity hint."""
        root, report = self._plantuml('class A\nclass B\nA "*" -- "1" B')
        self.assertEqual(root.find("Model/addAssociation").get("multTargetToSource"), "Seq{0,-1,false,false}")
        self.assertFalse(report.has_adaptations())

    def test_adaptations_are_grouped_for_display_but_not_csv(self) -> None:
        """Count identical messages while retaining each original problem in the CSV."""
        _root, report = self._plantuml('A "bad" -- "1" B\nA "bad" -- "1" B\nA "other" -- "1" B')
        self.assertEqual(report.get_adaptation_summary_lines(), [
            "Invalid multiplicity 'bad' replaced by 0..*. (2×)",
            "Invalid multiplicity 'other' replaced by 0..*.",
        ])
        path = self._folder / "problems.csv"
        report.write_problem_list(str(path))
        with path.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.reader(file))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[1][4], rows[2][4])

    def test_duplicate_roles_are_numbered_and_only_duplicates_are_displayed(self) -> None:
        """Show role names for repeated pairs and automatically named roles."""
        path = self._write("roles.puml", '@startuml\nA "1" -- "1" B : first\n'
                           'A "1" -- "1" B : second\nA "1" -- "1" C : third\n@enduml')
        model, _ = PlantUmlImporter().import_file(path)
        first, second, single = model.get_associations()
        self.assertEqual([first.get_source_access_name(), second.get_source_access_name()], ["b", "b1"])
        self.assertEqual([first.get_target_access_name(), second.get_target_access_name()], ["a", "a1"])
        ui = SimpleNamespace(current_model=model, _name=ModelDeepenerApp._name,
                             _association_multiplicity_text=ModelDeepenerApp._association_multiplicity_text)
        for name in ("_association_table_row", "_class_with_access_name", "_has_duplicate_association_end"):
            setattr(ui, name, MethodType(getattr(ModelDeepenerApp, name), ui))
        self.assertEqual(ui._association_table_row(first)[1:3], ("A (a)", "B (b)"))
        self.assertEqual(ui._association_table_row(second)[1:3], ("A (a1)", "B (b1)"))
        self.assertEqual(ui._association_table_row(single)[1:3], ("A (a)", "C (c)"))

    def test_visibility_prefixes_do_not_change_attributes_or_operations(self) -> None:
        """Read all four visibility prefixes without putting their symbols into names or types."""
        for sign in ("+", "-", "#", "~"):
            with self.subTest(sign=sign):
                root, report = self._plantuml(
                    f"class A {{\n {sign}String name\n {sign} int count()\n {sign}String[] tags\n}}")
                attributes = root.findall("Model/addAttribute")
                self.assertEqual(attributes[0].get("name"), "name")
                self.assertEqual(attributes[0].get("type"), "Root::XCore::String")
                self.assertEqual(attributes[1].get("multiplicity"), "Seq{1,1,true,false}")
                self.assertIsNone(root.find("Model/addOperation"))
                self.assertEqual(len(report.get_adaptations()), 2)

    def test_inputs_and_reader_rows_are_independent_copies(self) -> None:
        """Mutating constructor input or returned CSV rows must not change stored operation or reader data."""
        parameters = [UmlParameter("value", "int")]
        operation = UmlOperation("read", parameters, "int")
        parameters.clear()
        self.assertEqual(len(operation.get_parameters()), 1)
        reader = CsvReader(self._write("rows.csv", "name\nAlice\n"))
        rows = reader.get_data_rows()
        rows[0][0] = "Changed"
        self.assertEqual(reader.get_data_rows(), [["Alice"]])

    def test_duplicate_registration_does_not_partly_register_a_format(self) -> None:
        """Reject a class claiming CSV after an unused ending without keeping its first new ending."""
        class ConflictingImporter(CsvImporter):
            """Claim an unused suffix followed by CSV to verify all-or-nothing registration."""
            EXTENSIONS = (".unused_test", ".CSV")

        previous = supported_extensions()
        with self.assertRaisesRegex(ValueError, "already registered.*.csv"):
            register_importer(ConflictingImporter)
        self.assertEqual(supported_extensions(), previous)

    def test_csv_validation_raises_value_errors(self) -> None:
        """Reject empty files, data headers, wrong row lengths and invalid column selections explicitly."""
        for text, message in [("", "at least one row"), ("1,2\n3,4\n", "header does not look valid"),
                              ("name,age\nAlice\n", "has 1 values")]:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, message):
                    CsvImporter().import_file(self._write("invalid.csv", text))
        path = self._write("valid.csv", "name,age\nAlice,25\n")
        for columns, message in [([], "At least one CSV column"), (["missing"], "were not found")]:
            importer = CsvImporter()
            importer.select_columns(columns)
            with self.assertRaisesRegex(ValueError, message):
                importer.import_file(path)
        model = BaseMlmModel(path)
        with self.assertRaisesRegex(ValueError, "already imported"):
            model.import_xml(path)


class ImportSaveTests(unittest.TestCase):
    """Verify that GUI import adoption follows successful copying and database persistence."""

    def _ui(self) -> SimpleNamespace:
        """Provide only the GUI collaborators needed to run import adoption without opening a window."""
        importer = Mock()
        importer.FORMAT_NAME = "PlantUML"
        model = BaseMlmModel()
        return SimpleNamespace(
            current_model=object(), current_selected_columns=["old"], current_file_path="source.puml",
            current_file_type="XML", file_path_var=Mock(),
            action_completed={1: False}, action_unlocked={2: False},
            _importer_for_file=Mock(return_value=importer),
            _read_import_candidate=Mock(return_value=(model, ImportReport(), [])),
            _store_loaded_model=Mock(return_value=True), _show_error=Mock(), _show_model_page=Mock())

    def test_plantuml_examples_are_listed_and_already_in_source_folder(self) -> None:
        """Offer PlantUML sources and keep files already stored in the source folder."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "models" / "plantuml"
            root.mkdir(parents=True)
            path = root / "Example.txt"
            path.write_text("@startuml\nclass A\n@enduml\n", encoding="utf-8")
            self.assertEqual(ModelDeepenerApp._collect_example_files(str(root)), [(str(root), ["Example.txt"])])

    def test_import_from_external_file_never_copies_source(self) -> None:
        """Keep the original path and create no numbered files in the model folder."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'external' / 'Example.txt'
            source.parent.mkdir()
            source.write_text('@startuml\nclass A\n@enduml\n', encoding='utf-8')
            models = root / 'models' / 'plantuml'
            models.mkdir(parents=True)
            (models / 'Example.txt').write_text('@startuml\nclass B\n@enduml\n', encoding='utf-8')
            ui = self._ui()
            ui.current_file_path = str(source)
            importer = PlantUmlImporter()
            ui._importer_for_file.return_value = importer
            def read_candidate(_importer):
                model, report = importer.import_file(str(source))
                return model, report, []
            ui._read_import_candidate.side_effect = read_candidate
            with patch.object(PlantUmlImporter, 'SOURCE_FOLDER', str(models)):
                ModelDeepenerApp._create_model(ui)
                ModelDeepenerApp._create_model(ui)
            self.assertEqual([path.name for path in models.iterdir()], ['Example.txt'])
            self.assertEqual(ui.current_file_path, str(source))
            self.assertEqual(ui._store_loaded_model.call_count, 2)

    def test_failed_commit_does_not_display_candidate(self) -> None:
        """Keep the previous model and workflow when the storage helper reports a failed commit."""
        ui = self._ui()
        previous = ui.current_model
        ui._store_loaded_model.return_value = False
        ModelDeepenerApp._create_model(ui)
        self.assertIs(ui.current_model, previous)
        self.assertFalse(ui.action_completed[1])
        ui._show_model_page.assert_not_called()
        ui.file_path_var.set.assert_not_called()

    def test_successful_save_adopts_candidate_and_enables_next_step(self) -> None:
        """Display the new model after it is saved without copying the source."""
        ui = self._ui()
        candidate = ui._read_import_candidate.return_value[0]
        ModelDeepenerApp._create_model(ui)
        self.assertIs(ui.current_model, candidate)
        self.assertEqual(ui.current_file_path, "source.puml")
        ui._store_loaded_model.assert_called_once_with("PLANTUML", candidate, "source.puml", [])
        self.assertEqual(ui.current_file_type, "PLANTUML")
        self.assertTrue(ui.action_completed[1])
        self.assertTrue(ui.action_unlocked[2])
        ui._show_model_page.assert_called_once()

    def test_database_failure_removes_unsaved_candidate(self) -> None:
        """A failed real database save leaves existing objects intact and no candidate in memory."""
        with tempfile.TemporaryDirectory() as folder:
            database = DatabaseFolder(folder).create_database("Models")
            ui = SimpleNamespace(_database=database, loaded_models=[], _unique_model_name=Mock(return_value="New"),
                                 _current_timestamp_text=Mock(return_value="now"), ACTION_TITLES={2: "Imported"},
                                 _show_error=Mock())
            model = BaseMlmModel()
            with patch.object(database, "commit", side_effect=OSError("Disk full")):
                self.assertFalse(ModelDeepenerApp._store_loaded_model(ui, "CSV", model, "source.csv", []))
            self.assertEqual(database.get_all(), [])
            self.assertEqual(ui.loaded_models, [])
            ui._show_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
