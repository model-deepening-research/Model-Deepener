"""Build a BaseMLM model from a normalized class diagram."""
from src.basemlm.basemlm_association import BaseMlmAssociation
from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_enum_type import BaseMlmEnumType
from src.basemlm.basemlm_object import BaseMlmObject
from src.basemlm.basemlm_type_spec import TypeSpec
from src.basemlm.multiplicity import Multiplicity

from src.basemlm.basemlm_model import BaseMlmModel
from src.importers.import_report import ImportReport
from src.importers.class_diagram import ClassDiagram, UNKNOWN_TYPE


PRIMITIVE_TYPES = {
    "string": "Root::XCore::String", "sting": "Root::XCore::String",
    "int": "Root::XCore::Integer", "integer": "Root::XCore::Integer", "long": "Root::XCore::Integer",
    "double": "Root::XCore::Float", "float": "Root::XCore::Float",
    "boolean": "Root::XCore::Boolean", "date": "Root::Auxiliary::Date",
    "datetime": "Root::Auxiliary::Date", "time": "Root::Auxiliary::Date",
}


class ClassDiagramBuilder:
    """Create BaseMLM objects from a normalized class diagram."""

    def build(self, model: BaseMlmModel, diagram: ClassDiagram) -> ImportReport:
        """Create model objects from the normalized diagram and return its adaptations."""
        package = f"Root::{diagram.get_name()}"
        model.set_path_name(package)
        model.set_model_name(diagram.get_name())
        classes, enums = self._create_classes_and_enums(model, diagram, package)
        self._set_generalizations(diagram, classes)
        self._create_attributes(model, diagram, package, classes, enums)
        self._create_associations(model, diagram, classes)
        return self._create_import_report(diagram)

    @staticmethod
    def _create_classes_and_enums(
            model: BaseMlmModel, diagram: ClassDiagram, package: str,
    ) -> tuple[dict[str, BaseMlmObject], dict[str, BaseMlmEnumType]]:
        """Create classes and enums and report names that match primitive types."""
        classes: dict[str, BaseMlmObject] = {}
        enums: dict[str, BaseMlmEnumType] = {}
        for item in diagram.get_classes():
            obj = BaseMlmObject(f"{package}::{item.get_name()}", item.get_name(), "1",
                                BaseMlmObject.meta_class(), str(item.is_abstract()).lower(), model)
            classes[item.get_name()] = obj
            model.add_mlm_object(obj)
            if item.get_name().lower() in PRIMITIVE_TYPES:
                diagram.add_adaptation("Primitive type name conflict", item.get_name(),
                                       f"Class '{item.get_name()}' has the name of a primitive type; "
                                       "the primitive type takes precedence for attributes.")
        for item in diagram.get_enums():
            enum = BaseMlmEnumType(item.get_name())
            for literal in item.get_literals():
                enum.add_enum_value(literal)
            enums[item.get_name()] = enum
            model.add_enum(enum)
            if item.get_name().lower() in PRIMITIVE_TYPES:
                diagram.add_adaptation("Primitive type name conflict", item.get_name(),
                                       f"Enumeration '{item.get_name()}' has the name of a primitive type; "
                                       "the primitive type takes precedence for attributes.")
        model.set_instances_of_mlm_objects()
        return classes, enums

    @staticmethod
    def _set_generalizations(diagram: ClassDiagram, classes: dict[str, BaseMlmObject]) -> None:
        """Connect each class to its declared parent."""
        for item in diagram.get_classes():
            for parent in item.get_parents():
                classes[item.get_name()].add_parent_class(classes[parent])

    def _create_attributes(self, model: BaseMlmModel, diagram: ClassDiagram, package: str,
                           classes: dict[str, BaseMlmObject], enums: dict[str, BaseMlmEnumType]) -> None:
        """Create attributes and connect each one to its owner and type."""
        for item in diagram.get_classes():
            owner = classes[item.get_name()]
            for attribute in item.get_attributes():
                type_path, spec = self._resolve_attribute_type(
                    model, diagram, package, item.get_name(), attribute.get_type_name(), classes, enums)
                attr = BaseMlmAttribute(attribute.get_name(), type_path, 0, spec,
                                        multiplicity=Multiplicity(1, 1))
                attr.set_owner(owner)
                owner.add_attr(attr)

    @staticmethod
    def _resolve_attribute_type(model: BaseMlmModel, diagram: ClassDiagram, package: str,
                                owner_name: str, type_name: str, classes: dict[str, BaseMlmObject],
                                enums: dict[str, BaseMlmEnumType]) -> tuple[str, TypeSpec]:
        """Resolve a primitive, enum or class type, using String for unknown types."""
        type_path = PRIMITIVE_TYPES.get(type_name.lower())
        if type_path:
            return type_path, model.parse_attribute_type(type_path)
        if type_name in enums:
            return f"{package}::{type_name}", enums[type_name]
        if type_name in classes:
            return f"{package}::{type_name}", classes[type_name]
        type_path = PRIMITIVE_TYPES["string"]
        diagram.add_adaptation(UNKNOWN_TYPE, owner_name, f"Unknown type '{type_name}' replaced by String.")
        return type_path, model.parse_attribute_type(type_path)

    @staticmethod
    def _create_associations(model: BaseMlmModel, diagram: ClassDiagram,
                             classes: dict[str, BaseMlmObject]) -> None:
        """Create associations and their ends using the normalized classes and bounds."""
        for item in diagram.get_associations():
            association = BaseMlmAssociation(item.get_name() or "associated_to", 0, 0,
                                             item.get_target_role(), item.get_source_role())
            association.xml_attributes = {"sourceVisibleFromTarget": "true", "targetVisibleFromSource": "true"}
            association.set_source_object(classes[item.get_source()])
            association.set_target_object(classes[item.get_target()])
            source = item.get_source_multiplicity()
            target = item.get_target_multiplicity()
            association.set_source_multiplicity(source.get_lower(), source.get_upper())
            association.set_target_multiplicity(target.get_lower(), target.get_upper())
            model.add_association(association)
        model.add_association_ends()
        for association in model.get_associations():
            association.get_source_association_end().set_owner(association.get_source_object())
            association.get_target_association_end().set_owner(association.get_target_object())

    @staticmethod
    def _create_import_report(diagram: ClassDiagram) -> ImportReport:
        """Collect the diagram adaptations in an import report."""
        report = ImportReport()
        for adaptation in diagram.get_adaptations():
            report.add_adaptation(adaptation)
        return report

