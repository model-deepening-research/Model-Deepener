"""Preserve abstract flags and XModeler value bounds through import and export."""
import contextlib
import io
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from src.basemlm.basemlm_model import BaseMlmModel
from src.basemlm.multiplicity import Multiplicity
from src.importers import CsvImporter, PlantUmlImporter, XmlImporter
from src.object_database.folder import DatabaseFolder
from src.object_database.persistent import Persistent


class MultiplicityRoundTripTests(unittest.TestCase):
    """Check actual model state as well as the XML emitted by the public export entry point."""

    def setUp(self) -> None:
        """Keep every source, export and database in an independent temporary directory."""
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self._folder = Path(self._directory.name)

    def _write(self, name: str, text: str) -> str:
        """Create a source fixture without modifying the repository's example models."""
        path = self._folder / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def _export(self, model: BaseMlmModel) -> tuple[ElementTree.Element, BaseMlmModel]:
        """Export to the original package path and reimport the resulting XML file."""
        path = str(self._folder / "export.xml")
        with contextlib.redirect_stdout(io.StringIO()):
            model.export_xml(path, project_name=model.path_name)
        root = ElementTree.parse(path).getroot()
        reimported, report = XmlImporter().import_file(path)
        self.assertFalse(report.has_problems())
        return root, reimported

    def test_attribute_seq_flag_means_has_upper_bound(self) -> None:
        """Read finite true bounds as bounded and false or -1 bounds as unbounded."""
        cases = [
            ("Seq{1,1,true,false}", 1, 1, False),
            ("Seq{0,1,true,false}", 0, 1, False),
            ("Seq{2,5,true,false}", 2, 5, False),
            ("Seq{0,-1,false,false}", 0, -1, True),
            ("Seq{1,5,false,false}", 1, -1, True),
            ("Seq{0,-1,true,false}", 0, -1, True),
        ]
        for text, lower, upper, unbounded in cases:
            with self.subTest(text=text):
                parsed = XmlImporter._parse_attribute_multiplicity(text)
                self.assertEqual(parsed.get_lower_bound(), lower)
                self.assertEqual(parsed.get_upper_bound(), upper)
                self.assertEqual(parsed.is_unbounded(), unbounded)
                self.assertEqual(XmlImporter._association_bounds(text), (lower, upper))
        parsed = XmlImporter._parse_attribute_multiplicity("Seq{1,1,true,false}")
        self.assertTrue(parsed.is_exactly_one())
        self.assertEqual(str(parsed), "(1..1)")

    def test_plantuml_abstractness_and_attribute_bounds_survive_export(self) -> None:
        """Keep an abstract class and its String array unbounded after a complete round trip."""
        path = self._write("classes.puml", "@startuml\nabstract class A {\n String[] tags\n int count\n}\n"
                           "class B\nA -- B\n@enduml\n")
        model, _report = PlantUmlImporter().import_file(path)
        count = model.get_objects()[0].get_regular_attributes()[1].multiplicity
        self.assertEqual(str(count), "(1..1)")
        self.assertFalse(count.is_unbounded())
        root, reimported = self._export(model)
        classes = root.findall("Model/addMetaClass")
        self.assertEqual(classes[0].get("abstract"), "true")
        self.assertEqual(classes[1].get("abstract"), "false")
        self.assertTrue(reimported.get_objects()[0].is_abstract())
        attributes = root.findall("Model/addAttribute")
        self.assertEqual(attributes[0].get("multiplicity"), "Seq{0,-1,false,false}")
        self.assertEqual(attributes[1].get("multiplicity"), "Seq{1,1,true,false}")
        imported_attributes = reimported.get_objects()[0].get_regular_attributes()
        self.assertTrue(imported_attributes[0].multiplicity.is_unbounded())
        self.assertFalse(imported_attributes[1].multiplicity.is_unbounded())

    def test_xml_attribute_and_association_bounds_survive_export(self) -> None:
        """Preserve optional, finite-range and unbounded attributes and both association ends."""
        path = self._write("bounds.xml", '''<XModelerPackage path="Root::T"><Model>
<addMetaClass package="Root::T" name="A" level="1" abstract="true"/>
<addMetaClass package="Root::T" name="B" level="1" abstract="false"/>
<addAttribute package="Root::T" class="Root::T::A" name="optional" level="0"
 type="Root::XCore::String" multiplicity="Seq{0,1,true,false}"/>
<addAttribute package="Root::T" class="Root::T::A" name="finite" level="0"
 type="Root::XCore::String" multiplicity="Seq{2,5,true,false}"/>
<addAttribute package="Root::T" class="Root::T::A" name="many" level="0"
 type="Root::XCore::String" multiplicity="Seq{1,-1,false,false}"/>
<addAssociation package="Root::T" fwName="rel" classSource="Root::T::A" classTarget="Root::T::B"
 instLevelSource="0" instLevelTarget="0" accessTargetFromSourceName="b" accessSourceFromTargetName="a"
 multTargetToSource="Seq{1,1,true,false}" multSourceToTarget="Seq{0,9,false,false}"/>
</Model></XModelerPackage>''')
        model, report = XmlImporter().import_file(path)
        self.assertFalse(report.has_problems())
        association = model.get_associations()[0]
        self.assertFalse(association.source_multiplicity.is_unbounded())
        self.assertTrue(association.target_multiplicity.is_unbounded())
        self.assertEqual(association.target_multiplicity.get_upper_bound(), -1)
        _root, reimported = self._export(model)
        attrs = reimported.get_objects()[0].get_regular_attributes()
        self.assertEqual(str(attrs[0].multiplicity), "(0..1)")
        self.assertEqual(str(attrs[1].multiplicity), "(2..5)")
        self.assertEqual(str(attrs[2].multiplicity), "(1..*)")
        association = reimported.get_associations()[0]
        self.assertEqual(str(association.source_multiplicity), "(1..1)")
        self.assertEqual(str(association.target_multiplicity), "(0..*)")

    def test_new_association_export_uses_has_upper_bound(self) -> None:
        """Write correct Seq flags even when an association has no original XML metadata to reuse."""
        path = self._write("new.puml", '@startuml\nA "1" -- "0..*" B\n@enduml\n')
        model, _report = PlantUmlImporter().import_file(path)
        model.get_associations()[0].xml_attributes = None
        root, reimported = self._export(model)
        relationship = root.find("Model/addAssociation")
        self.assertEqual(relationship.get("multTargetToSource"), "Seq{1,1,true,false}")
        self.assertEqual(relationship.get("multSourceToTarget"), "Seq{0,-1,false,false}")
        self.assertFalse(reimported.get_associations()[0].source_multiplicity.is_unbounded())

    def test_csv_attribute_without_multiplicity_exports_as_exactly_one(self) -> None:
        """Assign the specified 1..1 export default to CSV attributes without stored bounds."""
        model, _report = CsvImporter().import_file(self._write("data.csv", "name\nAlice\n"))
        self.assertIsNone(model.get_objects()[0].get_regular_attributes()[0].multiplicity)
        root, reimported = self._export(model)
        self.assertEqual(root.find("Model/addAttribute").get("multiplicity"), "Seq{1,1,true,false}")
        self.assertFalse(reimported.get_objects()[0].get_regular_attributes()[0].multiplicity.is_unbounded())

    def test_saved_old_bound_flags_are_not_reparsed_when_opening_a_database(self) -> None:
        """Demonstrate that an old stored 1..1 value marked unbounded requires reimport or repair."""
        model, _report = CsvImporter().import_file(self._write("old.csv", "name\nAlice\n"))
        model.get_objects()[0].get_regular_attributes()[0].multiplicity = Multiplicity(1, 1, unbound=True)
        database_folder = DatabaseFolder(str(self._folder))
        database = database_folder.create_database("Old")
        stored = Persistent()
        stored.model = model
        database.store(stored)
        database.commit()
        restored = database_folder.open_database("Old").get(stored.get_oid()).model
        self.assertTrue(restored.get_objects()[0].get_regular_attributes()[0].multiplicity.is_unbounded())


if __name__ == "__main__":
    unittest.main()
