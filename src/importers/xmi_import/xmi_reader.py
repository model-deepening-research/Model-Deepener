"""Read UML XMI models into the shared class diagram."""
from pathlib import Path
from typing import Optional
from urllib.parse import unquote
import xml.etree.ElementTree as ET

from src.importers.class_diagram import (ClassDiagram, UmlAssociation, UmlAttribute, UmlEnum,
                                         UmlMultiplicity, EXACTLY_ONE, ZERO_TO_MANY, lower_first)
from src.importers.class_diagram_normalizer import ClassDiagramNormalizer

XSI_TYPE = '{http://www.w3.org/2001/XMLSchema-instance}type'
PRIMITIVES = {
    'string': 'String', 'integer': 'Integer', 'int': 'Integer', 'long': 'Integer',
    'short': 'Integer', 'unlimitednatural': 'Integer', 'boolean': 'Boolean',
    'real': 'Float', 'float': 'Float', 'double': 'Float', 'decimal': 'Float',
    'date': 'Date', 'datum': 'Date', 'datetime': 'Date',
}
PATHMAP_PRIMITIVES = {
    **PRIMITIVES,
    'byte': 'Integer', 'biginteger': 'Integer', 'char': 'String', 'character': 'String',
    'bigdecimal': 'Float', 'time': 'Date',
    'estring': 'String', 'echar': 'String', 'echaracterobject': 'String',
    'eint': 'Integer', 'eintegerobject': 'Integer', 'elong': 'Integer', 'elongobject': 'Integer',
    'eshort': 'Integer', 'eshortobject': 'Integer', 'ebyte': 'Integer', 'ebyteobject': 'Integer',
    'ebiginteger': 'Integer', 'eboolean': 'Boolean', 'ebooleanobject': 'Boolean',
    'edouble': 'Float', 'edoubleobject': 'Float', 'efloat': 'Float', 'efloatobject': 'Float',
    'ebigdecimal': 'Float', 'edate': 'Date',
}
CLASS_KINDS = {'Class', 'Interface', 'AssociationClass'}


def local_tag(element: ET.Element) -> str:
    """Return the local name of an XML element."""
    return element.tag.split('}')[-1]


def xmi_id(element: ET.Element) -> str:
    """Return the XMI identifier of an element."""
    for key, value in element.attrib.items():
        if key.endswith('}id') and ('XMI' in key or 'xmi' in key):
            return value
    return ''


def xmi_ref(element: ET.Element) -> str:
    """Return an XMI id reference or href."""
    for key, value in element.attrib.items():
        if key.endswith('}idref'):
            return value
    return element.get('href', '')


def kind(element: ET.Element) -> str:
    """Return the UML element type."""
    value = element.get(XSI_TYPE, '')
    return value.split(':')[-1] if value else local_tag(element)


