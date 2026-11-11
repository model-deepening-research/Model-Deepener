"""Regression tests for import fidelity, independent input data and atomic GUI adoption."""
import csv
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.basemlm.basemlm_model import BaseMlmModel
from src.basemlm.basemlm_predefined_type import DateType
from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_slot import BaseMlmSlot
from src.gui.app import ModelDeepenerApp
from src.importers import CsvImporter, PlantUmlImporter, XmlImporter
from src.importers.csv_reader import CsvReader
from src.importers.import_report import ImportReport
from src.importers.model_importer import register_importer, supported_extensions
from src.importers.plantuml_diagram import UmlOperation, UmlParameter
from src.importers.plantuml_reader import parse_multiplicity
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
        root = ElementTree.fromstring(importer.convert_to_xml(path))
        _model, report = importer.import_file(path)
        return root, report

    def test_each_class_typed_attribute_keeps_its_own_role(self) -> None:
        """Turn mother and father of type Person into two distinct directed relationships."""
        root, report = self._plantuml("class Person {\n Person mother\n Person father\n}")
        associations = root.findall("Model/addAssociation")
        self.assertEqual(len(associations), 2)
        roles = []
        for association in associations:
            roles.append(association.get("accessTargetFromSourceName"))
            self.assertEqual(association.get("sourceVisibleFromTarget"), "false")
            self.assertEqual(association.get("targetVisibleFromSource"), "true")
        self.assertEqual(roles, ["mother", "father"])
        self.assertEqual(report.get_adaptations(), [])

    def test_only_matching_label_replaces_an_attribute_and_reports_it(self) -> None:
        """Drop mother only for a matching label and retain father and unrelated relationships."""
        for relation in ("Child --> Person : mother", "Person --> Child : mother"):
            with self.subTest(relation=relation):
                root, report = self._plantuml(
                    "class Child {\n Person mother\n Person father\n}\nclass Person\n" + relation)
                self.assertEqual(len(root.findall("Model/addAssociation")), 2)
                self.assertEqual(len(report.get_adaptations()), 2)
                self.assertIn("Child.mother", report.get_adaptations()[0].get_description())
        root, report = self._plantuml(
            "class Child {\n Person mother\n}\nclass Person\nChild --> Person : knows")
        self.assertEqual(len(root.findall("Model/addAssociation")), 2)
        for hint in report.get_adaptations():
            self.assertNotIn("omitted", hint.get_description())

    def test_repeated_class_attribute_is_covered_by_the_existing_role(self) -> None:
        """Keep one mother relationship and explain the repeated declaration rather than duplicating it."""
        root, report = self._plantuml("class Child {\n Person mother\n Person mother\n}\nclass Person")
        self.assertEqual(len(root.findall("Model/addAssociation")), 1)
        self.assertEqual(len(report.get_adaptations()), 1)
        self.assertIn("same role or label", report.get_adaptations()[0].get_description())

    def test_unique_unlabelled_composition_uses_the_attribute_role(self) -> None:
        """Reuse a sole composition for availability while preserving its bounds and navigation."""
        root, report = self._plantuml(
            'class Hotel {\n RoomAvailability availability\n}\nclass RoomAvailability\n'
            'Hotel "1" *-- "0..*" RoomAvailability')
        associations = root.findall("Model/addAssociation")
        self.assertEqual(len(associations), 1)
        association = associations[0]
        self.assertEqual(association.get("accessTargetFromSourceName"), "availability")
        self.assertEqual(association.get("multTargetToSource"), "Seq{1,1,true,false}")
        self.assertEqual(association.get("multSourceToTarget"), "Seq{0,-1,false,false}")
        self.assertEqual(association.get("sourceVisibleFromTarget"), "true")
        self.assertEqual(association.get("targetVisibleFromSource"), "true")
        self.assertEqual(len(report.get_adaptations()), 1)
        description = report.get_adaptations()[0].get_description()
        self.assertIn("Hotel.availability", description)
        self.assertIn("role 'availability'", description)

    def test_unique_unlabelled_reverse_association_names_the_reached_end(self) -> None:
        """Apply availability to the source end when the attribute owner is written on the right."""
        root, report = self._plantuml(
            'class Hotel {\n RoomAvailability availability\n}\nclass RoomAvailability\n'
            'RoomAvailability "0..*" <-- "1" Hotel')
        associations = root.findall("Model/addAssociation")
        self.assertEqual(len(associations), 1)
        association = associations[0]
        self.assertEqual(association.get("accessSourceFromTargetName"), "availability")
        self.assertEqual(association.get("sourceVisibleFromTarget"), "true")
        self.assertEqual(association.get("targetVisibleFromSource"), "false")
        self.assertEqual(len(report.get_adaptations()), 1)

    def test_multiple_attributes_do_not_reuse_an_unlabelled_association(self) -> None:
        """Keep mother and father distinct even after one attribute has already been removed."""
        root, report = self._plantuml(
            'class Child {\n Person mother\n Person father\n}\nclass Person\n'
            'Child "1" -- "0..*" Person')
        associations = root.findall("Model/addAssociation")
        self.assertEqual(len(associations), 3)
        self.assertEqual(associations[1].get("accessTargetFromSourceName"), "mother")
        self.assertEqual(associations[2].get("accessTargetFromSourceName"), "father")
        self.assertFalse(report.has_problems())

    def test_multiple_unlabelled_associations_do_not_absorb_an_attribute(self) -> None:
        """Add a separate mother relationship when two unlabelled relationships make reuse ambiguous."""
        root, report = self._plantuml(
            'class Child {\n Person mother\n}\nclass Person\n'
            'Child "1" -- "0..*" Person\nChild "0..1" -- "1" Person')
        associations = root.findall("Model/addAssociation")
        self.assertEqual(len(associations), 3)
        self.assertEqual(associations[2].get("accessTargetFromSourceName"), "mother")
        self.assertFalse(report.has_problems())

    def test_association_class_preserves_both_navigation_flags(self) -> None:
        """Split each arrow direction through C without enabling navigation absent from its basis."""
        cases = [("-->", "false", "true"), ("<--", "true", "false"), ("--", "true", "true")]
        for arrow, source_visible, target_visible in cases:
            with self.subTest(arrow=arrow):
                root, _report = self._plantuml(
                    f'class A\nclass B\nclass C\nA "1" {arrow} "0..*" B\n(A, B) .. C')
                associations = root.findall("Model/addAssociation")
                self.assertEqual(len(associations), 2)
                self.assertEqual(associations[0].get("classTarget"), "Root::diagram::C")
                self.assertEqual(associations[1].get("classSource"), "Root::diagram::C")
                for association in associations:
                    self.assertEqual(association.get("sourceVisibleFromTarget"), source_visible)
                    self.assertEqual(association.get("targetVisibleFromSource"), target_visible)

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
        for value in ("5..2", "*..1", "*..*", "*"):
            with self.subTest(value=value):
                self.assertIsNone(parse_multiplicity(value))
                root, report = self._plantuml(f'class A\nclass B\nA "{value}" -- "1" B')
                association = root.find("Model/addAssociation")
                self.assertEqual(association.get("multTargetToSource"), "Seq{0,-1,false,false}")
                self.assertIn("Invalid multiplicity", report.get_adaptations()[0].get_description())
        for value in ("0..*", "0..1", "2..5", "1"):
            with self.subTest(valid=value):
                self.assertIsNotNone(parse_multiplicity(value))

    def test_visibility_prefixes_do_not_change_attributes_or_operations(self) -> None:
        """Read all four visibility prefixes without putting their symbols into names or types."""
        for sign in ("+", "-", "#", "~"):
            with self.subTest(sign=sign):
                root, report = self._plantuml(
                    f"class A {{\n {sign}String name\n {sign} int count()\n {sign}String[] tags\n}}")
                attributes = root.findall("Model/addAttribute")
                self.assertEqual(attributes[0].get("name"), "name")
                self.assertEqual(attributes[0].get("type"), "Root::XCore::String")
                self.assertEqual(attributes[1].get("multiplicity"), "Seq{0,-1,false,false}")
                self.assertEqual(root.find("Model/addOperation").get("name"), "count")
                self.assertFalse(report.has_problems())

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
            _persist_imported_source_file=Mock(return_value="copy.puml"),
            _store_loaded_model=Mock(return_value=True), _show_error=Mock(), _show_model_page=Mock())

    def test_failed_source_copy_keeps_previous_model_and_workflow(self) -> None:
        """Report a source-copy error without saving or replacing any active GUI state."""
        ui = self._ui()
        previous = vars(ui).copy()
        ui._persist_imported_source_file.side_effect = OSError("Disk full")
        ModelDeepenerApp._create_model(ui)
        self.assertIs(ui.current_model, previous["current_model"])
        self.assertEqual(ui.current_selected_columns, ["old"])
        self.assertEqual(ui.current_file_path, "source.puml")
        self.assertEqual(ui.current_file_type, "XML")
        self.assertFalse(ui.action_completed[1])
        self.assertFalse(ui.action_unlocked[2])
        ui._store_loaded_model.assert_not_called()
        ui._show_model_page.assert_not_called()
        ui.file_path_var.set.assert_not_called()
        self.assertIn("Disk full", ui._show_error.call_args.args[1])

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
        """Display the new PlantUML model only after its copy and storage have succeeded."""
        ui = self._ui()
        candidate = ui._read_import_candidate.return_value[0]
        ModelDeepenerApp._create_model(ui)
        self.assertIs(ui.current_model, candidate)
        self.assertEqual(ui.current_file_path, "copy.puml")
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
