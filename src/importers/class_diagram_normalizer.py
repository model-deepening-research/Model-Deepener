"""Normalize shared class diagram roles."""
from typing import Dict, Set
from src.importers.class_diagram import (ClassDiagram, UmlAssociation, UmlMultiplicity,
                                         COMPOSITION_WHOLE_END, EXACTLY_ONE, lower_first)


class ClassDiagramNormalizer:
    """Assign unique association roles throughout inheritance hierarchies."""

    def __init__(self, diagram: ClassDiagram) -> None:
        """Remember the diagram to normalize."""
        self._diagram = diagram

    def normalize(self) -> None:
        """Complete association role names."""
        self._assign_role_names()

    @staticmethod
    def composition_whole(diagram: ClassDiagram, multiplicity: UmlMultiplicity | None,
                          whole: str, part: str) -> UmlMultiplicity:
        """Complete a missing whole bound and report bounds exceeding one."""
        if multiplicity is None:
            return EXACTLY_ONE
        if not multiplicity.is_at_most_one():
            diagram.add_adaptation(COMPOSITION_WHOLE_END, whole,
                                   f"Composition {whole} *-- {part}: the whole end has '{multiplicity.get_text()}', expected at most 1.")
        return multiplicity

    def _assign_role_names(self) -> None:
        """Assign roles without conflicts in the owner's inheritance hierarchy."""
        ancestors: Dict[str, Set[str]] = {}
        attributes: Dict[str, Set[str]] = {}
        for uml_class in self._diagram.get_classes():
            name = uml_class.get_name()
            attributes[name] = {attribute.get_name() for attribute in uml_class.get_attributes()}
            ancestors[name] = self._ancestor_names(name)

        roles: Dict[str, Set[str]] = {name: set() for name in attributes}
        for name in sorted(attributes, key=lambda item: len(ancestors[item])):
            related = {other for other in attributes
                       if other == name or other in ancestors[name] or name in ancestors[other]}
            used: Set[str] = set()
            for other in related:
                used.update(attributes[other])
                used.update(roles[other])
            for association in self._diagram.get_associations():
                if association.get_source() == name:
                    self._assign_target_role(association, used)
                    roles[name].add(association.get_target_role())
                if association.get_target() == name:
                    self._assign_source_role(association, used)
                    roles[name].add(association.get_source_role())

    def _ancestor_names(self, name: str) -> Set[str]:
        """Return all ancestors of a class, stopping at cycles."""
        ancestors: Set[str] = set()
        pending = list(self._diagram.get_class(name).get_parents())
        while pending:
            parent = pending.pop()
            if parent != name and parent not in ancestors:
                ancestors.add(parent)
                pending.extend(self._diagram.get_class(parent).get_parents())
        return ancestors

    def _assign_target_role(self, association: UmlAssociation, used: Set[str]) -> None:
        """Set the name under which the source reaches the target, unless an attribute has already set it."""
        wish = association.get_target_role() or lower_first(association.get_target())
        association.set_target_role(self._unique_name(wish, used))

    @staticmethod
    def _unique_name(wish: str, used: Set[str]) -> str:
        """Return the name with a numeric suffix if it is already used."""
        candidate = wish
        number = 1
        while candidate in used:
            candidate = f"{wish}{number}"
            number += 1
        used.add(candidate)
        return candidate

    def _assign_source_role(self, association: UmlAssociation, used: Set[str]) -> None:
        """Name the source reached from the target, preserving a role supplied by an attribute."""
        wish = association.get_source_role() or lower_first(association.get_source())
        association.set_source_role(self._unique_name(wish, used))
