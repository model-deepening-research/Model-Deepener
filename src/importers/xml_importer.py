"""Builds a model from an XModeler XML file."""
import re
import xml.etree.ElementTree as ElementTree
from typing import Dict, List, Optional, Tuple, Union
from xml.dom.minidom import Element, parse

from src.basemlm.basemlm_association import BaseMlmAssociation
from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_constraint import BaseMlmConstraint
from src.basemlm.basemlm_enum_type import BaseMlmEnumType
from src.basemlm.basemlm_link import BaseMlmLink
from src.basemlm.basemlm_model import BaseMlmModel, metaClass
from src.basemlm.basemlm_object import BaseMlmObject
from src.basemlm.basemlm_operation import BaseMlmOperation
from src.basemlm.basemlm_predefined_type import UnknownType
from src.basemlm.basemlm_slot import BaseMlmSlot
from src.basemlm.basemlm_type_spec import TypeSpec
from src.basemlm.multiplicity import Multiplicity
from src.importers.import_report import (ASSOCIATION_WITHOUT_CLASS, ATTRIBUTE_TYPE_WITHOUT_PATH, INSTANCE_WITHOUT_CLASS,
                                         ImportReport, LINK_WITHOUT_ASSOCIATION, LINK_WITHOUT_OBJECT, StructureProblem,
                                         UNKNOWN_ATTRIBUTE_TYPE, UNKNOWN_PARENT, UNKNOWN_SUBCLASS)
from src.importers.model_importer import ModelImporter, register_importer
from src.importers.slot_value_converter import SlotValueConverter

PATH_SEPARATOR = "::"
UNKNOWN_LEVEL = "99"
NOT_ABSTRACT = "false"
SEQ_START = "Seq{"
BUILT_IN_PACKAGES = ("XCore", "Auxiliary")
MINIMUM_TYPE_PATH_LENGTH = 3

# Recognizes the first three parts of a multiplicity, for example in: Seq{1,1,true,false}
ATTRIBUTE_MULTIPLICITY_PATTERN = re.compile(r"Seq\{\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(true|false)", re.IGNORECASE)


