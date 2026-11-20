"""Tests for name conversion during model construction."""
import unittest
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

from src.basemlm.basemlm_model import BaseMlmModel
from src.importers.class_diagram import ClassDiagram, UmlAttribute, UmlEnum, EXACTLY_ONE
from src.importers.class_diagram_builder import ClassDiagramBuilder
from src.importers.model_names import normalized_name, unique_name


class ModelNameTests(unittest.TestCase):
    """Check name conversion and type references."""

    def test_name_rules(self) -> None:
        self.assertEqual(normalized_name('PassportNumber', attribute=True), 'passportNumber')
        self.assertEqual(normalized_name('Baby Clothing'), 'BabyClothing')
        self.assertEqual(normalized_name('Co-pilot', association=True), 'Co_pilot')
        self.assertEqual(normalized_name('1name'), '_1name')
        self.assertEqual(normalized_name('...'), '...')
        used: set[str] = set()
        self.assertEqual([unique_name('name', used), unique_name('name', used)], ['name', 'name1'])

    def test_builder_resolves_renamed_type(self) -> None:
        diagram = ClassDiagram('Example')
        item = diagram.get_or_create_class('Baby Clothing')
        item.add_attribute(UmlAttribute('Name', 'Baby Clothing', EXACTLY_ONE))
        item.add_attribute(UmlAttribute('name', 'String', EXACTLY_ONE))
        enum = UmlEnum('Some Enum')
        enum.add_literal('Some Value')
        diagram.add_enum(enum)
        model = BaseMlmModel()
        ClassDiagramBuilder().build(model, diagram)
        obj = model.get_all_flat_classes()[0]
        self.assertEqual(obj.get_name(), 'BabyClothing')
        attrs = obj.get_regular_attributes()
        self.assertEqual([attr.get_name() for attr in attrs], ['name', 'name1'])
        self.assertIs(attrs[0].get_type_spec(), obj)
        self.assertEqual(attrs[0].attr_type_str, 'Root::Example::BabyClothing')
        self.assertEqual(model.get_enum_types()[0].enum_values, ['SomeValue'])


    def test_inherited_attributes_are_unique(self) -> None:
        diagram = ClassDiagram('Example')
        parent = diagram.get_or_create_class('Parent')
        child = diagram.get_or_create_class('Child')
        child.add_parent('Parent')
        parent.add_attribute(UmlAttribute('Name', 'String', EXACTLY_ONE))
        child.add_attribute(UmlAttribute('name', 'String', EXACTLY_ONE))
        model = BaseMlmModel()
        ClassDiagramBuilder().build(model, diagram)
        objects = {obj.get_name(): obj for obj in model.get_objects()}
        self.assertEqual(objects['Parent'].get_regular_attributes()[0].get_name(), 'name')
        self.assertEqual(objects['Child'].get_regular_attributes()[0].get_name(), 'name1')

    def test_export_normalizes_names_and_references_without_mutating_model(self) -> None:
        diagram = ClassDiagram('Example')
        first = diagram.get_or_create_class('Baby Clothing')
        second = diagram.get_or_create_class('Child')
        second.add_parent('Baby Clothing')
        second.add_attribute(UmlAttribute('Name', 'Baby Clothing', EXACTLY_ONE))
        model = BaseMlmModel()
        ClassDiagramBuilder().build(model, diagram)
        obj = model.get_all_flat_classes()[0]
        obj.set_name('Baby Clothing')
        obj.full_name = 'Root::Example::Baby Clothing'
        child = model.get_all_flat_classes()[1]
        child.get_regular_attributes()[0].set_name('Name')
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'out.xml')
            model.export_xml(path, project_name='Root::Example')
            root = ET.parse(path).getroot()
        self.assertEqual(root.find("Model/addMetaClass[@name='BabyClothing']").get('name'), 'BabyClothing')
        self.assertEqual(root.find('Model/changeParent').get('new'), 'Root::Example::BabyClothing')
        self.assertEqual(root.find('Model/addAttribute').get('name'), 'name')
        self.assertEqual(root.find('Model/addAttribute').get('type'), 'Root::Example::BabyClothing')
        self.assertEqual(obj.get_name(), 'Baby Clothing')
        self.assertEqual(child.get_regular_attributes()[0].get_name(), 'Name')


if __name__ == '__main__':
    unittest.main()
