"""Read Ecore metamodels into the shared class diagram."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import unquote
import xml.etree.ElementTree as ET

from src.importers.class_diagram import ClassDiagram, UmlAssociation, UmlAttribute, UmlEnum, UmlMultiplicity, EXACTLY_ONE, ZERO_TO_MANY, lower_first
from src.importers.class_diagram_normalizer import ClassDiagramNormalizer

XSI_TYPE = '{http://www.w3.org/2001/XMLSchema-instance}type'
XMI_ID = '{http://www.omg.org/XMI}id'
ECORE_URI = 'http://www.eclipse.org/emf/2002/Ecore'
XMLTYPE_URI = 'http://www.eclipse.org/emf/2003/XMLType'
PRIMITIVES = {
    'estring': 'String', 'echar': 'String', 'echaracterobject': 'String',
    'eint': 'Integer', 'eintegerobject': 'Integer', 'elong': 'Integer', 'elongobject': 'Integer',
    'eshort': 'Integer', 'eshortobject': 'Integer', 'ebyte': 'Integer', 'ebyteobject': 'Integer',
    'ebiginteger': 'Integer', 'edouble': 'Float', 'edoubleobject': 'Float', 'efloat': 'Float',
    'efloatobject': 'Float', 'ebigdecimal': 'Float', 'eboolean': 'Boolean', 'ebooleanobject': 'Boolean',
    'edate': 'Date', 'string': 'String', 'int': 'Integer', 'integer': 'Integer', 'long': 'Integer',
    'short': 'Integer', 'byte': 'Integer', 'biginteger': 'Integer', 'char': 'String',
    'double': 'Float', 'float': 'Float', 'real': 'Float', 'decimal': 'Float', 'bigdecimal': 'Float',
    'boolean': 'Boolean', 'date': 'Date', 'datetime': 'Date', 'time': 'Date',
}


@dataclass
class Reference:
    """An Ecore reference and its owning class."""
    owner: str
    path: str
    element: ET.Element
    root_index: int


class EcoreReader:
    """Read Ecore packages, classifiers and references."""

    def __init__(self, path: str) -> None:
        """Prepare a reader for one file."""
        self._path = Path(path)
        self._diagram = ClassDiagram(self._path.stem)
        self._classifiers: dict[str, tuple[str, str]] = {}
        self._elements: list[tuple[ET.Element, str, str, int]] = []
        self._references: list[Reference] = []
        self._ref_paths: dict[str, Reference] = {}
        self._used_names: set[str] = set()

    def read_diagram(self) -> ClassDiagram:
        """Read and resolve all packages and their references."""
        root = ET.parse(self._path).getroot()
        packages = [root] if root.tag.split('}')[-1] == 'EPackage' else [e for e in root if e.tag.split('}')[-1] == 'EPackage']
        for index, package in enumerate(packages):
            self._read_package(package, '', index, package.get('name', f'package{index}'))
        for element, name, path, root_index in self._elements:
            if self._kind(element) == 'EClass':
                self._read_class(element, name, path, root_index)
        self._read_references()
        return self._diagram

    @staticmethod
    def _kind(element: ET.Element) -> str:
        """Return the classifier or feature kind."""
        return element.get(XSI_TYPE, '').split(':')[-1]

    def _read_package(self, package: ET.Element, prefix: str, root_index: int, package_path: str) -> None:
        """Index classifiers and recursively flatten nested packages."""
        for element in package:
            tag = element.tag.split('}')[-1]
            if tag == 'eClassifiers':
                kind = self._kind(element)
                original = element.get('name', '')
                if not original:
                    self._diagram.add_adaptation('Unnamed classifier', '', 'Unnamed Ecore classifier skipped.')
                    continue
                path = f'{prefix}/{original}'
                name = original
                if kind in ('EClass', 'EEnum'):
                    suffix = 1
                    while name in self._used_names:
                        name = f'{original}{suffix}'
                        suffix += 1
                    if name != original:
                        self._diagram.add_adaptation('Duplicate classifier name', original,
                                                     f"Classifier '{package_path}/{original}' renamed to '{name}'.")
                    self._used_names.add(name)
                self._classifiers[f'#/{root_index}{path}'] = (kind, name)
                identifier = element.get(XMI_ID)
                if identifier:
                    self._classifiers['#' + identifier] = (kind, name)
                if kind == 'EClass':
                    obj = self._diagram.get_or_create_class(name)
                    obj.set_abstract(element.get('abstract') == 'true' or element.get('interface') == 'true')
                    if element.get('interface') == 'true':
                        self._diagram.add_adaptation('Interface', name, f"Interface '{name}' imported as an abstract class.")
                    self._elements.append((element, name, path, root_index))
                elif kind == 'EEnum':
                    enum = UmlEnum(name)
                    for literal in element:
                        if literal.tag.split('}')[-1] == 'eLiterals' and literal.get('name'):
                            enum.add_literal(literal.get('name'))
                    self._diagram.add_enum(enum)
                elif kind == 'EDataType':
                    representation = PRIMITIVES.get(name.lower(), 'String')
                    self._diagram.add_adaptation('EDataType', name,
                                                 f"EDataType '{package_path}/{original}' is represented as {representation} when used.")
            elif tag == 'eSubpackages':
                subpackage = package_name(element)
                self._read_package(element, prefix + '/' + subpackage, root_index, package_path + '/' + subpackage)

    @staticmethod
    def _canonical(reference: str, root_index: int) -> Optional[str]:
        """Return a package-scoped local key or None for an external reference."""
        reference = unquote(reference.strip().split()[-1]) if reference.strip() else ''
        if reference.startswith('//'):
            reference = '#' + reference
        if reference.startswith('#//'):
            return f'#/{root_index}/' + reference[3:]
        if reference.startswith('#'):
            return reference
        if reference and '/' not in reference and ':' not in reference and '#' not in reference:
            return '#' + reference
        return None

    def _resolve(self, reference: str, root_index: int = 0) -> Optional[tuple[str, str]]:
        """Resolve a local Ecore fragment within its root package."""
        key = self._canonical(reference, root_index)
        if key is None:
            return None
        return self._classifiers.get(key)

    @staticmethod
    def _type_ref(element: ET.Element) -> str:
        """Return a type reference from an attribute or nested href."""
        if element.get('eType'):
            return element.get('eType')
        for child in element:
            if child.tag.split('}')[-1] in ('eType', 'eGenericType'):
                return child.get('href') or child.get('eClassifier') or ''
        return ''

    def _attribute_type(self, element: ET.Element, owner: str, name: str, root_index: int) -> str:
        """Resolve an attribute type or report a String fallback."""
        ref = self._type_ref(element)
        last = ref.split('#//')[-1].split('/')[-1]
        if (ECORE_URI in ref or XMLTYPE_URI in ref) and last.lower() in PRIMITIVES:
            return PRIMITIVES[last.lower()]
        resolved = self._resolve(ref, root_index)
        if resolved and resolved[0] == 'EDataType':
            last = resolved[1]
        declared_datatype = ((resolved and resolved[0] == 'EDataType') or 'ecore:EDataType ' in ref
                             or (resolved is None and '#//' in ref and self._canonical(ref, root_index) is None))
        for child in element:
            if child.tag.split('}')[-1] == 'eType' and self._kind(child) == 'EDataType':
                declared_datatype = True
        if declared_datatype and last.lower() in PRIMITIVES:
            mapped = PRIMITIVES[last.lower()]
            self._diagram.add_adaptation('Datatype mapped to primitive', owner,
                                         f"Attribute '{owner}.{name}': datatype '{ref}' mapped to {mapped}.")
            return mapped
        if resolved and resolved[0] in ('EClass', 'EEnum'):
            return resolved[1]
        kind = 'EDataType' if ((resolved and resolved[0] == 'EDataType') or ECORE_URI in ref or XMLTYPE_URI in ref) else 'Unknown type'
        self._diagram.add_adaptation(kind, owner, f"Attribute '{owner}.{name}': {kind} '{ref}' replaced by String.")
        return 'String'

    def _read_class(self, element: ET.Element, name: str, path: str, root_index: int) -> None:
        """Read parents, attributes, operations and reference declarations."""
        obj = self._diagram.get_class(name)
        parents = element.get('eSuperTypes', '').split()
        for child in element:
            if child.tag.split('}')[-1] == 'eGenericSuperTypes':
                parents.append(child.get('eClassifier') or child.get('href') or '')
        for parent in parents:
            resolved = self._resolve(parent, root_index)
            if resolved and resolved[0] == 'EClass':
                obj.add_parent(resolved[1])
            else:
                self._fallback(obj.get_name(), 'unresolvedParent', parent)
        for feature in element:
            tag = feature.tag.split('}')[-1]
            if tag == 'eOperations':
                self._diagram.add_adaptation('Operation skipped', name, f"Operation '{name}.{feature.get('name', '')}' skipped.")
            elif tag == 'eStructuralFeatures':
                feature_name = feature.get('name', '')
                if not feature_name:
                    self._diagram.add_adaptation('Unnamed feature', name, f"Unnamed feature of '{name}' skipped.")
                    continue
                kind = self._kind(feature)
                if kind == 'EAttribute':
                    obj.add_attribute(UmlAttribute(feature_name, self._attribute_type(feature, name, feature_name, root_index), EXACTLY_ONE))
                elif kind == 'EReference':
                    ref = Reference(name, f'#/{root_index}{path}/{feature_name}', feature, root_index)
                    self._references.append(ref)
                    self._ref_paths[ref.path] = ref
                    if feature.get(XMI_ID):
                        self._ref_paths['#' + feature.get(XMI_ID)] = ref

    def _fallback(self, owner: str, name: str, reference: str) -> None:
        """Keep an unresolved reference as a String attribute and report it."""
        self._diagram.get_class(owner).add_attribute(UmlAttribute(name, 'String', EXACTLY_ONE))
        self._diagram.add_adaptation('Unresolved reference', owner,
                                     f"Reference '{owner}.{name}' to '{reference}' imported as String.")

    def _bounds(self, reference: Reference) -> UmlMultiplicity:
        """Read Ecore reference bounds, with Ecore's defaults of zero and one."""
        try:
            lower = int(reference.element.get('lowerBound', '0'))
            upper = int(reference.element.get('upperBound', '1'))
            if upper == -2:
                return ZERO_TO_MANY
            if lower < 0 or upper < -1 or (upper != -1 and lower > upper):
                raise ValueError()
            return UmlMultiplicity(lower, upper)
        except ValueError:
            self._diagram.add_adaptation('Invalid multiplicity', reference.owner,
                                         f"Reference '{reference.owner}.{reference.element.get('name')}' has invalid bounds; 0..* used.")
            return ZERO_TO_MANY

    def _read_references(self) -> None:
        """Create attributes or paired associations, processing containment first."""
        done: set[str] = set()
        incoming: dict[str, Reference] = {}
        for reference in self._references:
            opposite = reference.element.get('eOpposite', '')
            key = self._canonical(opposite, reference.root_index)
            opposite_ref = self._ref_paths.get(key) if key else None
            if opposite_ref:
                incoming[opposite_ref.path] = reference
        references = sorted(self._references, key=lambda ref: (
            ref.element.get('containment') != 'true', not bool(ref.element.get('eOpposite'))))
        for ref in references:
            if ref.path in done:
                continue
            name = ref.element.get('name')
            type_ref = self._type_ref(ref.element)
            target = self._resolve(type_ref, ref.root_index)
            opposite_path = ref.element.get('eOpposite', '')
            key = self._canonical(opposite_path, ref.root_index)
            opposite = self._ref_paths.get(key) if key else None
            if not opposite_path:
                opposite = incoming.get(ref.path)
            if not target or target[0] != 'EClass':
                self._fallback(ref.owner, name, type_ref)
                done.add(ref.path)
                continue
            if (opposite_path and opposite is None) or (opposite and opposite.owner != target[1]):
                self._fallback(ref.owner, name, opposite_path)
                done.add(ref.path)
                continue
            if opposite and opposite.path in done:
                self._fallback(ref.owner, name, opposite_path)
                done.add(ref.path)
                continue
            bounds = self._bounds(ref)
            if ref.element.get('containment') != 'true' and opposite is None and bounds.get_upper() == 1:
                self._diagram.get_class(ref.owner).add_attribute(UmlAttribute(name, target[1], EXACTLY_ONE))
            else:
                if ref.element.get('containment') == 'true':
                    explicit = opposite and any(key in opposite.element.attrib for key in ('lowerBound', 'upperBound'))
                    whole_bounds = self._bounds(opposite) if explicit else None
                    source_bounds = ClassDiagramNormalizer.composition_whole(self._diagram, whole_bounds, ref.owner, target[1])
                else:
                    source_bounds = self._bounds(opposite) if opposite else ZERO_TO_MANY
                association = UmlAssociation(ref.owner, target[1], source_bounds, bounds)
                association.set_target_role(name)
                association.set_source_role(opposite.element.get('name') if opposite else lower_first(ref.owner))
                self._diagram.add_association(association)
                if opposite:
                    done.add(opposite.path)
            done.add(ref.path)


def package_name(package: ET.Element) -> str:
    """Return the name used in a nested package fragment."""
    return package.get('name', '')
