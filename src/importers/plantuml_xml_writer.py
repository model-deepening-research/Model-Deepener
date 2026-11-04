"""Writes a normalized PlantUML diagram as XModeler XML text in the form of the example models."""
import xml.etree.ElementTree as ElementTree
from typing import List, Tuple

from src.importers.plantuml_diagram import (MANY, PlantUmlDiagram, UNKNOWN_TYPE, UmlAttribute, UmlAssociation, UmlClass,
                                            UmlMultiplicity, UmlOperation, lower_first)

STRING_TYPE = "Root::XCore::String"
INTEGER_TYPE = "Root::XCore::Integer"
FLOAT_TYPE = "Root::XCore::Float"
BOOLEAN_TYPE = "Root::XCore::Boolean"
DATE_TYPE = "Root::Auxiliary::Date"
ANY_TYPE = "Root::XCore::Element"
PRIMITIVE_TYPES = {
    "string": STRING_TYPE,
    "sting": STRING_TYPE,
    "int": INTEGER_TYPE,
    "integer": INTEGER_TYPE,
    "long": INTEGER_TYPE,
    "double": FLOAT_TYPE,
    "float": FLOAT_TYPE,
    "boolean": BOOLEAN_TYPE,
    "date": DATE_TYPE,
    "datetime": DATE_TYPE,
    "time": DATE_TYPE,
}
ROOT_PREFIX = "Root::"
XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'
XML_INDENT = "    "
XMODELER_FORMAT_VERSION = "4"
XMODELER_VERSION = "2.3.4_u1.1.1"
DEFAULT_ASSOCIATION_TYPE = "Root::Associations::DefaultAssociation"
DEFAULT_ASSOCIATION_NAME = "has"
DISPLAY_PROPERTIES = ["SLOTS", "CONCRETESYNTAX", "METACLASSNAME", "ISSUETABLE", "OPERATIONS", "DERIVEDATTRIBUTES",
                      "CONSTRAINTS", "CONSTRAINTREPORTS", "DERIVEDOPERATIONS", "OPERATIONVALUES", "GETTERSANDSETTERS"]
HIDDEN_DISPLAY_PROPERTIES = ("METACLASSNAME", "ISSUETABLE")
GRID_COLUMNS = 5
GRID_START = 50
GRID_COLUMN_WIDTH = 300
GRID_ROW_HEIGHT = 250


def xml_boolean(value: bool) -> str:
    """Return the way the XML format writes a truth value."""
    if value:
        return "true"
    return "false"


def multiplicity_to_xml(multiplicity: UmlMultiplicity) -> str:
    """Return the XML form, for example Seq{0,1,true,false} for 0..1 and Seq{0,-1,false,false} for 0..*."""
    has_upper_bound = xml_boolean(multiplicity.get_upper() != MANY)
    return f"Seq{{{multiplicity.get_lower()},{multiplicity.get_upper()},{has_upper_bound},false}}"


