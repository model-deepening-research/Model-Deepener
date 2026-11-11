"""Checks the importers: finding the importer, typed slot values, and the report that import_file returns."""
import os
import tempfile
import unittest
from datetime import date
from typing import Tuple

from src.basemlm.basemlm_model import BaseMlmModel
from src.basemlm.basemlm_predefined_type import BooleanType, DateType, FloatType, IntegerType, StringType
from src.basemlm.basemlm_slot import BaseMlmSlot
from src.importers import CsvImporter, XmlImporter, importer_for, supported_extensions
from src.importers.csv_reader import CsvReader
from src.importers.import_report import ImportReport

PROJECT = "Root::T"
XML_HEAD = (f'<?xml version="1.0" encoding="UTF-8"?><XModelerPackage path="{PROJECT}" version="4"><Imports/>'
            f'<Model name="{PROJECT}">'
            f'<addMetaClass abstract="false" level="1" name="K" package="{PROJECT}"/>'
            f'<addInstance abstract="false" level="0" name="o" of="{PROJECT}::K" package="{PROJECT}"/>')
XML_TAIL = "</Model><Diagrams/></XModelerPackage>"


def typed_slot(attribute_type: str, value: str) -> str:
    """Return the XML of an attribute of the given type and of a slot with the given value."""
    return (f'<addAttribute class="{PROJECT}::K" level="0" multiplicity="Seq{{1,1,true,false}}" name="x" '
            f'package="{PROJECT}" type="{attribute_type}"/>'
            f'<changeSlotValue class="{PROJECT}::o" package="{PROJECT}" slotName="x" valueToBeParsed="{value}"/>')


class ImporterTests(unittest.TestCase):
    """Checks the importers with small files."""

    def setUp(self) -> None:
        """Create a temporary folder for the files of one test."""
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)

    def _write(self, name: str, text: str) -> str:
        """Write a text to a file in the temporary folder and return its path."""
        path = os.path.join(self._directory.name, name)
        with open(path, "w", encoding="utf-8", newline="") as file:
            file.write(text)
        return path

    def _import_slot(self, attribute_type: str, value: str) -> Tuple[BaseMlmSlot, ImportReport]:
        """Import a model with one slot and return the slot and the report."""
        path = self._write("model.xml", XML_HEAD + typed_slot(attribute_type, value) + XML_TAIL)
        model, report = importer_for(path).import_file(path)
        slot = [obj for obj in model.get_objects() if obj.get_name() == "o"][0].get_all_slots()[0]
        return slot, report

    def test_importer_is_found_by_file_ending(self) -> None:
        """Resolve CSV and uppercase XML endings to their formats and reject an unsupported PDF."""
        self.assertIsInstance(importer_for("a.csv"), CsvImporter)
        self.assertIsInstance(importer_for("a.XML"), XmlImporter)
        self.assertEqual(supported_extensions(), [".csv", ".plantuml", ".puml", ".txt", ".xml"])
        with self.assertRaisesRegex(ValueError, "must be a CSV, PlantUML or XML file"):
            importer_for("a.pdf")

    def test_valid_values_get_their_type_and_no_value_counts_as_failed(self) -> None:
        """Convert valid XML primitives and dates to Python values without reporting a mismatch."""
        cases = [
            ("Root::XCore::Integer", "42", int, 42),
            ("Root::XCore::Integer", "00123", int, 123),
            ("Root::XCore::Float", "3", float, 3.0),
            ("Root::XCore::Float", "1.5E3", float, 1500.0),
            ("Root::XCore::Boolean", "TRUE", bool, True),
            ("Root::XCore::String", "00123", str, "00123"),
            ("Root::XCore::String", "[80,97].asString()", str, "Pa"),
            ("Root::Auxiliary::Date", "Auxiliary::Date::createDate(2024, 12, 12)", date, date(2024, 12, 12)),
        ]
        for attribute_type, value, python_type, expected in cases:
            with self.subTest(attribute_type=attribute_type, value=value):
                slot, report = self._import_slot(attribute_type, value)
                self.assertIs(type(slot.get_value()), python_type)
                self.assertEqual(slot.get_value(), expected)
                self.assertFalse(slot.has_conversion_failed())
                self.assertFalse(report.has_problems())

    def test_attribute_types_are_the_classes_the_converter_checks(self) -> None:
        """Classes imported over two module paths are different classes, so every value would count as failed."""
        cases = [("Root::XCore::String", StringType), ("Root::XCore::Integer", IntegerType),
                 ("Root::XCore::Float", FloatType), ("Root::XCore::Boolean", BooleanType),
                 ("Root::Auxiliary::Date", DateType)]
        model = BaseMlmModel()
        for attribute_type, expected_class in cases:
            with self.subTest(attribute_type=attribute_type):
                self.assertIsInstance(model.parse_attribute_type(attribute_type), expected_class)

    def test_value_that_does_not_fit_is_reported_with_readable_text(self) -> None:
        """Keep an invalid integer expression as readable text while retaining its raw expression in the report."""
        slot, report = self._import_slot("Root::XCore::Integer", "[78].asString()")
        self.assertEqual(slot.get_value(), "N")
        self.assertEqual(slot.xml_value, "[78].asString()")
        self.assertTrue(slot.has_conversion_failed())
        self.assertEqual(report.get_conversion_failures()[0].get_raw_value(), "[78].asString()")

    def test_report_is_returned_and_not_kept_on_the_model(self) -> None:
        """Return an invalid XML slot in the report without adding report state to the model."""
        path = self._write("model.xml", XML_HEAD + typed_slot("Root::XCore::Integer", "abc") + XML_TAIL)
        model, report = importer_for(path).import_file(path)
        self.assertTrue(report.has_conversion_failures())
        self.assertFalse(hasattr(model, "_import_report"))
        self.assertFalse(hasattr(model, "get_import_report"))

    def test_constructor_builds_the_same_model_as_the_importer(self) -> None:
        """Create identical CSV object names through both APIs and honor the selected age column."""
        path = self._write("data.csv", "name,age\nAnna,25\nBen,31\n")
        imported, _report = importer_for(path).import_file(path)
        constructed = BaseMlmModel(path)
        self.assertEqual([obj.get_name() for obj in constructed.get_objects()],
                         [obj.get_name() for obj in imported.get_objects()])
        selected = BaseMlmModel(path, selected_csv_columns=["age"])
        self.assertEqual([attr.get_name() for attr in selected.get_objects()[0].get_all_attributes()], ["age"])

    def test_csv_values_get_the_type_of_their_column(self) -> None:
        """Keep ZIP codes as strings while converting CSV flags and counts to bool and int."""
        path = self._write("data.csv", "zip,flag,count\n00123,TRUE,1\n456,false,2\n")
        model, report = importer_for(path).import_file(path)
        first_row = model.get_objects()[1].get_all_slots()
        self.assertEqual([slot.get_value() for slot in first_row], ["00123", True, 1])
        self.assertFalse(report.has_problems())

    def test_header_check_is_in_the_reader(self) -> None:
        """Accept a name-and-age header and reject a first row that has the same data kinds as later rows."""
        self.assertTrue(CsvReader(self._write("a.csv", "name,age\nAnna,25\n")).first_row_looks_like_header())
        self.assertFalse(CsvReader(self._write("b.csv", "Anna,25,Essen\nBen,31,Duisburg\n")).first_row_looks_like_header())


if __name__ == "__main__":
    unittest.main()
