from collections import defaultdict
from typing import List

from .helpers import get_ancestors, get_descendants
from .violations import ConstraintViolation


class BaseMLMValidator:
    """Checks a model against the non-Type BaseMLM integrity constraints."""

    def __init__(self, model):
        """Create a validator for the given ``FmmlxModel``."""
        self._model = model

    @property
    def model(self):
        """Return the model that is being checked."""
        return self._model

    def validate(self) -> List[ConstraintViolation]:
        """Run all implemented constraints and return every violation found."""
        violations = []
        violations.extend(self.validate_c1_valid_element_name())
        violations.extend(self.validate_c2_unique_object_name())
        violations.extend(self.validate_c3_unique_attribute_name())
        violations.extend(self.validate_c4_no_type_properties_in_pure_objects())
        violations.extend(self.validate_c5_no_generalization_between_pure_objects())
        violations.extend(self.validate_c6_abstract_classes())
        violations.extend(self.validate_c7_no_metaclass_instances_on_l0())
        violations.extend(self.validate_c8_valid_object_level())
        violations.extend(self.validate_c9_pure_generalization_relationships())
        violations.extend(self.validate_c10_no_cyclic_hierarchies())
        violations.extend(self.validate_c13_valid_instantiation_level())
        violations.extend(self.validate_c15_necessary_slots_provided())
        violations.extend(self.validate_c16_multiplicity_conformance())
        return violations

    def validate_c1_valid_element_name(self) -> List[ConstraintViolation]:
        """Check C-1: every model element must have a non-empty name."""
        violations = []
        for element, name in self._named_elements():
            if name == "":
                violations.append(ConstraintViolation(
                    "C-1", "Model element name must not be empty", element))
        return violations

    def validate_c2_unique_object_name(self) -> List[ConstraintViolation]:
        """Check C-2: every object name must be unique in the model."""
        names = defaultdict(list)
        for obj in self.model.mlm_objects:
            names[self._element_name(obj)].append(obj)

        violations = []
        for name, objects in names.items():
            if len(objects) > 1:
                violations.append(ConstraintViolation(
                    "C-2", f"Object name '{name}' is used more than once", objects))
        return violations

    def validate_c3_unique_attribute_name(self) -> List[ConstraintViolation]:
        """Check C-3: attribute names must be unique, including inherited attributes."""
        violations = []
        for obj in self.model.mlm_objects:
            attributes = []
            seen = set()
            for candidate in [obj, *get_ancestors(obj)]:
                for attribute in getattr(candidate, "attr_list", []):
                    marker = id(attribute)
                    if marker not in seen:
                        seen.add(marker)
                        attributes.append(attribute)

            names = defaultdict(list)
            for attribute in attributes:
                names[self._element_name(attribute)].append(attribute)
            for name, matching_attributes in names.items():
                if len(matching_attributes) > 1:
                    violations.append(ConstraintViolation(
                        "C-3",
                        f"Attribute name '{name}' is not unique for '{self._element_name(obj)}'",
                        obj))
        return violations

    def validate_c4_no_type_properties_in_pure_objects(self) -> List[ConstraintViolation]:
        """Check C-4: a level-0 pure object must not have attributes."""
        violations = []
        for obj in self.model.mlm_objects:
            if obj.level == 0 and len(getattr(obj, "attr_list", [])) != 0:
                violations.append(ConstraintViolation(
                    "C-4",
                    "A pure object on level 0 must not have type properties",
                    obj))
        return violations

    def validate_c5_no_generalization_between_pure_objects(self) -> List[ConstraintViolation]:
        """Check C-5: a level-0 pure object must not have generalization children."""
        violations = []
        for obj in self.model.mlm_objects:
            if obj.level != 0:
                continue
            children = [
                candidate for candidate in self.model.mlm_objects
                if obj in getattr(candidate, "parent_classes", [])
            ]
            if children:
                violations.append(ConstraintViolation(
                    "C-5",
                    "A level-0 object must not have generalization children",
                    obj))
        return violations

    def validate_c7_no_metaclass_instances_on_l0(self) -> List[ConstraintViolation]:
        """Check C-7: a level-0 object must not be an instance of MetaClass."""
        violations = []
        for obj in self.model.mlm_objects:
            class_of_object = getattr(obj, "class_of_object", None)
            if obj.level == 0 and self._is_metaclass(class_of_object):
                violations.append(ConstraintViolation(
                    "C-7",
                    "A level-0 object must not be an instance of MetaClass",
                    obj))
        return violations

    def validate_c8_valid_object_level(self) -> List[ConstraintViolation]:
        """Check C-8: an object level must be valid for its class level."""
        violations = []
        for obj in self.model.mlm_objects:
            class_of_object = getattr(obj, "class_of_object", None)
            if class_of_object is None:
                continue

            valid_level = obj.level >= 0 and (
                obj.level == class_of_object.level - 1
                or self._is_metaclass(class_of_object)
            )
            if not valid_level:
                violations.append(ConstraintViolation(
                    "C-8",
                    "Object level must be non-negative and one lower than its class level",
                    obj))
        return violations

    def validate_c9_pure_generalization_relationships(self) -> List[ConstraintViolation]:
        """Check C-9: a generalization child and parent must share one level."""
        violations = []
        for obj in self.model.mlm_objects:
            for parent in getattr(obj, "parent_classes", []):
                if obj.level != parent.level:
                    violations.append(ConstraintViolation(
                        "C-9",
                        "A generalization child and its parent must be on the same level",
                        obj))
        return violations

    def validate_c10_no_cyclic_hierarchies(self) -> List[ConstraintViolation]:
        """Check C-10: generalization and instance-of relationships must not cycle."""
        violations = []
        for obj in self.model.mlm_objects:
            if obj in get_ancestors(obj):
                violations.append(ConstraintViolation(
                    "C-10",
                    "An object must not occur among its own ancestors",
                    obj))
        return violations

    def validate_c6_abstract_classes(self) -> List[ConstraintViolation]:
        """Check C-6: abstract objects must be typed and must have no instances."""
        violations = []
        for obj in self.model.mlm_objects:
            if not getattr(obj, "is_abstract", False):
                continue
            if obj.level < 1:
                violations.append(ConstraintViolation(
                    "C-6",
                    "An abstract object must be on level 1 or higher",
                    obj))
            if len(getattr(obj, "instances", [])) != 0:
                violations.append(ConstraintViolation(
                    "C-6",
                    "An abstract object must not have instances",
                    obj))
        return violations

    def validate_c13_valid_instantiation_level(self) -> List[ConstraintViolation]:
        """Check C-13: an attribute level must be from zero up to its owner level."""
        violations = []
        for obj in self.model.mlm_objects:
            for attribute in getattr(obj, "attr_list", []):
                owner = getattr(attribute, "owner", None) or obj
                inst_level = self._as_int(getattr(attribute, "inst_level", None))
                owner_level = self._as_int(getattr(owner, "level", None))
                if inst_level is None or owner_level is None or not (0 <= inst_level < owner_level):
                    violations.append(ConstraintViolation(
                        "C-13",
                        "An attribute instantiation level must be at least 0 and lower than its owner level",
                        attribute))
        return violations

    def validate_c15_necessary_slots_provided(self) -> List[ConstraintViolation]:
        """Check C-15: each required descendant must provide a slot for an attribute."""
        violations = []
        for owner in self.model.mlm_objects:
            for attribute in getattr(owner, "attr_list", []):
                inst_level = self._as_int(getattr(attribute, "inst_level", None))
                if inst_level is None:
                    continue
                descendants = [
                    descendant for descendant in get_descendants(self.model, owner)
                    if descendant.level == inst_level
                ]
                for descendant in descendants:
                    if not any(
                        self._slot_matches_attribute(slot, attribute)
                        for slot in getattr(descendant, "slot_list", [])
                    ):
                        violations.append(ConstraintViolation(
                            "C-15",
                            f"Object '{self._element_name(descendant)}' must provide a slot for attribute "
                            f"'{self._element_name(attribute)}'",
                            descendant))
        return violations

    def validate_c16_multiplicity_conformance(self) -> List[ConstraintViolation]:
        """Check C-16: slot value counts must fit the attribute multiplicity."""
        violations = []
        for obj in self.model.mlm_objects:
            for slot in getattr(obj, "slot_list", []):
                attribute = self._slot_attribute(slot)
                multiplicity = self._get_multiplicity(attribute)
                if attribute is None or multiplicity is None:
                    continue
                value_count = len(slot.get_values_as_list())
                lower_bound = multiplicity.min_multiplicity
                upper_bound_ok = (
                    multiplicity.is_unbounded
                    or value_count <= multiplicity.max_multiplicity
                )
                if value_count < lower_bound or not upper_bound_ok:
                    violations.append(ConstraintViolation(
                        "C-16",
                        f"Slot '{self._element_name(slot)}' has {value_count} values, "
                        f"but its multiplicity is {multiplicity}",
                        slot))
        return violations

    @staticmethod
    def _is_metaclass(obj) -> bool:
        return obj is not None and getattr(obj, "name", None) == "MetaClass"

    def _named_elements(self):
        for obj in self.model.mlm_objects:
            yield obj, self._element_name(obj)
            for attribute in getattr(obj, "attr_list", []):
                yield attribute, self._element_name(attribute)
            for slot in getattr(obj, "slot_list", []):
                yield slot, self._element_name(slot)
            for operation in getattr(obj, "operations_list", []):
                yield operation, self._element_name(operation)
            for constraint in getattr(obj, "constraints_list", []):
                yield constraint, self._element_name(constraint)

        for association in getattr(self.model, "associations", []):
            yield association, self._element_name(association)
        for enum in getattr(self.model, "enums", []):
            yield enum, self._element_name(enum)

    @staticmethod
    def _element_name(element) -> str:
        """Return the common model-element name used by this project."""
        return getattr(element, "name", "")

    @staticmethod
    def _as_int(value):
        """Return an integer value or ``None`` when the value is not usable."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _get_multiplicity(attribute):
        """Return the multiplicity stored directly or through an association end."""
        if attribute is None:
            return None
        multiplicity = getattr(attribute, "multiplicity", None)
        if multiplicity is not None:
            return multiplicity
        association = getattr(attribute, "association", None)
        if association is None:
            return None
        if getattr(attribute, "is_source_end", False):
            return association.target_multiplicity
        return association.source_multiplicity

    @staticmethod
    def _slot_attribute(slot):
        """Return the attribute represented by a slot, including a slot link."""
        getter = getattr(slot, "get_attribute", None)
        if getter is not None:
            return getter()
        return getattr(slot, "attribute", None)

    def _slot_matches_attribute(self, slot, attribute) -> bool:
        """Match a slot to an attribute by reference or by its model name."""
        slot_attribute = self._slot_attribute(slot)
        if slot_attribute is attribute:
            return True
        return (
            slot_attribute is None
            and self._element_name(slot) == self._element_name(attribute)
        )