class PlantUmlXmlWriter:
    """Builds the XML document of one normalized diagram. An unknown type is reported on the diagram."""

    def __init__(self, diagram: PlantUmlDiagram) -> None:
        """Remember the diagram. All names in the XML start with the path of its package."""
        self._diagram = diagram
        self._package = f"Root::{diagram.get_name()}"

    def to_xml_string(self) -> str:
        """Return the whole document, in the order of the XML format.

        A later element refers to earlier ones, so the classes come first and the diagram last.
        """
        root = ElementTree.Element("XModelerPackage", {
            "path": self._package, "version": XMODELER_FORMAT_VERSION, "xModelerVersion": XMODELER_VERSION})
        ElementTree.SubElement(root, "Imports")
        model_element = ElementTree.SubElement(root, "Model", {"name": self._package})

        self._write_classes(model_element)
        self._write_generalizations(model_element)
        self._write_enums(model_element)
        self._write_attributes(model_element)
        self._write_operations(model_element)
        self._write_associations(model_element)
        self._write_diagram(root)

        ElementTree.indent(root, space=XML_INDENT)
        return XML_DECLARATION + ElementTree.tostring(root, encoding="unicode") + "\n"

    def _qualified(self, name: str) -> str:
        """Return the full path of a class or enum, for example Root::Cruise::Ship."""
        return f"{self._package}::{name}"

    def _is_class_or_enum(self, type_name: str) -> bool:
        """Return True if the name belongs to a class or an enum of the diagram."""
        return self._diagram.has_enum(type_name) or self._diagram.has_class(type_name)

    def _resolve_type(self, type_name: str, owner_name: str) -> str:
        """Map a PlantUML type name to an XML type path. An unknown type becomes a String."""
        if self._is_class_or_enum(type_name):
            return self._qualified(type_name)
        if type_name.lower() in PRIMITIVE_TYPES:
            return PRIMITIVE_TYPES[type_name.lower()]
        self._diagram.add_adaptation(UNKNOWN_TYPE, owner_name, f"Unknown type '{type_name}' replaced by String.")
        return STRING_TYPE

    def _write_classes(self, parent: ElementTree.Element) -> None:
        """Write each class, written abstract class A in PlantUML, as an addMetaClass element."""
        for uml_class in self._diagram.get_classes():
            ElementTree.SubElement(parent, "addMetaClass", {
                "abstract": xml_boolean(uml_class.is_abstract()),
                "isControlClass": "false", "level": "1", "maxLevel": "1",
                "name": uml_class.get_name(), "package": self._package, "singleton": "false"})

    def _write_generalizations(self, parent: ElementTree.Element) -> None:
        """Write each generalization, written Parent <|-- Child in PlantUML, as a changeParent element."""
        for uml_class in self._diagram.get_classes():
            if uml_class.get_parent() is not None:
                ElementTree.SubElement(parent, "changeParent", {
                    "class": self._qualified(uml_class.get_name()), "new": self._qualified(uml_class.get_parent()),
                    "old": "", "package": self._package})

    def _write_enums(self, parent: ElementTree.Element) -> None:
        """Write each enum, written enum Color { RED } in PlantUML, with addEnumeration and addEnumerationValue."""
        for uml_enum in self._diagram.get_enums():
            ElementTree.SubElement(parent, "addEnumeration", {"name": uml_enum.get_name()})
            for literal in uml_enum.get_literals():
                ElementTree.SubElement(parent, "addEnumerationValue", {
                    "enum_name": uml_enum.get_name(), "enum_value_name": literal})

    def _write_attributes(self, parent: ElementTree.Element) -> None:
        """Write each attribute, written String name in PlantUML, as an addAttribute element."""
        for uml_class in self._diagram.get_classes():
            for attribute in uml_class.get_attributes():
                self._write_attribute(parent, uml_class, attribute)

    def _write_attribute(self, parent: ElementTree.Element, uml_class: UmlClass, attribute: UmlAttribute) -> None:
        """Write one addAttribute element."""
        ElementTree.SubElement(parent, "addAttribute", {
            "class": self._qualified(uml_class.get_name()), "level": "0",
            "multiplicity": multiplicity_to_xml(attribute.get_multiplicity()),
            "name": attribute.get_name(), "package": self._package,
            "type": self._resolve_type(attribute.get_type_name(), uml_class.get_name())})

    def _write_operations(self, parent: ElementTree.Element) -> None:
        """Write each operation, written int add(int a) in PlantUML, as an addOperation element."""
        for uml_class in self._diagram.get_classes():
            for operation in uml_class.get_operations():
                self._write_operation(parent, uml_class.get_name(), operation)

    def _write_operation(self, parent: ElementTree.Element, class_name: str, operation: UmlOperation) -> None:
        """Write one addOperation element. Its body does nothing, because PlantUML only has the signature."""
        names, types = self._parameter_names_and_types(operation, class_name)
        return_type = ANY_TYPE
        if operation.get_return_type():
            return_type = self._resolve_type(operation.get_return_type(), class_name)
        ElementTree.SubElement(parent, "addOperation", {
            "body": self._operation_body(operation.get_name(), names, types, return_type),
            "class": self._qualified(class_name), "level": "0", "monitored": "true",
            "name": operation.get_name(), "package": self._package,
            "paramNames": ",".join(names), "paramTypes": ",".join(types), "type": return_type})

    def _parameter_names_and_types(self, operation: UmlOperation, class_name: str) -> Tuple[List[str], List[str]]:
        """Return the parameter names and their type paths.

        A single word in the parameter list can be a class or enum; the name is then derived from it.
        """
        names = []
        types = []
        for parameter in operation.get_parameters():
            name = parameter.get_name()
            if parameter.get_type_name() is not None:
                names.append(name)
                types.append(self._resolve_type(parameter.get_type_name(), class_name))
            elif self._diagram.has_class(name) or self._diagram.has_enum(name):
                names.append(lower_first(name))
                types.append(self._qualified(name))
            else:
                names.append(name)
                types.append(ANY_TYPE)
        return names, types

    def _operation_body(self, operation_name: str, names: List[str], types: List[str], return_type: str) -> str:
        """Return the source text of an operation that only returns null."""
        signature_parts = []
        for index, name in enumerate(names):
            signature_parts.append(f"{name}:{self._short_type(types[index])}")
        signature = ",".join(signature_parts)
        return (f"@Operation {operation_name}[monitor=true,delToClassAllowed=false]({signature}):"
                f"{self._short_type(return_type)}\n  null\nend")

    @staticmethod
    def _short_type(type_path: str) -> str:
        """Return a type path without the leading Root::, which is how operation source text writes it."""
        return type_path.replace(ROOT_PREFIX, "", 1)

    def _write_associations(self, parent: ElementTree.Element) -> None:
        """Write each association, written A "1" -- "0..*" B in PlantUML, as an addAssociation element."""
        for association in self._diagram.get_associations():
            self._write_association(parent, association)

    def _write_association(self, parent: ElementTree.Element, association: UmlAssociation) -> None:
        """Write one addAssociation element. An association without a name is called has."""
        name = association.get_name()
        if not name:
            name = DEFAULT_ASSOCIATION_NAME
        ElementTree.SubElement(parent, "addAssociation", {
            "accessSourceFromTargetName": association.get_source_role(),
            "accessTargetFromSourceName": association.get_target_role(),
            "associationType": DEFAULT_ASSOCIATION_TYPE,
            "classSource": self._qualified(association.get_source()),
            "classTarget": self._qualified(association.get_target()),
            "fwName": name,
            "instLevelSource": "0", "instLevelTarget": "0",
            "multSourceToTarget": multiplicity_to_xml(association.get_target_multiplicity()),
            "multTargetToSource": multiplicity_to_xml(association.get_source_multiplicity()),
            "package": self._package, "reverseName": "-1",
            "sourceVisibleFromTarget": xml_boolean(association.is_source_navigable()),
            "targetVisibleFromSource": xml_boolean(association.is_target_navigable())})

    def _write_diagram(self, root: ElementTree.Element) -> None:
        """Write the Diagrams part, which says where XModeler shows the classes and what it displays."""
        diagrams = ElementTree.SubElement(root, "Diagrams")
        diagram = ElementTree.SubElement(diagrams, "Diagram", {"name": "UMLDiagram", "umlMode": "true"})
        self._write_diagram_instances(diagram)
        ElementTree.SubElement(diagram, "Edges")
        self._write_display_properties(diagram)
        ElementTree.SubElement(diagram, "Notes")
        views = ElementTree.SubElement(diagram, "Views")
        ElementTree.SubElement(views, "View", {"name": "Main View", "tx": "0.0", "ty": "0.0", "xx": "1.0"})

    def _write_diagram_instances(self, diagram: ElementTree.Element) -> None:
        """Place all classes in a simple grid. Enums are hidden, as in the diagrams XModeler writes."""
        instances = ElementTree.SubElement(diagram, "Instances")
        for index, uml_class in enumerate(self._diagram.get_classes()):
            column = index % GRID_COLUMNS
            row = index // GRID_COLUMNS
            ElementTree.SubElement(instances, "Instance", {
                "hidden": "false", "path": self._qualified(uml_class.get_name()),
                "xCoordinate": str(GRID_START + column * GRID_COLUMN_WIDTH),
                "yCoordinate": str(GRID_START + row * GRID_ROW_HEIGHT)})
        for uml_enum in self._diagram.get_enums():
            ElementTree.SubElement(instances, "Instance", {
                "hidden": "true", "path": self._qualified(uml_enum.get_name()), "xCoordinate": "0", "yCoordinate": "0"})

    @staticmethod
    def _write_display_properties(diagram: ElementTree.Element) -> None:
        """Write which parts XModeler shows. Only a few of them are hidden."""
        properties = ElementTree.SubElement(diagram, "DiagramDisplayProperties")
        for key in DISPLAY_PROPERTIES:
            ElementTree.SubElement(properties, key).text = xml_boolean(key not in HIDDEN_DISPLAY_PROPERTIES)
