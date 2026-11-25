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
          <ownedAttribute xmi:id="endB" name="parts" type="b" association="rel" aggregation="composite"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Class" xmi:id="b" name="B"/>
        <packagedElement xsi:type="uml:Association" xmi:id="rel" name="hasParts" memberEnd="endA endB">
          <ownedEnd xmi:id="endA" name="owner" type="a"/>
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

    def test_class_typed_property_remains_attribute(self) -> None:
        """Keep a class-typed property as an attribute."""
        model, _ = self._import('''
        <packagedElement xsi:type="uml:Class" xmi:id="a" name="A">
          <ownedAttribute xmi:id="prop" name="ref" type="b" lower="0" upper="1"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Class" xmi:id="b" name="B"/>''')
        objects = {obj.name: obj for obj in model.get_objects()}
        attribute = objects['A'].get_regular_attributes()[0]
        self.assertEqual(attribute.name, 'ref')
        self.assertIs(attribute.get_type_spec(), objects['B'])
        self.assertEqual(model.get_associations(), [])

    def test_datatype_matching_unique_class_and_numeric(self) -> None:
        """Resolve matching class types and numeric without losing attribute types."""
        model, report = self._import('''
        <packagedElement xsi:type="uml:Class" xmi:id="owner" name="Owner">
          <ownedAttribute xmi:id="a" name="target" type="dt"/>
          <ownedAttribute xmi:id="n" name="amount" type="num"/>
          <ownedAttribute xmi:id="u" name="unknown" type="unknown"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Class" xmi:id="target" name="Target"/>
        <packagedElement xsi:type="uml:DataType" xmi:id="dt" name="Target"/>
        <packagedElement xsi:type="uml:DataType" xmi:id="num" name="numeric"/>
        <packagedElement xsi:type="uml:DataType" xmi:id="unknown" name="Custom"/>''')
        objects = {obj.name: obj for obj in model.get_objects()}
        attrs = {attr.name: attr for attr in objects['Owner'].get_regular_attributes()}
        self.assertIs(attrs['target'].get_type_spec(), objects['Target'])
        self.assertEqual(attrs['amount'].get_attr_type(), 'Float')
        self.assertEqual(attrs['unknown'].get_attr_type(), 'String')
        messages = [item.get_description() for item in report.get_adaptations()]
        self.assertTrue(any("datatype 'Custom' replaced by String" in msg for msg in messages))
        self.assertFalse(any("datatype 'Target'" in msg or "datatype 'numeric'" in msg for msg in messages))

    def test_datatype_with_ambiguous_class_names_keeps_string_warning(self) -> None:
        """Do not guess between same-named classes in different packages."""
        model, report = self._import('''
        <packagedElement xsi:type="uml:Package" xmi:id="p1" name="P1">
          <packagedElement xsi:type="uml:Class" xmi:id="a" name="Target"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Package" xmi:id="p2" name="P2">
          <packagedElement xsi:type="uml:Class" xmi:id="b" name="Target"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Class" xmi:id="owner" name="Owner">
          <ownedAttribute xmi:id="attr" name="target" type="dt"/>
        </packagedElement>
        <packagedElement xsi:type="uml:DataType" xmi:id="dt" name="Target"/>''')
        owner = next(obj for obj in model.get_objects() if obj.name == 'Owner')
        self.assertEqual(owner.get_regular_attributes()[0].get_attr_type(), 'String')
        self.assertTrue(any("datatype 'Target' replaced by String" in item.get_description()
                            for item in report.get_adaptations()))

    def test_numeric_datatype_prefers_same_named_class(self) -> None:
        """Use numeric as a class when there is exactly one such class."""
        model, _ = self._import('''
        <packagedElement xsi:type="uml:Class" xmi:id="owner" name="Owner">
          <ownedAttribute xmi:id="attr" name="value" type="dt"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Class" xmi:id="number" name="numeric"/>
        <packagedElement xsi:type="uml:DataType" xmi:id="dt" name="numeric"/>''')
        objects = {obj.name: obj for obj in model.get_objects()}
        self.assertIs(objects['Owner'].get_regular_attributes()[0].get_type_spec(), objects['numeric'])

    def test_unnamed_association_kinds(self) -> None:
        """Use the aggregation kind only when an association has no name."""
        model, _ = self._import('''
        <packagedElement xsi:type="uml:Class" xmi:id="a" name="A"/>
        <packagedElement xsi:type="uml:Class" xmi:id="b" name="B"/>
        <packagedElement xsi:type="uml:Association" xmi:id="r1" memberEnd="a1 b1">
          <ownedEnd xmi:id="a1" type="a"/><ownedEnd xmi:id="b1" type="b" aggregation="composite"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Association" xmi:id="r2" memberEnd="a2 b2">
          <ownedEnd xmi:id="a2" type="a"/><ownedEnd xmi:id="b2" type="b" aggregation="shared"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Association" xmi:id="r3" memberEnd="a3 b3" name="named">
          <ownedEnd xmi:id="a3" type="a"/><ownedEnd xmi:id="b3" type="b" aggregation="composite"/>
        </packagedElement>''')
        self.assertEqual([a.name for a in model.get_associations()], ['composition_of', 'aggregation_of', 'named'])

    def test_composition_whole_explicit_bounds(self) -> None:
        for bounds, expected, warning in [('', '(1..1)', False), ('lower="0" upper="1"', '(0..1)', False),
                                          ('upper="*"', '(0..*)', True), ('lower="2" upper="3"', '(2..3)', True),
                                          ('><lowerValue value="0"/><upperValue value="1"/></ownedEnd>', '(0..1)', False)]:
            with self.subTest(bounds=bounds):
                end = f'<ownedEnd xmi:id="e1" type="a" {bounds}'
                if not bounds.startswith('>'):
                    end += '/>'
                model, report = self._import(f'''
                <packagedElement xsi:type="uml:Class" xmi:id="a" name="A"/>
                <packagedElement xsi:type="uml:Class" xmi:id="b" name="B"/>
                <packagedElement xsi:type="uml:Association" xmi:id="r" memberEnd="e1 e2">
                  {end}
                  <ownedEnd xmi:id="e2" type="b" aggregation="composite" upper="*"/>
                </packagedElement>''')
                self.assertEqual(str(model.get_associations()[0].source_multiplicity), expected)
                self.assertEqual(str(model.get_associations()[0].target_multiplicity), '(0..*)')
                self.assertEqual(any(a.get_problem_type() == 'Composition whole end' for a in report.get_adaptations()), warning)

    def test_composition_bounds_in_association_class_and_nary(self) -> None:
        model, report = self._import('''
        <packagedElement xsi:type="uml:Class" xmi:id="a" name="A"/>
        <packagedElement xsi:type="uml:Class" xmi:id="b" name="B"/>
        <packagedElement xsi:type="uml:Class" xmi:id="c" name="C"/>
        <packagedElement xsi:type="uml:AssociationClass" xmi:id="m" name="Membership" memberEnd="m1 m2">
          <ownedEnd xmi:id="m1" type="a" lower="0" upper="1"/>
          <ownedEnd xmi:id="m2" type="b" aggregation="composite" upper="*"/>
        </packagedElement>
        <packagedElement xsi:type="uml:Association" xmi:id="n" memberEnd="n1 n2 n3">
          <ownedEnd xmi:id="n1" type="a" aggregation="composite"/>
          <ownedEnd xmi:id="n2" type="b"/><ownedEnd xmi:id="n3" type="c"/>
        </packagedElement>''')
        associations = model.get_associations()
        self.assertEqual(str(associations[1].source_multiplicity), '(0..1)')
        self.assertEqual(str(associations[2].target_multiplicity), '(0..*)')
        self.assertEqual(sum(a.get_problem_type() == 'Composition whole end' for a in report.get_adaptations()), 0)

    def test_composition_whole_on_right_end(self) -> None:
        model, report = self._import('''
        <packagedElement xsi:type="uml:Class" xmi:id="a" name="A"/>
        <packagedElement xsi:type="uml:Class" xmi:id="b" name="B"/>
        <packagedElement xsi:type="uml:Association" xmi:id="r" memberEnd="part whole">
          <ownedEnd xmi:id="part" type="b" aggregation="composite" upper="*"/>
          <ownedEnd xmi:id="whole" type="a" upper="2"/>
        </packagedElement>''')
        association = model.get_associations()[0]
        self.assertEqual(str(association.source_multiplicity), '(0..*)')
        self.assertEqual(str(association.target_multiplicity), '(0..2)')
        hints = [a for a in report.get_adaptations() if a.get_problem_type() == 'Composition whole end']
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0].get_object_name(), 'A')

    def test_composition_whole_on_association_class(self) -> None:
        model, report = self._import('''
        <packagedElement xsi:type="uml:Class" xmi:id="a" name="A"/>
        <packagedElement xsi:type="uml:Class" xmi:id="b" name="B"/>
        <packagedElement xsi:type="uml:AssociationClass" xmi:id="m" name="Membership" memberEnd="part whole">
          <ownedEnd xmi:id="part" type="b" aggregation="composite" upper="*"/>
          <ownedEnd xmi:id="whole" type="a" upper="2"/>
        </packagedElement>''')
        first, second = model.get_associations()
        self.assertEqual(str(first.target_multiplicity), '(0..2)')
        self.assertEqual(str(second.source_multiplicity), '(0..*)')
        self.assertEqual(sum(a.get_problem_type() == 'Composition whole end' for a in report.get_adaptations()), 1)

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
                             _persist_imported_source_file=Mock(), _database=Mock(), _show_error=Mock())
        ui._importer_for_file.return_value.import_file = Mock(return_value=(model, report))
        ui._run_model_task = lambda _total, _message, work, success, _failure: success(work(None))
        with patch('src.gui.app.ask_import_problems', return_value=True):
            ModelDeepenerApp._create_model(ui)
        ui._database.store.assert_not_called()
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
