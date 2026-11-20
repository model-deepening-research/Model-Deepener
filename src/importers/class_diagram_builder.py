"""Build a BaseMLM model from a normalized class diagram."""
from src.basemlm.basemlm_association import BaseMlmAssociation
from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_enum_type import BaseMlmEnumType
from src.basemlm.basemlm_object import BaseMlmObject
from src.basemlm.basemlm_type_spec import TypeSpec
from src.basemlm.multiplicity import Multiplicity

from src.basemlm.basemlm_model import BaseMlmModel
from src.importers.model_names import normalized_name, unique_name, make_inherited_names_unique
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
        make_inherited_names_unique(model.get_objects())
        report = self._create_import_report(diagram)
        for adaptation in report.get_adaptations():
            element = classes.get(adaptation.get_object_name()) or enums.get(adaptation.get_object_name())
            if element is None and adaptation.get_problem_type() == "Constraint not exported":
                for alias, left, right in diagram.get_association_classes():
                    if (alias == adaptation.get_object_name() and diagram.has_note(alias)
                            and f"on ({left}, {right})" in adaptation.get_description()):
                        for name in (left, right):
                            if name in classes:
                                classes[name].add_import_note(adaptation.get_description(), True)
            if element is not None:
                description = adaptation.get_description()
                kind = adaptation.get_problem_type()
                if kind == UNKNOWN_TYPE:
                    continue
                if hasattr(element, "get_regular_attributes"):
                    for attribute in element.get_regular_attributes():
                        original = getattr(attribute, "_import_source_name", attribute.get_name())
                        if f"{adaptation.get_object_name()}.{original}" in description:
                            element = attribute
                            break
                field = "name"
                if hasattr(element, "get_type_spec"):
                    if "multiplicity" in kind.lower() or "multiplicity" in description.lower():
                        field = "multiplicity"
                    elif "type" in kind.lower() or "type" in description.lower():
                        field = "type"
                element.add_import_note(description, report.is_serious_adaptation(adaptation), field)
        return report

    @staticmethod
    def _create_classes_and_enums(
            model: BaseMlmModel, diagram: ClassDiagram, package: str,
    ) -> tuple[dict[str, BaseMlmObject], dict[str, BaseMlmEnumType]]:
        """Create classes and enums and report names that match primitive types."""
        classes: dict[str, BaseMlmObject] = {}
        enums: dict[str, BaseMlmEnumType] = {}
        used_names: set[str] = set()
        for item in diagram.get_classes():
            name = unique_name(normalized_name(item.get_name()), used_names)
            obj = BaseMlmObject(f"{package}::{name}", name, "1",
                                BaseMlmObject.meta_class(), str(item.is_abstract()).lower(), model)
            if name != item.get_name():
                obj.add_import_note(f"{item.get_name()} \u2192 {name}")
            for operation in item.get_skipped_operations():
                obj.add_import_note(f"Operation skipped: {operation}")
            classes[item.get_name()] = obj
            model.add_mlm_object(obj)
            if item.get_name().lower() in PRIMITIVE_TYPES:
                diagram.add_adaptation("Primitive type name conflict", item.get_name(),
                                       f"Class '{item.get_name()}' has the name of a primitive type; "
                                       "the primitive type takes precedence for attributes.")
        for item in diagram.get_enums():
            name = unique_name(normalized_name(item.get_name()), used_names)
            enum = BaseMlmEnumType(name)
            if name != item.get_name():
                enum.add_import_note(f"{item.get_name()} \u2192 {name}")
            used_literals: set[str] = set()
            for literal in item.get_literals():
                value = unique_name(normalized_name(literal), used_literals)
                enum.add_enum_value(value)
                if value != literal:
                    enum.add_import_note(f"{literal} \u2192 {value}", field=f"value:{value}")
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
            used_names: set[str] = set()
            for attribute in item.get_attributes():
                name = unique_name(normalized_name(attribute.get_name(), attribute=True), used_names)
                type_path, spec = self._resolve_attribute_type(
                    model, diagram, package, item.get_name(), attribute.get_type_name(), classes, enums)
                attr = BaseMlmAttribute(name, type_path, 0, spec,
                                        multiplicity=Multiplicity(1, 1))
                attr._import_source_name = attribute.get_name()
                if (attribute.get_type_name().lower() not in PRIMITIVE_TYPES
                        and attribute.get_type_name() not in enums and attribute.get_type_name() not in classes):
                    attr.add_import_note(f"Unknown type '{attribute.get_type_name()}' replaced by String.", True, "type")
                if name != attribute.get_name():
                    attr.add_import_note(f"{attribute.get_name()} \u2192 {name}")
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
            return f"{package}::{enums[type_name].get_name()}", enums[type_name]
        if type_name in classes:
            return f"{package}::{classes[type_name].get_name()}", classes[type_name]
        type_path = PRIMITIVE_TYPES["string"]
        diagram.add_adaptation(UNKNOWN_TYPE, owner_name, f"Unknown type '{type_name}' replaced by String.")
        return type_path, model.parse_attribute_type(type_path)

    @staticmethod
    def _create_associations(model: BaseMlmModel, diagram: ClassDiagram,
                             classes: dict[str, BaseMlmObject]) -> None:
        """Create associations and their ends using the normalized classes and bounds."""
        used_roles = {name: {attr.get_name() for attr in obj.get_regular_attributes()}
                      for name, obj in classes.items()}
        for item in diagram.get_associations():
            name = normalized_name(item.get_name() or "associated_to", association=True)
            target_role = unique_name(normalized_name(item.get_target_role()), used_roles[item.get_source()])
            source_role = unique_name(normalized_name(item.get_source_role()), used_roles[item.get_target()])
            association = BaseMlmAssociation(name, 0, 0, target_role, source_role)
            if item.is_name_generated():
                association.add_import_note(f"Association name assigned: {name}.")
            if item.get_name() and name != item.get_name():
                association.add_import_note(f"{item.get_name()} \u2192 {name}")
            association.xml_attributes = {"sourceVisibleFromTarget": "true", "targetVisibleFromSource": "true"}
            association.set_source_object(classes[item.get_source()])
            association.set_target_object(classes[item.get_target()])
            source = item.get_source_multiplicity()
            target = item.get_target_multiplicity()
            association.set_source_multiplicity(source.get_lower(), source.get_upper())
            association.set_target_multiplicity(target.get_lower(), target.get_upper())
            model.add_association(association)
            association._generated_source_role = item.is_target_role_generated()
            association._generated_target_role = item.is_source_role_generated()
            association._original_source_role = item.get_target_role()
            association._original_target_role = item.get_source_role()
        model.add_association_ends()
        for association in model.get_associations():
            association.get_source_association_end().set_owner(association.get_source_object())
            association.get_target_association_end().set_owner(association.get_target_object())
            if association.source_access_name != association._original_source_role:
                association.get_source_association_end().add_import_note(
                    f"{association._original_source_role} \u2192 {association.source_access_name}")
            if association.target_access_name != association._original_target_role:
                association.get_target_association_end().add_import_note(
                    f"{association._original_target_role} \u2192 {association.target_access_name}")
            if association._generated_source_role:
                association.get_source_association_end().add_import_note(
                    f"Role name assigned: {association.source_access_name}.")
            if association._generated_target_role:
                association.get_target_association_end().add_import_note(
                    f"Role name assigned: {association.target_access_name}.")

    @staticmethod
    def _create_import_report(diagram: ClassDiagram) -> ImportReport:
        """Collect the diagram adaptations in an import report."""
        report = ImportReport()
        for adaptation in diagram.get_adaptations():
            report.add_adaptation(adaptation)
        return report

