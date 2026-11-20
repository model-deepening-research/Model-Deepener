"""Tests for Ecore imports and the shared class diagram."""
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from src.importers import EcoreImporter, PlantUmlImporter, importer_for
from src.gui.app import ModelDeepenerApp

HEAD = ('<ecore:EPackage xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:ecore="http://www.eclipse.org/emf/2002/Ecore" name="demo">')
TAIL = '</ecore:EPackage>'


class EcoreImporterTests(unittest.TestCase):
    """Exercise Ecore types, references, inheritance and reporting."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def _import(self, text: str):
        path = Path(self.directory.name) / 'sample.ecore'
        path.write_text(HEAD + text + TAIL, encoding='utf-8')
        self.assertIsInstance(importer_for(str(path)), EcoreImporter)
        return EcoreImporter().import_file(str(path))

    def test_reference_rules_and_containment_precedence(self) -> None:
        """Pair opposites once and preserve containment and single and many references."""
        model, report = self._import('''
        <eClassifiers xsi:type="ecore:EClass" name="A">
          <eStructuralFeatures xsi:type="ecore:EReference" name="contained" eType="#//B" containment="true" eOpposite="#//B/parent" upperBound="-1"/>
          <eStructuralFeatures xsi:type="ecore:EReference" name="single" eType="#//B"/>
          <eStructuralFeatures xsi:type="ecore:EReference" name="many" eType="#//B" upperBound="-1"/>
          <eStructuralFeatures xsi:type="ecore:EReference" name="missing" eType="other.ecore#//Lost"/>
        </eClassifiers>
        <eClassifiers xsi:type="ecore:EClass" name="B">
          <eStructuralFeatures xsi:type="ecore:EReference" name="parent" eType="#//A" eOpposite="#//A/contained"/>
        </eClassifiers>''')
        objects = {obj.name: obj for obj in model.get_objects()}
        attrs = {a.name: a for a in objects['A'].get_regular_attributes()}
        self.assertNotIn('single', attrs)
        self.assertEqual(attrs['missing'].get_attr_type(), 'String')
        self.assertTrue(any('other.ecore#//Lost' in a.get_description() for a in report.get_adaptations()))
        self.assertEqual(len(model.get_associations()), 3)
        contained, single, many = model.get_associations()
        self.assertEqual((single.source_object.name, single.target_object.name, single.source_access_name), ('A', 'B', 'single'))
        self.assertEqual(str(single.target_multiplicity), '(0..1)')
        self.assertEqual((contained.source_object.name, contained.target_object.name), ('A', 'B'))
        self.assertEqual((contained.source_access_name, contained.target_access_name), ('contained', 'parent'))
        self.assertEqual(str(contained.source_multiplicity), '(1..1)')
        self.assertEqual(str(contained.target_multiplicity), '(0..*)')
        self.assertEqual((many.source_access_name, many.target_access_name), ('many', 'a1'))
        out = os.path.join(self.directory.name, 'out.xml')
        model.export_xml(out, project_name='Root::sample')
        associations = ET.parse(out).getroot().findall('Model/addAssociation')
        self.assertEqual([assoc.get('fwName') for assoc in associations], ['composition_of', 'associated_to', 'associated_to'])
        for assoc in associations:
            self.assertEqual(assoc.get('sourceVisibleFromTarget'), 'true')
            self.assertEqual(assoc.get('targetVisibleFromSource'), 'true')

    def test_reciprocal_references_require_eopposite(self) -> None:
        """Keep unrelated reciprocal references separate and pair explicit opposites."""
        model, _ = self._import('''
        <eClassifiers xsi:type="ecore:EClass" name="A">
          <eStructuralFeatures xsi:type="ecore:EReference" name="b" eType="#//B" lowerBound="0" upperBound="1"/>
          <eStructuralFeatures xsi:type="ecore:EReference" name="pairedB" eType="#//B" eOpposite="#//B/pairedA"/>
        </eClassifiers>
        <eClassifiers xsi:type="ecore:EClass" name="B">
          <eStructuralFeatures xsi:type="ecore:EReference" name="a" eType="#//A" lowerBound="1" upperBound="1"/>
          <eStructuralFeatures xsi:type="ecore:EReference" name="pairedA" eType="#//A" eOpposite="#//A/pairedB"/>
        </eClassifiers>''')
        associations = model.get_associations()
        self.assertEqual(len(associations), 3)
        by_role = {a.source_access_name: a for a in associations}
        self.assertEqual(str(by_role['b'].target_multiplicity), '(0..1)')
        self.assertEqual(str(by_role['a1'].target_multiplicity), '(1..1)')
        self.assertEqual((by_role['b'].source_object.name, by_role['b'].target_object.name), ('A', 'B'))
        self.assertEqual((by_role['a1'].source_object.name, by_role['a1'].target_object.name), ('B', 'A'))
        self.assertEqual(by_role['pairedB'].target_access_name, 'pairedA')
        self.assertTrue(all(not obj.get_regular_attributes() for obj in model.get_objects()))

    def test_containment_whole_explicit_bounds(self) -> None:
        for bounds, expected, warning in [('', '(1..1)', False), ('lowerBound="0" upperBound="1"', '(0..1)', False),
                                          ('upperBound="-1"', '(0..*)', True), ('lowerBound="2" upperBound="3"', '(2..3)', True)]:
            with self.subTest(bounds=bounds):
                model, report = self._import(f'''
                <eClassifiers xsi:type="ecore:EClass" name="A">
                  <eStructuralFeatures xsi:type="ecore:EReference" name="parts" eType="#//B" containment="true" eOpposite="#//B/owner" upperBound="-1"/>
                </eClassifiers><eClassifiers xsi:type="ecore:EClass" name="B">
                  <eStructuralFeatures xsi:type="ecore:EReference" name="owner" eType="#//A" {bounds}/>
                </eClassifiers>''')
                self.assertEqual(str(model.get_associations()[0].source_multiplicity), expected)
                self.assertEqual(any(a.get_problem_type() == 'Composition whole end' for a in report.get_adaptations()), warning)

    def test_types_packages_multiple_parents_and_operations(self) -> None:
        """Resolve duplicate package names, enums and all parent classes."""
        model, report = self._import('''
        <eClassifiers xsi:type="ecore:EClass" name="Parent"/>
        <eClassifiers xsi:type="ecore:EClass" name="Other"/>
        <eClassifiers xsi:type="ecore:EClass" name="Child" interface="true" eSuperTypes="#//Parent #//Other">
          <eStructuralFeatures xsi:type="ecore:EAttribute" name="text" eType="ecore:EDataType http://www.eclipse.org/emf/2002/Ecore#//EString"/>
          <eStructuralFeatures xsi:type="ecore:EAttribute" name="color" eType="#//Color"/>
          <eStructuralFeatures xsi:type="ecore:EAttribute" name="custom" eType="#//Custom"/>
          <eOperations name="work"/>
        </eClassifiers>
        <eClassifiers xsi:type="ecore:EEnum" name="Color"><eLiterals name="RED"/></eClassifiers>
        <eClassifiers xsi:type="ecore:EDataType" name="Custom"/>
        <eSubpackages name="sub"><eClassifiers xsi:type="ecore:EClass" name="Parent"/>
          <eClassifiers xsi:type="ecore:EClass" name="Holder"><eStructuralFeatures xsi:type="ecore:EReference" name="item" eType="#//sub/Parent"/></eClassifiers>
        </eSubpackages>''')
        objects = {o.name: o for o in model.get_objects()}
        child = objects['Child']
        self.assertEqual([p.name for p in child.get_parents()], ['Parent', 'Other'])
        self.assertTrue(child.is_abstract())
        self.assertEqual([(a.source_object.name, a.target_object.name) for a in model.get_associations()], [('Holder', 'Parent1')])
        self.assertEqual({a.name: a.get_attr_type() for a in child.get_regular_attributes()},
                         {'text': 'String', 'color': 'Color', 'custom': 'String'})
        kinds = {a.get_problem_type() for a in report.get_adaptations()}
        self.assertTrue({'Interface', 'EDataType', 'Operation skipped', 'Duplicate classifier name'} <= kinds)
        out = os.path.join(self.directory.name, 'out.xml')
        model.export_xml(out, project_name='Root::sample')
        parents = [e.get('new') for e in ET.parse(out).getroot().findall('Model/changeParent') if e.get('class') == 'Root::sample::Child']
        self.assertEqual(parents, ['Root::sample::Parent', 'Root::sample::Other'])

    def test_plantuml_multiple_parents_are_kept(self) -> None:
        """Keep both PlantUML generalizations."""
        path = Path(self.directory.name) / 'multi.puml'
        path.write_text('@startuml\nA <|-- C\nB <|-- C\n@enduml\n', encoding='utf-8')
        model, _ = PlantUmlImporter().import_file(str(path))
        child = next(o for o in model.get_objects() if o.name == 'C')
        self.assertEqual([p.name for p in child.get_parents()], ['A', 'B'])

    def test_inferred_opposite_and_unresolved_opposite(self) -> None:
        """Pair a one-sided opposite declaration and keep broken links as text."""
        model, report = self._import('''
        <eClassifiers xsi:type="ecore:EClass" name="A">
          <eStructuralFeatures xsi:type="ecore:EReference" name="parts" eType="#//B" containment="true" upperBound="-1"/>
          <eStructuralFeatures xsi:type="ecore:EReference" name="broken" eType="#//B" eOpposite="#//Missing/x"/>
        </eClassifiers>
        <eClassifiers xsi:type="ecore:EClass" name="B">
          <eStructuralFeatures xsi:type="ecore:EReference" name="owner" eType="#//A" eOpposite="#//A/parts"/>
        </eClassifiers>''')
        self.assertEqual(len(model.get_associations()), 1)
        association = model.get_associations()[0]
        self.assertEqual((association.source_access_name, association.target_access_name), ('parts', 'owner'))
        self.assertEqual(str(association.source_multiplicity), '(1..1)')
        owner = next(o for o in model.get_objects() if o.name == 'A')
        self.assertEqual([(a.name, a.get_attr_type()) for a in owner.get_regular_attributes()], [('broken', 'String')])
        self.assertTrue(any('#//Missing/x' in a.get_description() for a in report.get_adaptations()))

    def test_generic_supertype_and_inherited_role_collision(self) -> None:
        """Resolve generic parent classifiers and avoid role collisions with inherited properties."""
        model, _ = self._import('''
        <eClassifiers xsi:type="ecore:EClass" name="Parent">
          <eStructuralFeatures xsi:type="ecore:EReference" name="route" eType="#//Route" upperBound="-1"/>
        </eClassifiers>
        <eClassifiers xsi:type="ecore:EClass" name="Child">
          <eGenericSuperTypes eClassifier="#//Parent"/>
          <eStructuralFeatures xsi:type="ecore:EReference" name="route" eType="#//Route" upperBound="-1"/>
        </eClassifiers>
        <eClassifiers xsi:type="ecore:EClass" name="Route"/>''')
        child = next(o for o in model.get_objects() if o.name == 'Child')
        self.assertEqual([p.name for p in child.get_parents()], ['Parent'])
        self.assertTrue(child.only_unique_attribute_names())
        self.assertEqual([a.source_access_name for a in model.get_associations()], ['route', 'route1'])

    def test_multiple_inheritance_reserves_roles_from_all_parents(self) -> None:
        """Keep child roles distinct from both inherited role names."""
        model, _ = self._import('''
        <eClassifiers xsi:type="ecore:EClass" name="First">
          <eStructuralFeatures xsi:type="ecore:EReference" name="firstRoute" eType="#//Route" upperBound="-1"/>
        </eClassifiers>
        <eClassifiers xsi:type="ecore:EClass" name="Second">
          <eStructuralFeatures xsi:type="ecore:EReference" name="secondRoute" eType="#//Route" upperBound="-1"/>
        </eClassifiers>
        <eClassifiers xsi:type="ecore:EClass" name="Child" eSuperTypes="#//First #//Second">
          <eStructuralFeatures xsi:type="ecore:EReference" name="secondRoute" eType="#//Route" upperBound="-1"/>
        </eClassifiers>
        <eClassifiers xsi:type="ecore:EClass" name="Route"/>''')
        child = next(o for o in model.get_objects() if o.name == 'Child')
        self.assertTrue(child.only_unique_attribute_names())
        self.assertEqual([a.source_access_name for a in model.get_associations()],
                         ['firstRoute', 'secondRoute', 'secondRoute1'])

    def test_gui_accepts_ecore_for_import_and_xml_export(self) -> None:
        """Offer Ecore files and permit their model import from the GUI."""
        path = Path(self.directory.name) / 'gui.ecore'
        path.write_text(HEAD + '<eClassifiers xsi:type="ecore:EClass" name="A"/>' + TAIL, encoding='utf-8')
        ui = SimpleNamespace(current_file_path=str(path), _importer_for_file=ModelDeepenerApp._importer_for_file)
        self.assertTrue(ModelDeepenerApp._can_create_current_file(ui))
        self.assertTrue(any('*.ecore' in patterns for _name, patterns in ModelDeepenerApp._import_file_types()))

    def test_indexed_roots_local_ids_and_opposites_keep_package_identity(self) -> None:
        """Resolve root indexes and local XMI identifiers without merging equal class names."""
        path = Path(self.directory.name) / 'packages.ecore'
        path.write_text('''<xmi:XMI xmlns:xmi="http://www.omg.org/XMI"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xmlns:ecore="http://www.eclipse.org/emf/2002/Ecore">
          <ecore:EPackage name="first">
            <eClassifiers xsi:type="ecore:EClass" name="Node" xmi:id="nodeA">
              <eStructuralFeatures xsi:type="ecore:EReference" name="link" eType="#/1/Node" eOpposite="#/1/Node/back" upperBound="-1"/>
            </eClassifiers>
          </ecore:EPackage>
          <ecore:EPackage name="second">
            <eClassifiers xsi:type="ecore:EClass" name="Node" xmi:id="nodeB">
              <eStructuralFeatures xsi:type="ecore:EReference" name="back" eType="nodeA" eOpposite="#/0/Node/link"/>
            </eClassifiers>
            <eClassifiers xsi:type="ecore:EClass" name="Holder" eSuperTypes="nodeB">
              <eStructuralFeatures xsi:type="ecore:EReference" name="local" eType="//Node"/>
              <eStructuralFeatures xsi:type="ecore:EReference" name="first" eType="#/0/Node"/>
            </eClassifiers>
          </ecore:EPackage>
        </xmi:XMI>''', encoding='utf-8')
        model, report = EcoreImporter().import_file(str(path))
        objects = {o.name: o for o in model.get_objects()}
        self.assertEqual([p.name for p in objects['Holder'].get_parents()], ['Node1'])
        attrs = {a.name: a for a in objects['Holder'].get_regular_attributes()}
        self.assertEqual(attrs, {})
        self.assertEqual({(a.source_object.name, a.target_object.name) for a in model.get_associations()},
                         {('Holder', 'Node1'), ('Holder', 'Node'), ('Node', 'Node1')})
        self.assertEqual(len(model.get_associations()), 3)
        self.assertEqual((model.get_associations()[0].source_object.name,
                          model.get_associations()[0].target_object.name), ('Node', 'Node1'))
        descriptions = [a.get_description() for a in report.get_adaptations()]
        self.assertTrue(any('second/Node' in d and 'Node1' in d for d in descriptions))
        self.assertFalse(any('Unresolved reference' == a.get_problem_type() for a in report.get_adaptations()))

    def test_local_and_external_datatypes_map_to_primitives(self) -> None:
        """Map declared local and external primitive datatypes and report the mapping."""
        model, report = self._import('''
          <eClassifiers xsi:type="ecore:EDataType" name="Real"/>
          <eClassifiers xsi:type="ecore:EClass" name="A">
            <eStructuralFeatures xsi:type="ecore:EAttribute" name="local" eType="#//Real"/>
            <eStructuralFeatures xsi:type="ecore:EAttribute" name="external" eType="ecore:EDataType types.ecore#//Integer"/>
            <eStructuralFeatures xsi:type="ecore:EAttribute" name="externalUnqualified" eType="types.ecore#//Boolean"/>
          </eClassifiers>''')
        attrs = {a.name: a.get_attr_type() for a in model.get_objects()[0].get_regular_attributes()}
        self.assertEqual(attrs, {'local': 'Float', 'external': 'Integer', 'externalUnqualified': 'Boolean'})
        self.assertEqual(sum(a.get_problem_type() == 'Datatype mapped to primitive' for a in report.get_adaptations()), 3)

    def test_unspecified_multiplicity_is_zero_to_many_without_invalid_warning(self) -> None:
        """Interpret upperBound -2 as unspecified and use zero to many."""
        model, report = self._import('''
          <eClassifiers xsi:type="ecore:EClass" name="A">
            <eStructuralFeatures xsi:type="ecore:EReference" name="items" eType="#//B" upperBound="-2"/>
          </eClassifiers>
          <eClassifiers xsi:type="ecore:EClass" name="B"/>''')
        self.assertEqual(str(model.get_associations()[0].target_multiplicity), '(0..*)')
        self.assertFalse(any(a.get_problem_type() == 'Invalid multiplicity' for a in report.get_adaptations()))