class XmiReader:
    """Read UML classes, properties and relationships from one XMI file."""

    def __init__(self, path: str) -> None:
        """Prepare the model and identifier indexes."""
        self._path = Path(path)
        self._diagram = ClassDiagram(self._path.stem)
        self._ids: dict[str, ET.Element] = {}
        self._class_names: dict[str, str] = {}
        self._enum_names: dict[str, str] = {}
        self._used_names: set[str] = set()
        self._classes: list[ET.Element] = []
        self._associations: list[ET.Element] = []
        self._association_ends: set[str] = set()
        self._qualified: dict[str, Optional[ET.Element]] = {}
        self._local_uuids: set[str] = set()

    def read_diagram(self) -> ClassDiagram:
        """Read the UML model and return a normalized intermediate diagram."""
        root = ET.parse(self._path).getroot()
        for element in root.iter():
            identifier = xmi_id(element)
            if identifier:
                self._ids[identifier] = element
        roots = [root] if local_tag(root) == 'Model' else list(root)
        for element in roots:
            if local_tag(element) == 'Model' and element.tag.startswith('{http://www.eclipse.org/uml2/'):
                for extension in element:
                    if local_tag(extension) == 'Extension':
                        for detail in extension.iter():
                            if local_tag(detail) == 'details' and detail.get('key') == 'uuid' and detail.get('value'):
                                self._local_uuids.add(detail.get('value'))
                self._read_package(element, '')
        if not self._classes:
            self._diagram.add_adaptation('No classes', '', 'No UML classes or interfaces found; no model was imported.')
            return self._diagram
        for association in self._associations:
            self._association_ends.update(self._member_ids(association))
        for element in self._classes:
            self._read_class(element)
        for element in self._associations:
            self._read_association(element)
        return self._diagram

    def _unique_name(self, name: str, path: str) -> str:
        """Create a unique flattened classifier name and report a collision."""
        candidate = name
        number = 1
        while candidate in self._used_names:
            candidate = f'{name}{number}'
            number += 1
        if candidate != name:
            self._diagram.add_adaptation('Duplicate classifier name', name,
                                         f"Classifier '{path}/{name}' renamed to '{candidate}'.")
        self._used_names.add(candidate)
        return candidate

    def _read_package(self, package: ET.Element, path: str) -> None:
        """Index supported classifiers and associations in a package."""
        for element in package:
            if local_tag(element) not in ('packagedElement', 'nestedClassifier', 'ownedType'):
                continue
            element_kind = kind(element)
            name = element.get('name', '')
            identifier = xmi_id(element)
            if name:
                qualified = path + '/' + name
                if qualified in self._qualified:
                    self._qualified[qualified] = None
                else:
                    self._qualified[qualified] = element
            if element_kind in ('Package', 'Model'):
                self._read_package(element, path + '/' + (name or '(unnamed)'))
            elif element_kind in CLASS_KINDS:
                if not name:
                    name = f'Class{len(self._classes) + 1}'
                    self._diagram.add_adaptation('Unnamed class', '', f"Unnamed class at '{path}' named '{name}'.")
                unique = self._unique_name(name, path)
                self._class_names[identifier] = unique
                obj = self._diagram.get_or_create_class(unique)
                obj.set_abstract(element.get('isAbstract') == 'true' or element_kind == 'Interface')
                if element_kind == 'Interface':
                    self._diagram.add_adaptation('Interface', unique, f"Interface '{unique}' imported as an abstract class.")
                self._classes.append(element)
                if element_kind == 'AssociationClass':
                    self._associations.append(element)
                self._read_package(element, path + '/' + name)
            elif element_kind == 'Enumeration':
                name = name or f'Enum{len(self._enum_names) + 1}'
                unique = self._unique_name(name, path)
                self._enum_names[identifier] = unique
                enum = UmlEnum(unique)
                for literal in element:
                    if local_tag(literal) == 'ownedLiteral' and literal.get('name'):
                        enum.add_literal(literal.get('name'))
                self._diagram.add_enum(enum)
            elif element_kind == 'Association':
                self._associations.append(element)

    def _member_ids(self, association: ET.Element) -> list[str]:
        """Return member-end identifiers in their declared order."""
        result = association.get('memberEnd', '').split()
        for child in association:
            if local_tag(child) == 'memberEnd':
                reference = xmi_ref(child)
                if reference and reference not in result:
                    result.append(reference.lstrip('#'))
        for child in association:
            if local_tag(child) == 'ownedEnd' and xmi_id(child) not in result:
                result.append(xmi_id(child))
        return result

    @staticmethod
    def _type_reference(element: ET.Element) -> str:
        """Return a type id or a nested type href."""
        reference = element.get('type', '')
        if reference:
            return reference
        for child in element:
            if local_tag(child) == 'type':
                return xmi_ref(child)
        return ''

    def _resolve_element(self, reference: str) -> Optional[ET.Element]:
        """Resolve a local identifier without treating an external URL as local."""
        if not reference:
            return None
        if reference.startswith('genmymodel://'):
            location, separator, fragment = reference.partition('#')
            if not separator or location.removeprefix('genmymodel://') not in self._local_uuids:
                return None
            reference = '#' + fragment
        if reference.startswith('#//'):
            return self._qualified.get(unquote(reference[2:]))
        if '#' in reference and not reference.startswith('#'):
            return None
        return self._ids.get(reference.lstrip('#'))

    def _attribute_type(self, element: ET.Element, owner: str, name: str) -> str:
        """Resolve a property type, reporting unsupported and missing types."""
        reference = self._type_reference(element)
        target = self._resolve_element(reference)
        type_name = target.get('name', '') if target is not None else reference.rsplit('#', 1)[-1].lstrip('/')
        is_pathmap = reference.lower().startswith('pathmap://')
        primitives = PATHMAP_PRIMITIVES if is_pathmap else PRIMITIVES
        if type_name.lower() in primitives:
            return primitives[type_name.lower()]
        identifier = xmi_id(target) if target is not None else ''
        if identifier in self._enum_names:
            return self._enum_names[identifier]
        if identifier in self._class_names:
            return self._class_names[identifier]
        if target is not None and kind(target) == 'DataType':
            matches = [self._class_names[xmi_id(cls)] for cls in self._classes
                       if cls.get('name', '') == type_name]
            if len(matches) == 1:
                return matches[0]
            if not matches and type_name.lower() == 'numeric':
                return 'Float'
            category = 'DataType'
        elif not reference:
            category = 'Missing type'
        else:
            category = 'Unresolved type'
        self._diagram.add_adaptation(category, owner,
                                     f"Attribute '{owner}.{name}': {category.lower()} '{type_name or reference}' replaced by String.")
        return 'String'

    def _read_class(self, element: ET.Element) -> None:
        """Read one class's attributes and generalizations."""
        owner = self._class_names[xmi_id(element)]
        obj = self._diagram.get_class(owner)
        for child in element:
            tag = local_tag(child)
            if tag == 'generalization':
                parent_ref = child.get('general', '')
                if not parent_ref:
                    parent_ref = next((xmi_ref(c) for c in child if local_tag(c) == 'general'), '')
                target = self._resolve_element(parent_ref)
                parent = self._class_names.get(xmi_id(target)) if target is not None else None
                if parent:
                    obj.add_parent(parent)
                else:
                    obj.add_attribute(UmlAttribute('unresolvedParent', 'String', EXACTLY_ONE))
                    self._diagram.add_adaptation('Unresolved generalization', owner,
                                                 f"Class '{owner}': parent '{parent_ref}' imported as String attribute.")
            elif tag == 'ownedOperation':
                self._diagram.add_adaptation('Operation skipped', owner,
                                             f"Operation '{owner}.{child.get('name', '')}' skipped.")
            elif tag == 'ownedAttribute' and not child.get('association') and xmi_id(child) not in self._association_ends:
                name = child.get('name', '')
                if not name:
                    self._diagram.add_adaptation('Unnamed attribute', owner, f"Unnamed attribute in '{owner}' skipped.")
                    continue
                obj.add_attribute(UmlAttribute(name, self._attribute_type(child, owner, name), EXACTLY_ONE))

    def _bounds(self, end: ET.Element, label: str) -> UmlMultiplicity:
        """Read an association end's bounds; absent bounds mean zero to many."""
        lower_text = end.get('lower')
        upper_text = end.get('upper')
        for child in end:
            if local_tag(child) == 'lowerValue':
                lower_text = child.get('value', '0')
            elif local_tag(child) == 'upperValue':
                upper_text = child.get('value', '0')
        if lower_text is None and upper_text is None:
            return ZERO_TO_MANY
        try:
            lower = int(lower_text if lower_text is not None else '0')
            upper = -1 if upper_text in (None, '*', '-1') else int(upper_text)
            if lower < 0 or upper < -1 or (upper != -1 and lower > upper):
                raise ValueError()
            return UmlMultiplicity(lower, upper)
        except ValueError:
            self._diagram.add_adaptation('Invalid multiplicity', label,
                                         f"Association end '{label}' has invalid bounds; 0..* used.")
            return ZERO_TO_MANY

    def _read_association(self, element: ET.Element) -> None:
        """Create a binary association or transform an association class or n-ary relation."""
        ends = [self._resolve_element(reference) for reference in self._member_ids(element)]
        if len(ends) < 2:
            self._keep_unresolved_association(element, [end for end in ends if end is not None])
            self._diagram.add_adaptation('Invalid association', element.get('name', ''),
                                         f"Association '{element.get('name', '')}' has fewer than two ends.")
            return
        if any(end is None for end in ends):
            known = [end for end in ends if end is not None]
            self._keep_unresolved_association(element, known)
            self._diagram.add_adaptation('Unresolved association end', element.get('name', ''),
                                         f"Association '{element.get('name', '')}' has an unresolved end and was skipped.")
            return
        participants = []
        unresolved = []
        for end in ends:
            target = self._resolve_element(self._type_reference(end))
            identifier = xmi_id(target) if target is not None else ''
            if identifier not in self._class_names:
                if target is None:
                    unresolved.append(end)
                    continue
                return
            participants.append((self._class_names[identifier], end))
        if unresolved:
            self._keep_unresolved_association(element, ends, unresolved)
            return
        aggregation = {end.get('aggregation', 'none') for _, end in participants}
        default_name = ('composition_of' if 'composite' in aggregation else
                        'aggregation_of' if 'shared' in aggregation else 'associated_to')
        name = element.get('name') or default_name
        if kind(element) == 'AssociationClass':
            self._association_class(element, participants, name, not bool(element.get('name')))
        elif len(participants) > 2:
            self._nary_association(participants, name, name_generated=not bool(element.get('name')))
        else:
            self._add_binary(participants[0], participants[1], name, not bool(element.get('name')))

    def _keep_unresolved_association(self, association: ET.Element, ends: list[ET.Element],
                                     unresolved: Optional[list[ET.Element]] = None) -> None:
        """Keep unresolved association types as String attributes on known participants."""
        unknown = unresolved or []
        for end in ends:
            target = self._resolve_element(self._type_reference(end))
            owner = self._class_names.get(xmi_id(target)) if target is not None else None
            if owner is None:
                continue
            for missing in unknown or [association]:
                name = missing.get('name') or association.get('name') or 'unresolvedReference'
                reference = self._type_reference(missing)
                self._diagram.get_class(owner).add_attribute(UmlAttribute(name, 'String', EXACTLY_ONE))
                self._diagram.add_adaptation('Unresolved association type', owner,
                                             f"Association reference '{owner}.{name}' to '{reference}' imported as String.")

    def _add_binary(self, left: tuple[str, ET.Element], right: tuple[str, ET.Element], name: str,
                    name_generated: bool = False) -> None:
        """Add one association with its two end roles and multiplicities."""
        left_name, left_end = left
        right_name, right_end = right
        left_bound = self._end_bounds(left_end, left_name, right_name, right_end.get('aggregation') == 'composite')
        right_bound = self._end_bounds(right_end, right_name, left_name, left_end.get('aggregation') == 'composite')
        assoc = UmlAssociation(left_name, right_name, left_bound, right_bound, name)
        if name_generated:
            assoc.mark_name_generated()
        if not left_end.get('name'):
            assoc.mark_source_role_generated()
        if not right_end.get('name'):
            assoc.mark_target_role_generated()
        assoc.set_source_role(left_end.get('name') or lower_first(left_name))
        assoc.set_target_role(right_end.get('name') or lower_first(right_name))
        self._diagram.add_association(assoc)

    def _association_class(self, element: ET.Element, ends: list[tuple[str, ET.Element]], name: str,
                           name_generated: bool = False) -> None:
        """Represent an association class with associations through its class."""
        if len(ends) != 2:
            self._nary_association(ends, name, self._class_names[xmi_id(element)], name_generated)
            return
        middle = self._class_names[xmi_id(element)]
        left_name, left = ends[0]
        right_name, right = ends[1]
        right_bound = self._end_bounds(right, right_name, left_name, left.get('aggregation') == 'composite')
        left_bound = self._end_bounds(left, left_name, right_name, right.get('aggregation') == 'composite')
        first = UmlAssociation(left_name, middle, EXACTLY_ONE, right_bound, name)
        if name_generated:
            first.mark_name_generated()
        if not left.get('name'):
            first.mark_source_role_generated()
        first.set_source_role(left.get('name') or lower_first(left_name))
        second = UmlAssociation(middle, right_name, left_bound, EXACTLY_ONE, name)
        if name_generated:
            second.mark_name_generated()
        if not right.get('name'):
            second.mark_target_role_generated()
        second.set_target_role(right.get('name') or lower_first(right_name))
        self._diagram.add_association(first)
        self._diagram.add_association(second)
        self._diagram.add_adaptation('Association class', middle, f"Association class '{middle}' represented by two associations.")

    def _nary_association(self, ends: list[tuple[str, ET.Element]], name: str, middle: str = '',
                          name_generated: bool = False) -> None:
        """Represent an n-ary association using an intermediate class."""
        if not middle:
            middle = self._unique_name(''.join(end[0] for end in ends), self._diagram.get_name())
            self._diagram.get_or_create_class(middle)
        for participant, end in ends:
            bound = self._bounds(end, participant)
            assoc = UmlAssociation(middle, participant, ZERO_TO_MANY, bound, name)
            if name_generated:
                assoc.mark_name_generated()
            if not end.get('name'):
                assoc.mark_target_role_generated()
            assoc.set_target_role(end.get('name') or lower_first(participant))
            self._diagram.add_association(assoc)
        self._diagram.add_adaptation('N-ary association', name,
                                     f"N-ary association '{name}' represented by class '{middle}'.")

    def _end_bounds(self, end: ET.Element, whole: str, part: str, is_whole: bool) -> UmlMultiplicity:
        """Use the opposite end's composite marker to identify the whole."""
        if not is_whole:
            return self._bounds(end, whole)
        explicit = ('lower' in end.attrib or 'upper' in end.attrib or
                    any(local_tag(child) in ('lowerValue', 'upperValue') for child in end))
        bounds = self._bounds(end, whole) if explicit else None
        return ClassDiagramNormalizer.composition_whole(self._diagram, bounds, whole, part)
