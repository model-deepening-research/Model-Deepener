"""Tests for the UML XMI importer."""
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.gui.app import ModelDeepenerApp
from src.importers import XmiImporter, importer_for

HEAD = ('<xmi:XMI xmlns:xmi="http://schema.omg.org/spec/XMI/2.1" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML"><uml:Model xmi:id="model" name="model">')
TAIL = '</uml:Model></xmi:XMI>'


class XmiImporterTests(unittest.TestCase):
    """Check supported UML model constructs and GUI registration."""

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def _import(self, text: str):
        path = Path(self.folder.name) / 'example.xmi'
        path.write_text(HEAD + text + TAIL, encoding='utf-8')
        self.assertIsInstance(importer_for(str(path)), XmiImporter)
        return XmiImporter().import_file(str(path))

    def test_types_classes_enums_and_generalizations(self) -> None:
        """Resolve local identifiers, primitive hrefs and all generalizations."""
        model, report = self._import('''
        <packagedElement xsi:type="uml:Class" xmi:id="p" name="Parent"/>
        <packagedElement xsi:type="uml:Interface" xmi:id="i" name="Contract"/>
        <packagedElement xsi:type="uml:Class" xmi:id="c" name="Child">
          <generalization xmi:id="g1" general="p"/><generalization xmi:id="g2" general="i"/>
          <ownedAttribute xmi:id="a" name="number"><type xsi:type="uml:PrimitiveType" href="http://www.omg.org/PrimitiveTypes.xmi#//UnlimitedNatural"/></ownedAttribute>
          <ownedAttribute xmi:id="b" name="color" type="e"/>
          <ownedAttribute xmi:id="d" name="other" type="dt"/>
          <ownedAttribute xmi:id="z" name="missing" type="missingID"/>
          <ownedOperation xmi:id="op" name="work"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Enumeration" xmi:id="e" name="Color"><ownedLiteral name="RED"/></packagedElement>
        <packagedElement xsi:type="uml:DataType" xmi:id="dt" name="Custom"/>
        <packagedElement xsi:type="uml:UseCase" xmi:id="u" name="Ignored"/>''')
        objects = {o.name: o for o in model.get_objects()}
        child = objects['Child']
        self.assertEqual([p.name for p in child.get_parents()], ['Parent', 'Contract'])
        self.assertTrue(objects['Contract'].is_abstract())
        self.assertEqual({a.name: a.get_attr_type() for a in child.get_regular_attributes()},
                         {'number': 'Integer', 'color': 'Color', 'other': 'String', 'missing': 'String'})
        kinds = {a.get_problem_type() for a in report.get_adaptations()}
        self.assertTrue({'Interface', 'DataType', 'Unresolved type', 'Operation skipped'} <= kinds)

    def test_association_members_composition_and_navigation(self) -> None:
        """Read both owned and class-owned ends with roles and composition bounds."""
        model, _ = self._import('''
        <packagedElement xsi:type="uml:Class" xmi:id="a" name="A">
          <ownedAttribute xmi:id="endB" name="parts" type="b" association="rel"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Class" xmi:id="b" name="B"/>
        <packagedElement xsi:type="uml:Association" xmi:id="rel" name="hasParts" memberEnd="endA endB">
          <ownedEnd xmi:id="endA" name="owner" type="a" aggregation="composite"/>
        </packagedElement>''')
        assoc = model.get_associations()[0]
        self.assertEqual((assoc.name, assoc.source_object.name, assoc.target_object.name), ('hasParts', 'A', 'B'))
        self.assertEqual((assoc.source_access_name, assoc.target_access_name), ('parts', 'owner'))
        self.assertEqual((str(assoc.source_multiplicity), str(assoc.target_multiplicity)), ('(1..1)', '(0..*)'))
        self.assertEqual(len(assoc.source_object.get_regular_attributes()), 0)
        out = os.path.join(self.folder.name, 'out.xml')
        model.export_xml(out)
        xml_assoc = ET.parse(out).getroot().find('Model/addAssociation')
        self.assertEqual((xml_assoc.get('sourceVisibleFromTarget'), xml_assoc.get('targetVisibleFromSource')), ('true', 'true'))

    def test_association_class_and_nary_association(self) -> None:
        """Transform association classes and n-ary relationships through classes."""
        model, report = self._import('''
        <packagedElement xsi:type="uml:Class" xmi:id="a" name="A"/>
        <packagedElement xsi:type="uml:Class" xmi:id="b" name="B"/>
        <packagedElement xsi:type="uml:Class" xmi:id="c" name="C"/>
        <packagedElement xsi:type="uml:AssociationClass" xmi:id="m" name="Membership" memberEnd="m1 m2">
          <ownedAttribute xmi:id="prop" name="code"><type href="http://www.omg.org/PrimitiveTypes.xmi#//String"/></ownedAttribute>
          <ownedEnd xmi:id="m1" name="a" type="a"/><ownedEnd xmi:id="m2" name="b" type="b"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Association" xmi:id="n" name="triple" memberEnd="n1 n2 n3">
          <ownedEnd xmi:id="n1" name="a" type="a"/><ownedEnd xmi:id="n2" name="b" type="b"/>
          <ownedEnd xmi:id="n3" name="c" type="c"/>
        </packagedElement>''')
        self.assertEqual(len(model.get_associations()), 5)
        self.assertIn('Membership', [o.name for o in model.get_objects()])
        self.assertIn('ABC', [o.name for o in model.get_objects()])
        self.assertTrue({'Association class', 'N-ary association'} <= {a.get_problem_type() for a in report.get_adaptations()})

    def test_no_classes_is_reported_and_gui_does_not_save(self) -> None:
        """A use-case-only XMI is reported and does not create a stored GUI model."""
        model, report = self._import('<packagedElement xsi:type="uml:UseCase" xmi:id="u" name="Use"/>')
        self.assertEqual(model.get_objects(), [])
        self.assertEqual(report.get_adaptations()[0].get_problem_type(), 'No classes')
        ui = SimpleNamespace(current_file_path='example.xmi', _importer_for_file=Mock(return_value=XmiImporter()),
                             _read_import_candidate=Mock(return_value=(model, report, [])), _overlay=Mock(),
                             _persist_imported_source_file=Mock(), _store_loaded_model=Mock(), _show_error=Mock())
        with patch('src.gui.app.ask_import_problems', return_value=True):
            ModelDeepenerApp._create_model(ui)
        ui._store_loaded_model.assert_not_called()
        ui._persist_imported_source_file.assert_not_called()

    def test_duplicate_package_classes_and_unresolved_references(self) -> None:
        """Retain package identity and keep unresolved references as String attributes."""
        model, report = self._import('''
        <packagedElement xsi:type="uml:Package" xmi:id="p1" name="first">
          <packagedElement xsi:type="uml:Class" xmi:id="a" name="Item"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Package" xmi:id="p2" name="second">
          <packagedElement xsi:type="uml:Class" xmi:id="b" name="Item">
            <generalization xmi:id="g" general="missingParent"/>
          </packagedElement>
        </packagedElement>
        <packagedElement xsi:type="uml:Association" xmi:id="rel" memberEnd="one two">
          <ownedEnd xmi:id="one" type="a"/>
          <ownedEnd xmi:id="two" name="missingEnd" type="missingType"/>
        </packagedElement>''')
        objects = {o.name: o for o in model.get_objects()}
        self.assertEqual(objects['Item'].get_regular_attributes()[0].get_attr_type(), 'String')
        self.assertEqual(objects['Item'].get_regular_attributes()[0].name, 'missingEnd')
        self.assertEqual(objects['Item1'].get_regular_attributes()[0].name, 'unresolvedParent')
        messages = [a.get_description() for a in report.get_adaptations()]
        self.assertTrue(any('second/Item' in text and 'Item1' in text for text in messages))
        self.assertTrue(any('missingType' in text for text in messages))

    def test_genmymodel_self_reference_resolves_qualified_package_path(self) -> None:
        """Resolve a GenMyModel URI only when its model UUID and package path match."""
        model, report = self._import('''
          <xmi:Extension><eAnnotations><details key="uuid" value="model-uuid"/></eAnnotations></xmi:Extension>
          <packagedElement xsi:type="uml:Package" xmi:id="p" name="transaction">
            <packagedElement xsi:type="uml:Class" xmi:id="a" name="Parent"/>
            <packagedElement xsi:type="uml:Class" xmi:id="b" name="Child">
              <generalization><general href="genmymodel://model-uuid#//transaction/Parent"/></generalization>
              <ownedAttribute xmi:id="prop" name="other"><type href="genmymodel://other-uuid#//transaction/Parent"/></ownedAttribute>
            </packagedElement>
          </packagedElement>''')
        child = next(o for o in model.get_objects() if o.name == 'Child')
        self.assertEqual([p.name for p in child.get_parents()], ['Parent'])
        self.assertEqual(child.get_regular_attributes()[0].get_attr_type(), 'String')
        self.assertTrue(any(a.get_problem_type() == 'Unresolved type' for a in report.get_adaptations()))

    def test_pathmap_primitive_types_and_unknown_types(self) -> None:
        """Map known pathmap primitive names and report unknown library types."""
        model, report = self._import('''
          <packagedElement xsi:type="uml:Class" xmi:id="a" name="A">
            <ownedAttribute xmi:id="one" name="label"><type href="pathmap://UML_LIBRARIES/UMLPrimitiveTypes.library.uml#//String"/></ownedAttribute>
            <ownedAttribute xmi:id="two" name="count"><type href="pathmap://JAVA/JavaPrimitiveTypes.library.uml#//int"/></ownedAttribute>
            <ownedAttribute xmi:id="three" name="enabled"><type href="pathmap://ECORE/Ecore.library.uml#//EBoolean"/></ownedAttribute>
            <ownedAttribute xmi:id="four" name="amount"><type href="pathmap://ECORE/Ecore.library.uml#//EDouble"/></ownedAttribute>
            <ownedAttribute xmi:id="five" name="opaque"><type href="pathmap://UML_LIBRARIES/Other.library.uml#//ByteArray"/></ownedAttribute>
          </packagedElement>''')
        attrs = {a.name: a.get_attr_type() for a in model.get_objects()[0].get_regular_attributes()}
        self.assertEqual(attrs, {'label': 'String', 'count': 'Integer', 'enabled': 'Boolean',
                                 'amount': 'Float', 'opaque': 'String'})
        kinds = [a.get_problem_type() for a in report.get_adaptations()]
        self.assertEqual(kinds.count('Pathmap primitive type'), 0)
        self.assertEqual(kinds.count('Unresolved type'), 1)

    def test_additional_pathmap_aliases_do_not_change_own_datatypes(self) -> None:
        """Limit extra library aliases to pathmap references."""
        model, report = self._import('''
          <packagedElement xsi:type="uml:DataType" xmi:id="custom" name="Time"/>
          <packagedElement xsi:type="uml:Class" xmi:id="a" name="A">
            <ownedAttribute xmi:id="one" name="own" type="custom"/>
            <ownedAttribute xmi:id="two" name="library"><type href="pathmap://JAVA/PrimitiveTypes#//Time"/></ownedAttribute>
          </packagedElement>''')
        attrs = {a.name: a.get_attr_type() for a in model.get_objects()[0].get_regular_attributes()}
        self.assertEqual(attrs, {'own': 'String', 'library': 'Date'})
        self.assertEqual({a.get_problem_type() for a in report.get_adaptations()}, {'DataType'})

    def test_associations_with_fewer_than_two_ends_are_reported(self) -> None:
        """Report incomplete associations, including those ending at a use case."""
        model, report = self._import('''
          <packagedElement xsi:type="uml:Class" xmi:id="a" name="A"/>
          <packagedElement xsi:type="uml:UseCase" xmi:id="u" name="Use"/>
          <packagedElement xsi:type="uml:Association" xmi:id="r1" name="classLink" memberEnd="e1">
            <ownedEnd xmi:id="e1" type="a"/>
          </packagedElement>
          <packagedElement xsi:type="uml:Association" xmi:id="r2" name="useLink" memberEnd="e2">
            <ownedEnd xmi:id="e2" type="u"/>
          </packagedElement>''')
        messages = [a.get_description() for a in report.get_adaptations()
                    if a.get_problem_type() == 'Invalid association']
        self.assertEqual(len(messages), 2)
        self.assertTrue(any('classLink' in message for message in messages))
        self.assertTrue(any('useLink' in message for message in messages))
        self.assertEqual(model.get_objects()[0].get_regular_attributes()[0].get_attr_type(), 'String')
