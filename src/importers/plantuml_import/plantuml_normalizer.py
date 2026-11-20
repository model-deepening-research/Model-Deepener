"""Rewrites a PlantUML diagram so that it only uses concepts the XModeler format knows."""
from typing import Dict, List, Optional, Tuple

from src.importers.class_diagram import (ASSOCIATION_CLASS,
                                            COMPOSITION_WHOLE_END, CONSTRAINT_NOT_EXPORTED,
                                            EXACTLY_ONE, INVALID_MULTIPLICITY, MISSING_MULTIPLICITY, N_ARY_ASSOCIATION,
                                            ClassDiagram, RawRelation, UmlAssociation, UmlAttribute,
                                            UmlClass, UmlMultiplicity, ZERO_TO_MANY, lower_first, to_identifier)
from src.importers.plantuml_import.plantuml_reader import parse_multiplicity
from src.importers.class_diagram_normalizer import ClassDiagramNormalizer

GENERALIZATION_ARROW_START = "<|"
GENERALIZATION_ARROW_END = "|>"
COMPOSITION_ARROW_SIGN = "*"


class PlantUmlNormalizer(ClassDiagramNormalizer):
    """Rewrite prerequisites first: classes before relations, associations before association classes.

    Assign roles last, when every association is known. Hints are grouped by relation position.
    """

    def __init__(self, diagram: ClassDiagram) -> None:
        """Sort the relation lines by what they describe, because each kind has its own step.

        Each relation is stored with its position in the text.
        """
        self._diagram = diagram
        self._hints: Dict[int, List[Tuple[str, str, str]]] = {}
        self._diamond_legs: Dict[str, List[RawRelation]] = {}
        self._generalizations: List[Tuple[int, RawRelation]] = []
        self._association_relations: List[Tuple[int, RawRelation]] = []
        self._enum_relations: List[Tuple[int, RawRelation]] = []
        self._association_of_position: Dict[int, UmlAssociation] = {}
        for name in diagram.get_diamonds():
            self._diamond_legs[name] = []
        self._sort_relations()

    def _sort_relations(self) -> None:
        """Sort the relation lines into diamond legs, generalizations, enum relations and associations."""
        for position, relation in enumerate(self._diagram.get_relations()):
            if relation.get_left() in self._diamond_legs:
                self._diamond_legs[relation.get_left()].append(relation)
            elif relation.get_right() in self._diamond_legs:
                self._diamond_legs[relation.get_right()].append(relation)
            elif relation.is_generalization():
                self._generalizations.append((position, relation))
            elif self._diagram.has_enum(relation.get_left()) or self._diagram.has_enum(relation.get_right()):
                self._enum_relations.append((position, relation))
            else:
                self._association_relations.append((position, relation))

    def normalize(self) -> None:
        """Apply prerequisite rules before dependent conversions, then complete bounds and roles."""
        self._create_classes()
        self._set_generalizations()
        self._convert_associations()
        self._convert_aggregations()
        self._convert_compositions()
        self._resolve_association_classes()
        self._convert_enum_relations()
        self._resolve_n_ary_associations()
        self._report_constraints()
        self._add_hints_to_diagram()
        self._fill_missing_multiplicities()
        self._assign_role_names()

    def _create_classes(self) -> None:
        """Create the classes that are only used and never declared.

        In A -- B without a line class B, the class B is created here and becomes an addMetaClass
        element in the XML. The classes are created in the order of the lines that use them.
        """
        for relation in self._diagram.get_relations():
            if relation.get_left() not in self._diamond_legs and relation.get_right() not in self._diamond_legs:
                self._create_classes_of_relation(relation)
        for middle, end_a, end_b in self._diagram.get_association_classes():
            if not self._diagram.has_note(middle):
                self._diagram.get_or_create_class(middle)
                self._diagram.get_or_create_class(end_a)
                self._diagram.get_or_create_class(end_b)
        for diamond, legs in self._diamond_legs.items():
            self._diagram.get_or_create_class(self._diamond_class_name(diamond, legs))
            for leg in legs:
                self._diagram.get_or_create_class(self._diamond_participant(leg, diamond))

    def _create_classes_of_relation(self, relation: RawRelation) -> None:
        """Create the classes of one relation line. An enum itself does not become a class."""
        if relation.is_generalization():
            child, parent = self._child_and_parent(relation)
            self._diagram.get_or_create_class(child)
            self._diagram.get_or_create_class(parent)
        elif self._diagram.has_enum(relation.get_left()):
            self._diagram.get_or_create_class(relation.get_right())
        elif self._diagram.has_enum(relation.get_right()):
            self._diagram.get_or_create_class(relation.get_left())
        else:
            self._diagram.get_or_create_class(relation.get_left())
            self._diagram.get_or_create_class(relation.get_right())

    @staticmethod
    def _child_and_parent(relation: RawRelation) -> Tuple[str, str]:
        """Return the child and the parent. The triangle of the arrow points at the parent."""
        if relation.get_arrow().startswith(GENERALIZATION_ARROW_START):
            return relation.get_right(), relation.get_left()
        return relation.get_left(), relation.get_right()

    def _diamond_class_name(self, diamond: str, legs: List[RawRelation]) -> str:
        """Return the name of the new class: all participants in a row, or the diamond without any."""
        class_name = ""
        for leg in legs:
            class_name += self._diamond_participant(leg, diamond)
        if class_name == "":
            return diamond
        return class_name

    @staticmethod
    def _diamond_participant(leg: RawRelation, diamond: str) -> str:
        """Return the class on the other side of the diamond."""
        if leg.get_left() == diamond:
            return leg.get_right()
        return leg.get_left()

    def _set_generalizations(self) -> None:
        """Connect every declared child to its parent classes."""
        for _position, relation in self._generalizations:
            child, parent = self._child_and_parent(relation)
            self._diagram.get_class(child).add_parent(parent)

    def _add_hint(self, position: int, problem_type: str, object_name: str, description: str) -> None:
        """Store a hint for the user together with the position of the line it belongs to."""
        if position not in self._hints:
            self._hints[position] = []
        self._hints[position].append((problem_type, object_name, description))

    def _convert_associations(self) -> None:
        """Take over associations, written A "1" -- "0..*" B : label, and their direction.

        A reading-direction marker takes precedence over an arrowhead. Both ends remain navigable.
        """
        for position, relation in self._association_relations:
            source_multiplicity = self._read_multiplicity(relation.get_left_multiplicity(), position)
            target_multiplicity = self._read_multiplicity(relation.get_right_multiplicity(), position)
            name = self._association_name(relation.get_label())
            if not name:
                arrow = relation.get_arrow()
                name = "composition_of" if "*" in arrow else "aggregation_of" if "o" in arrow else "associated_to"
            if self._reverse_association(relation):
                association = UmlAssociation(relation.get_right(), relation.get_left(), target_multiplicity,
                                             source_multiplicity, name)
            else:
                association = UmlAssociation(relation.get_left(), relation.get_right(), source_multiplicity,
                                             target_multiplicity, name)
            if not self._association_name(relation.get_label()):
                association.mark_name_generated()
            self._diagram.add_association(association)
            self._association_of_position[position] = association

    @staticmethod
    def _reverse_association(relation: RawRelation) -> bool:
        """Return whether the right-hand class is the source of a relation."""
        label = (relation.get_label() or "").rstrip()
        if label.endswith(("<", ">")):
            return label.endswith("<")
        arrow = relation.get_arrow()
        return arrow.startswith("<") and not arrow.endswith(">")

    def _read_multiplicity(self, text: Optional[str], position: int) -> Optional[UmlMultiplicity]:
        """Return the multiplicity of a text such as 0..*. None means that nothing was written.

        An invalid text becomes 0..* and is reported, so that the import can continue.
        """
        if text is None or text.strip() == "":
            return None
        multiplicity = parse_multiplicity(text)
        if multiplicity is None:
            self._add_hint(position, INVALID_MULTIPLICITY, "", f"Invalid multiplicity '{text}' replaced by 0..*.")
            return ZERO_TO_MANY
        return multiplicity

    @staticmethod
    def _association_name(label: Optional[str]) -> Optional[str]:
        """Return the association name for a label, or None if the label holds no valid character."""
        if label is None or label == "":
            return None
        name = label.rstrip().removesuffix(">").removesuffix("<").strip()
        if name == "":
            return None
        return name

    def _convert_aggregations(self) -> None:
        """Keep A o-- B as the ordinary association already built by _convert_associations.

        XML has no aggregation marker. No further change to its bounds or navigation is needed.
        """

    def _convert_compositions(self) -> None:
        """Represent compositions as ordinary associations and check the whole end.

        A "1" *-- "0..*" B and B --* A are compositions with the whole A. In the XML they become a
        normal addAssociation. A missing whole end becomes exactly one; a larger bound is kept
        with a warning, so the user's declared multiplicity is not silently changed.
        """
        for position, relation in self._association_relations:
            arrow = relation.get_arrow()
            association = self._association_of_position[position]
            if COMPOSITION_ARROW_SIGN not in arrow:
                continue
            reverse = self._reverse_association(relation)
            if arrow.startswith(COMPOSITION_ARROW_SIGN) != reverse:
                association.set_source_multiplicity(self._check_whole_end(
                    association.get_source_multiplicity(), association.get_source(), association.get_target(), position))
            elif COMPOSITION_ARROW_SIGN in arrow:
                association.set_target_multiplicity(self._check_whole_end(
                    association.get_target_multiplicity(), association.get_target(), association.get_source(), position))

    def _check_whole_end(self, multiplicity: Optional[UmlMultiplicity], whole: str, part: str,
                         position: int) -> UmlMultiplicity:
        """Return the multiplicity of the whole. More than one is kept, but reported."""
        if multiplicity is None:
            return EXACTLY_ONE
        if not multiplicity.is_at_most_one():
            self._add_hint(position, COMPOSITION_WHOLE_END, whole,
                           f"Composition {whole} *-- {part}: the whole end has '{multiplicity.get_text()}', expected at most 1.")
        return multiplicity

    def _resolve_association_classes(self) -> None:
        """Resolve association classes, written (A, B) .. C. This needs the associations of the earlier step.

        A "mA" -- "mB" B becomes two addAssociation elements in the XML: A "1" -- "mB" C and
        C "mA" -- "1" B. The line (A, B) .. N1 with a note N1 is no association class.
        """
        for index, (middle, end_a, end_b) in enumerate(self._diagram.get_association_classes()):
            if not self._diagram.has_note(middle):
                self._resolve_one_association_class(middle, end_a, end_b, self._association_class_position(index))

    def _resolve_one_association_class(self, middle: str, end_a: str, end_b: str, position: int) -> None:
        """Replace the association A-B by two associations over the class in the middle.

        Without such an association, the two new ones get default multiplicities and a hint.
        """
        candidates = self._associations_between(end_a, end_b)
        if len(candidates) == 0:
            self._add_hint(position, ASSOCIATION_CLASS, middle,
                           f"Association class {middle}: no association {end_a}-{end_b} found.")
            self._diagram.add_association(UmlAssociation(end_a, middle, EXACTLY_ONE, ZERO_TO_MANY))
            self._diagram.add_association(UmlAssociation(middle, end_b, ZERO_TO_MANY, EXACTLY_ONE))
            return
        base = self._choose_base_association(candidates, middle, end_a, end_b, position)
        self._diagram.remove_association(base)
        source_association = UmlAssociation(
            base.get_source(), middle, EXACTLY_ONE, base.get_target_multiplicity(), base.get_name())
        target_association = UmlAssociation(
            middle, base.get_target(), base.get_source_multiplicity(), EXACTLY_ONE, base.get_name())
        if base.is_name_generated():
            source_association.mark_name_generated()
            target_association.mark_name_generated()
        self._diagram.add_association(source_association)
        self._diagram.add_association(target_association)

    def _associations_between(self, class_a: str, class_b: str) -> List[UmlAssociation]:
        """Return all associations that link the two classes, in any direction."""
        associations = []
        for association in self._diagram.get_associations():
            if association.connects(class_a, class_b):
                associations.append(association)
        return associations

    def _choose_base_association(self, candidates: List[UmlAssociation], middle: str, end_a: str, end_b: str,
                                 position: int) -> UmlAssociation:
        """Return the first association without a name, otherwise the first one. Several are reported."""
        base = candidates[0]
        chosen = f"named {base.get_name()}"
        for candidate in candidates:
            is_unnamed = any(
                candidate is association and not self._association_name(self._diagram.get_relations()[index].get_label())
                for index, association in self._association_of_position.items()
            )
            if is_unnamed:
                base = candidate
                chosen = "without a name"
                break
        if len(candidates) > 1:
            self._add_hint(position, ASSOCIATION_CLASS, middle,
                           f"Association class {middle}: {len(candidates)} associations {end_a}-{end_b}; "
                           f"the one {chosen} is used.")
        return base

    def _association_class_position(self, index: int) -> int:
        """Return the hint position of an association class: after all relation lines."""
        return len(self._diagram.get_relations()) + index

    def _convert_enum_relations(self) -> None:
        """Turn a relation to an enum, written Car --> "0..1" Color : paint, into an attribute.

        In the XML this becomes an addAttribute element of the class, with the enum as its type. The
        name comes from the label, otherwise from the enum. An attribute of that type already covers it.
        """
        for position, relation in self._enum_relations:
            if self._diagram.has_enum(relation.get_left()):
                owner_name, enum_name = relation.get_right(), relation.get_left()
                multiplicity_text = relation.get_left_multiplicity()
            else:
                owner_name, enum_name = relation.get_left(), relation.get_right()
                multiplicity_text = relation.get_right_multiplicity()
            owner = self._diagram.get_class(owner_name)
            if not self._has_attribute_of_type(owner, enum_name):
                self._add_enum_attribute(owner, enum_name, multiplicity_text, relation.get_label(), position)

    @staticmethod
    def _has_attribute_of_type(uml_class: UmlClass, type_name: str) -> bool:
        """Return True if the class has an attribute of this type."""
        for attribute in uml_class.get_attributes():
            if attribute.get_type_name() == type_name:
                return True
        return False

    def _add_enum_attribute(self, owner: UmlClass, enum_name: str, multiplicity_text: Optional[str],
                            label: Optional[str], position: int) -> None:
        """Add the attribute for an enum relation. Without a multiplicity the attribute has exactly one value."""
        name = enum_name
        if label is not None and to_identifier(label) != "":
            name = to_identifier(label)
        multiplicity = self._read_multiplicity(multiplicity_text, position)
        if multiplicity is None:
            multiplicity = EXACTLY_ONE
        owner.add_attribute(UmlAttribute(lower_first(name), enum_name, multiplicity))

    def _resolve_n_ary_associations(self) -> None:
        """Resolve an n-ary association, written <> d with d -- A, d -- "0..1" B, d -- C.

        In the XML the diamond becomes the class ABC (addMetaClass) with one addAssociation element
        per line, because the XML format only knows associations between two classes.
        """
        for index, (diamond, legs) in enumerate(self._diamond_legs.items()):
            position = self._diamond_position(index)
            class_name = self._diamond_class_name(diamond, legs)
            for leg in legs:
                multiplicity = self._read_multiplicity(self._diamond_participant_multiplicity(leg, diamond), position)
                self._diagram.add_association(UmlAssociation(
                    class_name, self._diamond_participant(leg, diamond), ZERO_TO_MANY, multiplicity))
            self._add_hint(
                position, N_ARY_ASSOCIATION, class_name,
                f"N-ary association '{diamond}' turned into class '{class_name}'; please check the multiplicities.")

    def _diamond_position(self, index: int) -> int:
        """Return the hint position of a diamond: after all association classes."""
        return self._association_class_position(len(self._diagram.get_association_classes())) + index

    @staticmethod
    def _diamond_participant_multiplicity(leg: RawRelation, diamond: str) -> Optional[str]:
        """Return the multiplicity text on the side of the class, not on the side of the diamond."""
        if leg.get_left() == diamond:
            return leg.get_right_multiplicity()
        return leg.get_left_multiplicity()

    def _report_constraints(self) -> None:
        """Report constraints that the XML format cannot hold, so they do not reach the XML.

        These are labels on generalizations, written A <|-- B : {total; disjoint}, and notes on two
        classes, written note "{XOR}" as N1 with (A, B) .. N1.
        """
        self._report_generalization_constraints()
        self._report_note_constraints()

    def _report_generalization_constraints(self) -> None:
        """Report the label of a generalization that was kept.

        The first parent of a class stays, so a generalization was kept if its parent is the one
        the class has now. A generalization that was left out already has its own hint.
        """
        for position, relation in self._generalizations:
            child, parent = self._child_and_parent(relation)
            if relation.get_label() is not None and parent in self._diagram.get_class(child).get_parents():
                self._add_hint(position, CONSTRAINT_NOT_EXPORTED, child,
                               f"Generalization constraint '{relation.get_label()}' on {child} -> {parent} is not exported.")

    def _report_note_constraints(self) -> None:
        """Report each note that is attached to two classes."""
        for index, (middle, end_a, end_b) in enumerate(self._diagram.get_association_classes()):
            if self._diagram.has_note(middle):
                self._add_hint(self._association_class_position(index), CONSTRAINT_NOT_EXPORTED, middle,
                               f"Constraint '{self._diagram.get_note_text(middle)}' on ({end_a}, {end_b}) is not exported.")

    def _add_hints_to_diagram(self) -> None:
        """Add the stored hints to the diagram in the order of their lines."""
        for position in sorted(self._hints):
            for problem_type, object_name, description in self._hints[position]:
                self._diagram.add_adaptation(problem_type, object_name, description)

    def _fill_missing_multiplicities(self) -> None:
        """Complete associations without a multiplicity, written A -- B.

        In the XML both ends become Seq{0,-1,false,false}, which is 0..*. A hint says how many were set.
        """
        missing = 0
        for association in self._diagram.get_associations():
            if association.get_source_multiplicity() is None:
                association.set_source_multiplicity(ZERO_TO_MANY)
                missing += 1
            if association.get_target_multiplicity() is None:
                association.set_target_multiplicity(ZERO_TO_MANY)
                missing += 1
        if missing > 0:
            self._diagram.add_adaptation(MISSING_MULTIPLICITY, "",
                                         f"{missing} missing association multiplicities set to 0..*.")
