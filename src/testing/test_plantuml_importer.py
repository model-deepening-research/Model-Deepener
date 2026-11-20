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
from src.importers.plantuml_import.plantuml_reader import PlantUmlReader

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
        self.assertEqual(supported_extensions(), [".csv", ".ecore", ".plantuml", ".puml", ".txt", ".xmi", ".xml"])
        self.assertIsInstance(importer_for("a.puml"), PlantUmlImporter)
        self.assertIsInstance(importer_for("a.PLANTUML"), PlantUmlImporter)

    def test_only_text_files_with_plantuml_are_accepted(self) -> None:
        """Accept a TXT file beginning with startuml and reject ordinary, empty and metadata text files."""
        accepted = self._write("a.txt", "\n\n  @startUML\nclass A\n@enduml\n")
        self.assertIsInstance(importer_for(accepted), PlantUmlImporter)
        for name, text in (("notes.txt", "Some notes about @startuml\n"), ("empty.txt", ""), ("metadata.txt", "x: 1\n")):
            path = self._write(name, text)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "must be a CSV, Ecore, PlantUML, UML-XMI or XML file"):
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
        """Use the folder for plantuml.txt and the exact stem for other files."""
        self.assertEqual(PlantUmlReader.get_model_name(os.path.join("x", "AirTravel", "plantuml.txt")), "AirTravel")
        self.assertEqual(PlantUmlReader.get_model_name(os.path.join("x", "my-model.puml")), "my-model")
        model, _ = self._import("class A", "models/plantuml/AirTravel.txt")
        self.assertEqual(model.get_model_name(), "AirTravel")
        self.assertEqual(model.path_name, "Root::AirTravel")

    def test_primitive_type_name_conflicts_are_reported(self) -> None:
        """Report class and enum collisions even when no attribute uses them."""
        model, report = self._import("class Date\nenum String {\n X\n}\nclass A {\n Date stamp\n String text\n}")
        attrs = {a.get_name(): a for obj in model.get_objects() if obj.get_name() == "A"
                 for a in obj.get_regular_attributes()}
        self.assertEqual(attrs["stamp"].attr_type_str, "Root::Auxiliary::Date")
        self.assertEqual(attrs["text"].attr_type_str, "Root::XCore::String")
        conflicts = [a for a in report.get_adaptations() if a.get_problem_type() == "Primitive type name conflict"]
        self.assertEqual({a.get_object_name() for a in conflicts}, {"Date", "String"})
        self.assertTrue(all("takes precedence" in a.get_description() for a in conflicts))
        _, unused_report = self._import("class Boolean")
        self.assertEqual(len(unused_report.get_adaptations()), 1)

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

    def test_attribute_and_association_levels_are_integers(self) -> None:
        """Create typed attribute and association-end levels with their owners."""
        model, _ = self._import('class A {\n String name\n}\nA "1" -- "1" B')
        for obj in model.get_objects():
            self.assertIs(type(obj.level), int)
            for attr in obj.get_all_attributes():
                self.assertIs(type(attr.get_inst_level()), int)
                self.assertIs(attr.get_owner(), obj)
                self.assertTrue(attr.valid_inst_level())

    def test_role_names_are_unique_across_inheritance(self) -> None:
        """Name parent roles before child roles regardless of declaration order."""
        model, _ = self._import('class Child\nclass Parent\nclass Route\nParent <|-- Child\n'
                                'Route -- Child : dropOff\nRoute -- Parent : pickup')
        by_name = {a.name: a for a in model.get_associations()}
        self.assertEqual(by_name['pickup'].get_target_access_name(), 'route')
        self.assertEqual(by_name['dropOff'].get_target_access_name(), 'route1')
        child = next(obj for obj in model.get_objects() if obj.name == 'Child')
        self.assertTrue(child.only_unique_attribute_names())

    def test_parent_role_avoids_attributes_in_descendants(self) -> None:
        """Reserve descendant attribute names when choosing an inherited role."""
        model, _ = self._import('class Parent\nclass Child {\n String route\n}\nclass Route\n'
                                'Parent <|-- Child\nRoute -- Parent')
        association = model.get_associations()[0]
        self.assertEqual(association.get_target_access_name(), 'route1')
        child = next(obj for obj in model.get_objects() if obj.name == 'Child')
        self.assertTrue(child.only_unique_attribute_names())

    def test_sibling_roles_can_share_a_name(self) -> None:
        """Keep identical role names when no class inherits both roles."""
        model, _ = self._import('class Parent\nclass First\nclass Second\nclass Route\n'
                                'Parent <|-- First\nParent <|-- Second\nRoute -- First\nRoute -- Second')
        self.assertEqual([a.get_target_access_name() for a in model.get_associations()], ['route', 'route'])

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
        """Retain abstract=true and use exactly one for array attributes."""
        path = self._write("m.puml", "@startuml\nabstract class A {\n Int[] n\n}\n@enduml\n")
        model, report = PlantUmlImporter().import_file(path)
        output = os.path.join(self._directory.name, "export.xml")
        model.export_xml(output)
        root = ElementTree.parse(output).getroot()
        self.assertEqual(root.find("Model/addMetaClass").get("abstract"), "true")
        self.assertEqual(root.find("Model/addAttribute").get("multiplicity"), "Seq{1,1,true,false}")

    def test_type_resolution_and_class_reference(self) -> None:
        """Resolve primitives, enums, classes and unknown types in order."""
        model, report = self._import("enum Color {\n RED\n}\nclass Engine\nclass Car {\n String title\n Color color\n Engine motor\n Unknown other\n DateTime stamp\n}")
        objects = {obj.get_name(): obj for obj in model.get_objects()}
        attrs = {attr.get_name(): attr for attr in objects["Car"].get_regular_attributes()}
        self.assertIs(attrs["motor"].get_type_spec(), objects["Engine"])
        self.assertEqual(attrs["motor"].attr_type_str, f"Root::{model.get_model_name()}::Engine")
        self.assertIs(attrs["color"].get_type_spec(), model.get_enum_types()[0])
        self.assertEqual(attrs["stamp"].get_attr_type(), "Date")
        self.assertEqual(attrs["other"].get_attr_type(), "String")
        self.assertTrue(any("Unknown type 'Unknown'" in a.get_description() for a in report.get_adaptations()))
        self.assertEqual(model.get_associations(), [])

    def test_ebike_frame_remains_class_typed_attribute(self) -> None:
        """Keep the Frame property as an attribute in the EBike example."""
        model, _ = PlantUmlImporter().import_file(os.path.join('models', 'plantuml', 'Ebike.txt'))
        objects = {obj.name: obj for obj in model.get_objects()}
        frame = next(attr for attr in objects['EBike'].get_regular_attributes() if attr.name == 'frame')
        self.assertIs(frame.get_type_spec(), objects['Frame'])

    def test_type_precedence_with_name_collisions(self) -> None:
        """Prefer primitives to enums and enums to classes with the same name."""
        model, _ = self._import("enum String {\n X\n}\nenum Shared {\n Y\n}\nclass Shared\nclass A {\n String title\n Shared value\n}")
        attrs = {a.get_name(): a for o in model.get_objects() if o.get_name() == "A" for a in o.get_regular_attributes()}
        self.assertEqual(attrs["title"].attr_type_str, "Root::XCore::String")
        self.assertIs(attrs["value"].get_type_spec(), next(e for e in model.get_enum_types() if e.get_name() == "Shared1"))

    def test_reading_direction_and_default_association_name(self) -> None:
        """Use the label direction and ignore arrowheads for exported navigation."""
        model, _ = self._import('A "1" --> "0..*" B : travels <\nB <-- C : drives >\nC -- D')
        first, second, third = model.get_associations()
        self.assertEqual((first.get_source_object().get_name(), first.get_target_object().get_name(), first.get_name()),
                         ("B", "A", "travels"))
        self.assertEqual((first.source_multiplicity.get_lower_bound(), first.target_multiplicity.get_lower_bound()), (0, 1))
        self.assertEqual((second.get_source_object().get_name(), second.get_target_object().get_name(), second.get_name()),
                         ("B", "C", "drives"))
        self.assertEqual(third.get_name(), "associated_to")
        target = os.path.join(self._directory.name, "direction.xml")
        model.export_xml(target)
        for association in ElementTree.parse(target).getroot().findall("Model/addAssociation"):
            self.assertEqual(association.get("sourceVisibleFromTarget"), "true")
            self.assertEqual(association.get("targetVisibleFromSource"), "true")

    def test_arrow_direction_and_association_default_names(self) -> None:
        """Use label direction first, then arrowheads, and retain relationship kinds."""
        model, _ = self._import("A <-- B\nC --> D\nE -- F\nG <-- H : label >\n"
                                "I --> J : label <\nK o-- L\nM --* N\nO *-- P : named")
        associations = model.get_associations()
        self.assertEqual([(a.source_object.name, a.target_object.name, a.name) for a in associations], [
            ('B', 'A', 'associated_to'), ('C', 'D', 'associated_to'),
            ('E', 'F', 'associated_to'), ('G', 'H', 'label'),
            ('J', 'I', 'label'), ('K', 'L', 'aggregation_of'),
            ('M', 'N', 'composition_of'), ('O', 'P', 'named')])
        for association in associations:
            self.assertEqual(association.xml_attributes['sourceVisibleFromTarget'], 'true')
            self.assertEqual(association.xml_attributes['targetVisibleFromSource'], 'true')

    def test_operations_and_arrays_reported(self) -> None:
        """Skip all operations with one hint and report each array."""
        model, report = self._import("class A {\n String[] tags\n int f()\n int g()\n}")
        hints = [a.get_description() for a in report.get_adaptations()]
        self.assertEqual(sum("Operations are skipped" in h for h in hints), 1)
        self.assertTrue(any("[]" in h for h in hints))
        self.assertEqual(str(model.get_objects()[0].get_regular_attributes()[0].multiplicity), "(1..1)")

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