class XmlImporter(ModelImporter):
    """Reads an XModeler XML file. The steps do not depend on the order of the commands in the file."""

    EXTENSIONS = (".xml",)
    SOURCE_FOLDER = "example_models"
    FORMAT_NAME = "XML"

    def __init__(self) -> None:
        """Create an importer. The document and the model are set when a file is imported."""
        self._document = None
        self._model: Optional[BaseMlmModel] = None
        self._report: Optional[ImportReport] = None
        self._converter: Optional[SlotValueConverter] = None

    def import_into(self, model: BaseMlmModel, path: str) -> ImportReport:
        """Fill the given empty model with the content of the XML file and return the problems found."""
        try:
            self._document = parse(path)
        except FileNotFoundError:
            raise FileNotFoundError(f"File '{path}' was not found!")
        except:
            raise Exception(f"File '{path}' could not be parsed!")

        self._model = model
        self._report = ImportReport()
        self._converter = SlotValueConverter(model, self._report)
        self._extract_model()
        return self._report

    def _extract_model(self) -> None:
        """Read the semantic model and keep its complete diagram section.

        The steps follow what they need: attributes need classes and enums, slots need attributes,
        and links need associations.
        """
        root_attributes = self._attributes_of(self._document.documentElement)
        imports_xml = self._section_as_element("Imports")
        path_name = self._retrieve_path_name()
        self._model.set_path_name(path_name)
        self._model.set_model_name(path_name.split(PATH_SEPARATOR)[-1])
        self._print_progress("BEGIN MLM EXTRACTION")
        for mlm_object in self._retrieve_all_mlm_objects():
            self._model.add_mlm_object(mlm_object)
        self._model.set_instances_of_mlm_objects()
        self._print_progress("ALL OBJECTS RETRIEVED")
        self._set_generalizations()
        self._print_progress("ALL GENERALIZATIONS RETRIEVED")
        for enum in self._retrieve_all_enums():
            self._model.add_enum(enum)
        self._print_progress("ALL ENUMS RETRIEVED")
        self._retrieve_all_attributes()
        self._print_progress("ALL ATTRIBUTES RETRIEVED")
        self._retrieve_all_slots()
        self._print_progress("ALL SLOTS RETRIEVED")
        self._retrieve_all_operations()
        self._retrieve_all_constraints()
        self._retrieve_all_associations()
        self._retrieve_all_links()
        self._model.add_association_ends()
        self._model.add_slot_links()
        self._model.set_xml_metadata(root_attributes, imports_xml, self._section_as_element("Diagrams"))

    def _print_progress(self, message: str) -> None:
        """Print a message if the model asks for progress messages."""
        if self._model.print_progress:
            print(message)

    @staticmethod
    def _attributes_of(element: Element) -> Dict[str, str]:
        """Return all attributes of an XML element, so that the export can write them again."""
        attributes = {}
        for attribute_name in element.attributes.keys():
            attributes[attribute_name] = element.getAttribute(attribute_name)
        return attributes

    def _section_as_element(self, tag_name: str) -> Optional[ElementTree.Element]:
        """Return the first element with this name in the form the export uses, or None if there is none."""
        nodes = self._document.getElementsByTagName(tag_name)
        if not nodes:
            return None
        return ElementTree.fromstring(nodes[0].toxml())

    def _retrieve_path_name(self) -> str:
        """Return the model path from current and older XModeler XML files.

        Version 4 stores the path on the root element. Version 3 stores it as
        the name of the first Project element, so both locations are checked.
        """
        root_path = self._document.documentElement.getAttribute("path")
        if root_path:
            return root_path

        project_nodes = self._document.getElementsByTagName("Project")
        if project_nodes and project_nodes[0].getAttribute("name"):
            return project_nodes[0].getAttribute("name")
        raise ValueError("The XML file does not contain an XModeler project path.")

    def _retrieve_all_mlm_objects(self) -> List[BaseMlmObject]:
        """Retrieve all classes and instances.

        First all highest-level classes are retrieved, since they have a separate XML tag. Afterward,
        the remaining objects are retrieved in repeated passes, because an instance can be the class
        of another instance and the order in the file does not matter. Instances that remain have no
        class in the model or depend on each other in a cycle. They are reported and not loaded.
        """
        mlm_objects = self._retrieve_metaclass_objects()
        pending_instances = self._retrieve_instance_objects()
        progress_made = True
        while pending_instances and progress_made:
            still_pending = []
            for instance_object in pending_instances:
                if not self._add_instance_with_class(instance_object, mlm_objects):
                    still_pending.append(instance_object)
            progress_made = len(still_pending) < len(pending_instances)
            pending_instances = still_pending
        for instance_object in pending_instances:
            self._report.add_structure_problem(StructureProblem(
                INSTANCE_WITHOUT_CLASS, instance_object.name, "", instance_object.class_of_object.full_name))
        return mlm_objects

    def _add_instance_with_class(self, instance_object: BaseMlmObject, mlm_objects: List[BaseMlmObject]) -> bool:
        """Connect an instance to its class and add it to the objects. Return False if the class is not there."""
        class_of_object = self._find_object_by_full_name(instance_object.class_of_object.full_name, mlm_objects)
        if class_of_object is None:
            return False
        declared_level = instance_object.level
        instance_object.set_class_of_object(class_of_object)
        instance_object.level = declared_level
        if self._model.print_progress:
            print(f"Object {instance_object.name} extracted.")
        mlm_objects.append(instance_object)
        return True

    def _retrieve_metaclass_objects(self) -> List[BaseMlmObject]:
        """Create the objects of all addMetaClass elements."""
        mlm_objects = []
        for object_element in self._document.getElementsByTagName("addMetaClass"):
            mlm_objects.append(BaseMlmObject(self._full_name_of(object_element), object_element.getAttribute("name"),
                                             object_element.getAttribute("level"), metaClass,
                                             object_element.getAttribute("abstract"), self._model))
        return mlm_objects

    def _retrieve_instance_objects(self) -> List[BaseMlmObject]:
        """Create the objects of all addInstance elements.

        Each one first gets a placeholder that only knows the name of its class, because the class
        itself may not exist yet.
        """
        mlm_objects = []
        for object_element in self._document.getElementsByTagName("addInstance"):
            declared_level = object_element.getAttribute("level")
            if declared_level == "":
                declared_level = UNKNOWN_LEVEL
            class_placeholder = BaseMlmObject(object_element.getAttribute("of"), "", UNKNOWN_LEVEL, None, NOT_ABSTRACT,
                                              self._model)
            mlm_objects.append(BaseMlmObject(self._full_name_of(object_element), object_element.getAttribute("name"),
                                             declared_level, class_placeholder,
                                             object_element.getAttribute("abstract"), self._model))
        return mlm_objects

    @staticmethod
    def _full_name_of(object_element: Element) -> str:
        """Return the full name of a class or instance element, like Root::Model::Person."""
        return object_element.getAttribute("package") + PATH_SEPARATOR + object_element.getAttribute("name")

    @staticmethod
    def _find_object_by_full_name(full_object_name: str, mlm_objects: List[BaseMlmObject]) -> Optional[BaseMlmObject]:
        """Return the object with this full name, or None if the list does not contain it."""
        for mlm_object in mlm_objects:
            if mlm_object.full_name == full_object_name:
                return mlm_object
        return None

    def _set_generalizations(self) -> None:
        """Connect the classes of all changeParent elements. An unknown class is reported."""
        for parent_element in self._document.getElementsByTagName("changeParent"):
            child_name = parent_element.getAttribute("class")
            child_class = self._find_object_by_full_name(child_name, self._model.get_objects())
            for parent_class_name in parent_element.getAttribute("new").split(","):
                parent_class = self._find_object_by_full_name(parent_class_name, self._model.get_objects())
                if child_class is None or parent_class is None:
                    problem_type = UNKNOWN_PARENT if parent_class is None else UNKNOWN_SUBCLASS
                    self._report.add_structure_problem(StructureProblem(
                        problem_type, child_name.split(PATH_SEPARATOR)[-1], "", parent_class_name))
                    continue
                child_class.add_parent_class(parent_class)

    def _retrieve_all_enums(self) -> List[BaseMlmEnumType]:
        """Create the enums of all addEnumeration elements with the values of their addEnumerationValue elements."""
        enums_tmp: List[BaseMlmEnumType] = []
        for enum_element in self._document.getElementsByTagName("addEnumeration"):
            enums_tmp.append(BaseMlmEnumType(enum_element.getAttribute("name")))
        for enum_value_element in self._document.getElementsByTagName("addEnumerationValue"):
            for enum_tmp in enums_tmp:
                if enum_value_element.getAttribute("enum_name") == enum_tmp.name:
                    enum_tmp.add_enum_value(enum_value_element.getAttribute("enum_value_name"))
        return enums_tmp

    def _retrieve_all_attributes(self) -> None:
        """Create the attributes of all addAttribute elements. An unknown type is reported."""
        for attribute_element in self._document.getElementsByTagName("addAttribute"):
            type_str = attribute_element.getAttribute("type")
            type_spec = self._find_attribute_type(type_str)
            new_attr = BaseMlmAttribute(attribute_element.getAttribute("name"), type_str,
                                        attribute_element.getAttribute("level"),
                                        UnknownType() if type_spec is None else type_spec,
                                        multiplicity=self._parse_attribute_multiplicity(
                                            attribute_element.getAttribute("multiplicity")))
            if type_spec is None:
                new_attr.mark_type_missing()
                self._report_missing_type(attribute_element, new_attr, type_str)
            owner_object = self._find_object_named_in_xml(attribute_element.getAttribute("class"))
            if owner_object is not None:
                owner_object.add_attr(new_attr)
                new_attr.set_owner(owner_object)

    def _report_missing_type(self, attribute_element: Element, attribute: BaseMlmAttribute, type_str: str) -> None:
        """Report an attribute whose type could not be found."""
        class_name = attribute_element.getAttribute("class").split(PATH_SEPARATOR)[-1]
        problem_type = UNKNOWN_ATTRIBUTE_TYPE if PATH_SEPARATOR in type_str else ATTRIBUTE_TYPE_WITHOUT_PATH
        self._report.add_structure_problem(StructureProblem(
            problem_type, class_name, f"{class_name}.{attribute.name}", type_str))

    def _find_attribute_type(self, type_str: str) -> Optional[TypeSpec]:
        """Return the type named in the XML file, or None if the model does not contain it."""
        type_path = type_str.split(PATH_SEPARATOR)
        if len(type_path) < MINIMUM_TYPE_PATH_LENGTH:
            return None
        if type_path[1] not in BUILT_IN_PACKAGES and not self._is_class_or_enum_name(type_path[2]):
            return None
        return self._model.parse_attribute_type(type_str)

    def _is_class_or_enum_name(self, name: str) -> bool:
        """Return True if an object or an enum of the model has this name."""
        for element in self._model.get_objects() + self._model.get_enum_types():
            if element.name == name:
                return True
        return False

    @staticmethod
    def _parse_attribute_multiplicity(multiplicity_value: str) -> Optional[Multiplicity]:
        """Read an XModeler ``Seq`` multiplicity used by an attribute."""
        if not multiplicity_value:
            return None
        match = ATTRIBUTE_MULTIPLICITY_PATTERN.search(multiplicity_value)
        if match is None:
            return None
        lower_bound = int(match.group(1))
        upper_bound = int(match.group(2))
        is_unbounded = match.group(3).lower() == "true"
        return Multiplicity(lower_bound, upper_bound, unbound=is_unbounded)

    def _find_object_named_in_xml(self, xml_object_name: str) -> Optional[BaseMlmObject]:
        """Return the object named in the XML, or None if there is no such object or several.

        XML files sometimes use the full model path and sometimes only the final class name.
        This finds the same class in both cases.
        """
        for mlm_object in self._model.get_objects():
            if xml_object_name == mlm_object.full_name:
                return mlm_object
        short_name = xml_object_name.split(PATH_SEPARATOR)[-1]
        matching_objects = []
        for mlm_object in self._model.get_objects():
            if short_name == mlm_object.name:
                matching_objects.append(mlm_object)
        if len(matching_objects) == 1:
            return matching_objects[0]
        return None

    def _retrieve_all_slots(self) -> None:
        """Read slot values while retaining their original XML expressions."""
        for slot_element in self._document.getElementsByTagName("changeSlotValue"):
            xml_value = slot_element.getAttribute("valueToBeParsed")
            new_slot = BaseMlmSlot(slot_element.getAttribute("slotName"), xml_value, xml_value=xml_value)
            owner_object = self._find_object_named_in_xml(slot_element.getAttribute("class"))
            if owner_object is not None:
                new_slot.set_owner_object(owner_object)
                new_slot.set_attribute()
                self._converter.convert(new_slot)
                owner_object.add_slot(new_slot)

    def _retrieve_all_operations(self) -> None:
        """Create the operations of all addOperation elements and keep their XML attributes for the export."""
        for operations_element in self._document.getElementsByTagName("addOperation"):
            new_operation = BaseMlmOperation(operations_element.getAttribute("name"),
                                             operations_element.getAttribute("level"),
                                             operations_element.getAttribute("type"))
            new_operation.xml_attributes = self._attributes_of(operations_element)
            for mlm_object in self._model.get_objects():
                if operations_element.getAttribute("class") == mlm_object.full_name:
                    mlm_object.add_operation(new_operation)

    def _retrieve_all_constraints(self) -> None:
        """Create the constraints of all addConstraint elements and keep their XML attributes for the export."""
        for constraint_element in self._document.getElementsByTagName("addConstraint"):
            new_constraint = BaseMlmConstraint(constraint_element.getAttribute("constName"),
                                               constraint_element.getAttribute("instLevel"))
            new_constraint.xml_attributes = self._attributes_of(constraint_element)
            for mlm_object in self._model.get_objects():
                if constraint_element.getAttribute("class") == mlm_object.full_name:
                    mlm_object.add_constraint(new_constraint)

    def _retrieve_all_associations(self) -> None:
        """Create the associations of all addAssociation elements. One without both classes is reported."""
        for association_element in self._document.getElementsByTagName("addAssociation"):
            new_association = self._create_association(association_element)
            self._set_end_objects(new_association, association_element)
            if new_association.get_source_object() is None or new_association.get_target_object() is None:
                self._report.add_structure_problem(StructureProblem(
                    ASSOCIATION_WITHOUT_CLASS, new_association.name, "", self._ends_text(association_element)))
                continue
            self._model.add_association(new_association)

    def _create_association(self, association_element: Element) -> BaseMlmAssociation:
        """Create an association with its names and multiplicities, but still without its classes."""
        new_association = BaseMlmAssociation(association_element.getAttribute("fwName"),
                                             association_element.getAttribute("instLevelSource"),
                                             association_element.getAttribute("instLevelTarget"),
                                             association_element.getAttribute("accessTargetFromSourceName"),
                                             association_element.getAttribute("accessSourceFromTargetName"))
        new_association.xml_attributes = self._attributes_of(association_element)
        source_lower, source_upper = self._association_bounds(association_element.getAttribute("multTargetToSource"))
        target_lower, target_upper = self._association_bounds(association_element.getAttribute("multSourceToTarget"))
        new_association.set_source_multiplicity(source_lower, source_upper)
        new_association.set_target_multiplicity(target_lower, target_upper)
        return new_association

    @staticmethod
    def _association_bounds(multiplicity_value: str) -> Tuple[int, int]:
        """Return the lower and upper bound of a multiplicity like Seq{0,-1,false,false}."""
        parts = multiplicity_value[len(SEQ_START):-1].split(",")
        return int(parts[0]), int(parts[1])

    def _set_end_objects(self, connection: Union[BaseMlmAssociation, BaseMlmLink], element: Element) -> None:
        """Set the source and target object of an association or link from the names in its XML element."""
        for mlm_object in self._model.get_objects():
            if element.getAttribute("classSource") == mlm_object.full_name:
                connection.set_source_object(mlm_object)
            if element.getAttribute("classTarget") == mlm_object.full_name:
                connection.set_target_object(mlm_object)

    @staticmethod
    def _ends_text(element: Element) -> str:
        """Return the two ends of an association or link for a problem report."""
        return f"{element.getAttribute('classSource')} -> {element.getAttribute('classTarget')}"

    def _retrieve_all_links(self) -> None:
        """Read links and connect each one to the association named in the XML. A link without a target is reported."""
        for link_element in self._document.getElementsByTagName("addLink"):
            new_link: BaseMlmLink = BaseMlmLink(link_element.getAttribute("name"))
            self._set_end_objects(new_link, link_element)
            association = self._find_association_of_link(link_element.getAttribute("name"))
            if association is not None:
                new_link.set_association(association)
            if (new_link.get_association() is None or new_link.get_source_object() is None
                    or new_link.get_target_object() is None):
                problem_type = LINK_WITHOUT_ASSOCIATION if new_link.get_association() is None else LINK_WITHOUT_OBJECT
                self._report.add_structure_problem(StructureProblem(
                    problem_type, new_link.name, "", self._ends_text(link_element)))
                continue
            self._model.add_link(new_link)

    def _find_association_of_link(self, link_name: str) -> Optional[BaseMlmAssociation]:
        """Return the association a link belongs to, or None if the name does not lead to exactly one.

        Some older files use the association's forward name while other files use an access name.
        The forward name is preferred because it is the direct and unambiguous reference used by
        the example models.
        """
        matching_associations = []
        for association in self._model.get_associations():
            if association.name == link_name:
                matching_associations.append(association)
        if len(matching_associations) != 1:
            matching_associations = []
            for association in self._model.get_associations():
                if association.get_source_access_name() == link_name:
                    matching_associations.append(association)
        if len(matching_associations) == 1:
            return matching_associations[0]
        return None


register_importer(XmlImporter)
