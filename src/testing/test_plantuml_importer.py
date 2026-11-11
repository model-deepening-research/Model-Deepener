"""Checks the PlantUML import with small diagrams. The golden models are not part of the repository."""
import os
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
import zlib
from typing import Tuple

from src.basemlm.basemlm_model import BaseMlmModel
from src.importers import PlantUmlImporter, importer_for, supported_extensions
from src.importers.import_report import ImportReport
from src.importers.plantuml_reader import PlantUmlReader

AIR_TRAVEL = """@startuml
class FlightExecution {
    Date departure
}
class Passenger
class Ticket
FlightExecution "0..*" -- "0..*" Passenger
(FlightExecution, Passenger) .. Ticket
@enduml
"""


def png_with_text(text: str) -> bytes:
    """Build a minimal PNG file that holds the text like PlantUML does."""
    data = b"plantuml\0\x01\0\0\0" + zlib.compress(text.encode("utf-8"))
    chunk = struct.pack(">I", len(data)) + b"iTXt" + data + b"\0\0\0\0"
    return b"\x89PNG\r\n\x1a\n" + chunk + struct.pack(">I", 0) + b"IEND" + b"\0\0\0\0"


class PlantUmlImporterTests(unittest.TestCase):
    """Checks the PlantUML import with small diagrams."""

    def setUp(self) -> None:
        """Create a temporary folder for the files of one test."""
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)

    def _write(self, name: str, text: str) -> str:
        """Write a text to a file in the temporary folder and return its path."""
        path = os.path.join(self._directory.name, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as file:
            file.write(text)
        return path

    def _import(self, body: str, name: str = "m.puml") -> Tuple[BaseMlmModel, ImportReport]:
        """Import a diagram with the given body and return the model and the report."""
        path = self._write(name, f"@startuml\n{body}\n@enduml\n")
        return importer_for(path).import_file(path)

    def _adaptation_texts(self, report: ImportReport) -> list:
        """Return the descriptions of all adaptations in a report."""
        return [adaptation.get_description() for adaptation in report.get_adaptations()]

    def test_endings_are_registered(self) -> None:
        """Resolve all registered PlantUML endings, including an uppercase extension, to PlantUmlImporter."""
        self.assertEqual(supported_extensions(), [".csv", ".plantuml", ".puml", ".txt", ".xml"])
        self.assertIsInstance(importer_for("a.puml"), PlantUmlImporter)
        self.assertIsInstance(importer_for("a.PLANTUML"), PlantUmlImporter)

    def test_only_text_files_with_plantuml_are_accepted(self) -> None:
        """Accept a TXT file beginning with startuml and reject ordinary, empty and metadata text files."""
        accepted = self._write("a.txt", "\n\n  @startUML\nclass A\n@enduml\n")
        self.assertIsInstance(importer_for(accepted), PlantUmlImporter)
        for name, text in (("notes.txt", "Some notes about @startuml\n"), ("empty.txt", ""), ("metadata.txt", "x: 1\n")):
            path = self._write(name, text)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "must be a CSV, PlantUML or XML file"):
                importer_for(path)

    def test_empty_text_file_reads_the_neighbor_image(self) -> None:
        """Reject an empty source without an image and recover its Order class after adding PNG metadata."""
        path = self._write("Shop/plantuml.txt", "")
        with self.assertRaises(ValueError):
            importer_for(path)
        with open(os.path.join(os.path.dirname(path), "plantuml.png"), "wb") as file:
            file.write(png_with_text("@startuml\nclass Order\n@enduml\nPlantUML version 1"))
        model, _report = importer_for(path).import_file(path)
        self.assertEqual(model.get_model_name(), "Shop")
        self.assertEqual([obj.get_name() for obj in model.get_objects()], ["Order"])

    def test_model_name_comes_from_the_folder_or_the_file(self) -> None:
        """Use the folder for plantuml.txt and normalize punctuation in ordinary diagram filenames."""
        self.assertEqual(PlantUmlReader.get_model_name(os.path.join("x", "AirTravel", "plantuml.txt")), "AirTravel")
        self.assertEqual(PlantUmlReader.get_model_name(os.path.join("x", "my-model.puml")), "my_model")

    def test_association_class_replaces_the_association(self) -> None:
        """Split FlightExecution-Passenger through Ticket while retaining a clean import report."""
        path = self._write("AirTravel/plantuml.txt", AIR_TRAVEL)
        model, report = importer_for(path).import_file(path)
        pairs = [(a.get_source_object().get_name(), a.get_target_object().get_name()) for a in model.get_associations()]
        self.assertEqual(pairs, [("FlightExecution", "Ticket"), ("Ticket", "Passenger")])
        self.assertFalse(report.has_problems())

    def test_rules_for_classes_and_generalization(self) -> None:
        """Preserve an abstract class, typed array attributes and both spellings of child-to-parent inheritance."""
        model, _report = self._import("abstract class A {\n Int n\n String[] tags\n}\nA <|-- B\nC --|> A")
        objects = {obj.get_name(): obj for obj in model.get_objects()}
        self.assertTrue(objects["A"].is_abstract())
        self.assertEqual([p.get_name() for p in objects["B"].get_parents()], ["A"])
        self.assertEqual([p.get_name() for p in objects["C"].get_parents()], ["A"])
        attributes = {a.get_name(): a.get_attr_type() for a in objects["A"].get_regular_attributes()}
        self.assertEqual(attributes, {"n": "Integer", "tags": "String"})

    def test_relation_to_an_enum_becomes_an_attribute(self) -> None:
        """Convert Card-to-Suit into a Suit attribute and retain its Hearts and Spades literals."""
        model, _report = self._import("enum Suit <<enum>> {\n Hearts\n Spades\n}\nclass Card\nCard --> Suit")
        card = [obj for obj in model.get_objects() if obj.get_name() == "Card"][0]
        self.assertEqual([(a.get_name(), a.get_attr_type()) for a in card.get_regular_attributes()], [("suit", "Suit")])
        self.assertEqual(model.get_enum_types()[0].enum_values, ["Hearts", "Spades"])

    def test_adaptations_are_reported_and_not_structure_problems(self) -> None:
        """Report missing or unknown types, malformed bounds and lost constraints only as adaptations."""
        model, report = self._import('class A {\n name\n Foo x\n}\nA "0..1*" -- "1" B\nA <|-- C : {total; disjoint}')
        self.assertTrue(report.has_adaptations())
        self.assertTrue(report.has_problems())
        self.assertFalse(report.has_structure_problems())
        self.assertFalse(report.has_conversion_failures())
        texts = " ".join(self._adaptation_texts(report))
        for expected in ("A.name' has no type", "Unknown type 'Foo'", "Invalid multiplicity '0..1*'", "{total; disjoint}"):
            self.assertIn(expected, texts)
        self.assertEqual(len(model.get_objects()), 3)

    def test_unusual_lines_do_not_stop_the_import(self) -> None:
        """Skip malformed declarations with hints while retaining the recognizable classes."""
        lines = ["class", "class A {", "{static}", "= 5", " : ", "a(b", "(", ")", "}", "}", "<>", "<> d", "d -- ", "A -- : x",
                 "note", '"', "A <|-- A", "A -- A : <", "enum E", "A --> E : >", "A *-- ", "(A, B) .. C", "C .. (A, Z)",
                 "class B {", "x(y z w, : )", "unterminated"]
        model, report = self._import("\n".join(lines))
        self.assertGreater(len(model.get_objects()), 0)
        self.assertTrue(report.has_adaptations())

    def test_empty_diagram_gives_an_empty_model(self) -> None:
        """Read an empty PUML file without inventing any classes."""
        path = self._write("empty.puml", "")
        model, _report = importer_for(path).import_file(path)
        self.assertEqual(model.get_objects(), [])

    def test_constructor_uses_the_importer(self) -> None:
        """Construct the three AirTravel classes through the compatible model constructor."""
        path = self._write("AirTravel/plantuml.txt", AIR_TRAVEL)
        self.assertEqual(len(BaseMlmModel(path).get_objects()), 3)

    def test_converted_xml_keeps_what_the_export_loses(self) -> None:
        """Retain abstract=true and unbounded array multiplicity in the direct PlantUML XML result."""
        path = self._write("m.puml", "@startuml\nabstract class A {\n Int[] n\n}\n@enduml\n")
        root = ElementTree.fromstring(PlantUmlImporter().convert_to_xml(path))
        self.assertEqual(root.find("Model/addMetaClass").get("abstract"), "true")
        self.assertEqual(root.find("Model/addAttribute").get("multiplicity"), "Seq{0,-1,false,false}")

    def test_copy_of_the_source_holds_the_text(self) -> None:
        """Copy recovered PNG source into Shop.txt and reimport it with the same model name."""
        path = self._write("Shop/plantuml.txt", "")
        with open(os.path.join(os.path.dirname(path), "plantuml.png"), "wb") as file:
            file.write(png_with_text("@startuml\nclass Order\n@enduml"))
        importer = importer_for(path)
        self.assertEqual(importer.source_file_name(path), "Shop.txt")
        target = os.path.join(self._directory.name, "Shop.txt")
        importer.copy_source_file(path, target)
        self.assertIsInstance(importer_for(target), PlantUmlImporter)
        self.assertEqual(importer_for(target).import_file(target)[0].get_model_name(), "Shop")

    def test_problem_list_contains_the_adaptations(self) -> None:
        """Write a missing attribute type adaptation and its explanation to the exported problem CSV."""
        _model, report = self._import("class A {\n name\n}")
        target = os.path.join(self._directory.name, "list.csv")
        report.write_problem_list(target)
        with open(target, encoding="utf-8-sig") as file:
            text = file.read()
        self.assertIn("Attribute without type", text)
        self.assertIn("has no type", text)


if __name__ == "__main__":
    unittest.main()
