"""Rewrites a PlantUML diagram so that it only uses concepts the XModeler format knows."""
from typing import Dict, List, Optional, Set, Tuple

from src.importers.plantuml_diagram import (ASSOCIATION_CLASS, COMPOSITION_WHOLE_END, CONSTRAINT_NOT_EXPORTED,
                                            EXACTLY_ONE, INVALID_MULTIPLICITY, MISSING_MULTIPLICITY, N_ARY_ASSOCIATION,
                                            PlantUmlDiagram, RawRelation, SEVERAL_PARENTS, UmlAssociation, UmlAttribute,
                                            UmlClass, UmlMultiplicity, ZERO_TO_MANY, lower_first, to_identifier)
from src.importers.plantuml_reader import parse_multiplicity

GENERALIZATION_ARROW_START = "<|"
GENERALIZATION_ARROW_END = "|>"
COMPOSITION_ARROW_SIGN = "*"
FIRST_NUMBER_FOR_UNIQUE_NAME = 2


class PlantUmlNormalizer:
    """Applies the rewriting rules to one diagram, one step after the other.

    The steps go through the diagram in their own order, but the user reads the hints in the order
    of the diagram lines. So a step stores each hint with the position of its line, and all hints
    are added to the diagram together once the steps that create them are done.
    """

    def __init__(self, diagram: PlantUmlDiagram) -> None:
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

    def normalize(self) -> None:
        """Run all rules in their fixed order on the diagram.

        Each step needs the classes from the first step. Association classes need the associations.
        N-ary associations come before attributes with a class as type, because this order decides
        the order of the associations in the XML and which association already exists.
        """
        self._create_classes()
        self._set_generalizations()
        self._convert_associations()
        self._convert_compositions()
        self._resolve_association_classes()
        self._convert_enum_relations()
        self._resolve_n_ary_associations()
        self._convert_class_typed_attributes()
        self._report_constraints()
        self._add_hints_to_diagram()
        self._fill_missing_multiplicities()
        self._assign_role_names()

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

    def _add_hint(self, position: int, problem_type: str, object_name: str, description: str) -> None:
        """Store a hint for the user together with the position of the line it belongs to."""
        if position not in self._hints:
            self._hints[position] = []
        self._hints[position].append((problem_type, object_name, description))

    def _add_hints_to_diagram(self) -> None:
        """Add the stored hints to the diagram in the order of their lines."""
        for position in sorted(self._hints):
            for problem_type, object_name, description in self._hints[position]:
                self._diagram.add_adaptation(problem_type, object_name, description)

    def _association_class_position(self, index: int) -> int:
        """Return the hint position of an association class: after all relation lines."""
        return len(self._diagram.get_relations()) + index

    def _diamond_position(self, index: int) -> int:
        """Return the hint position of a diamond: after all association classes."""
        return self._association_class_position(len(self._diagram.get_association_classes())) + index

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

    def _set_generalizations(self) -> None:
        """Set the parents, written Parent <|-- Child or Child --|> Parent.

        In the XML this becomes a changeParent element. The XML format allows one parent, so a
        second one is reported and left out.
        """
        for position, relation in self._generalizations:
            child, parent = self._child_and_parent(relation)
            child_class = self._diagram.get_class(child)
            if child_class.get_parent() is None or child_class.get_parent() == parent:
                child_class.set_parent(parent)
            else:
                self._add_hint(position, SEVERAL_PARENTS, child,
                               f"'{child}' has more than one parent; only '{child_class.get_parent()}' is kept.")

    @staticmethod
    def _child_and_parent(relation: RawRelation) -> Tuple[str, str]:
        """Return the child and the parent. The triangle of the arrow points at the parent."""
        if relation.get_arrow().startswith(GENERALIZATION_ARROW_START):
            return relation.get_right(), relation.get_left()
        return relation.get_left(), relation.get_right()

    def _convert_associations(self) -> None:
        """Take over associations, written A "1" -- "0..*" B : label, and their direction.

        In the XML this becomes an addAssociation element. A --> B can only be navigated from A to
        B, and A <-- B only from B to A. The label becomes the name of the association.
        """
        for position, relation in self._association_relations:
            source_multiplicity = self._read_multiplicity(relation.get_left_multiplicity(), position)
            target_multiplicity = self._read_multiplicity(relation.get_right_multiplicity(), position)
            association = UmlAssociation(relation.get_left(), relation.get_right(), source_multiplicity,
                                         target_multiplicity, self._association_name(relation.get_label()))
            self._set_navigability(association, relation.get_arrow())
            self._diagram.add_association(association)
            self._association_of_position[position] = association

    @staticmethod
    def _association_name(label: Optional[str]) -> Optional[str]:
        """Return the association name for a label, or None if the label holds no valid character."""
        if label is None or label == "":
            return None
        name = to_identifier(label)
        if name == "":
            return None
        return name

    @staticmethod
    def _set_navigability(association: UmlAssociation, arrow: str) -> None:
        """Set the direction from an arrow. An arrow that points both ways or nowhere changes nothing."""
        points_right = arrow.endswith(">") and not arrow.endswith(GENERALIZATION_ARROW_END)
        points_left = arrow.startswith("<") and not arrow.startswith(GENERALIZATION_ARROW_START)
        if points_right and not points_left:
            association.set_navigability(False, True)
        elif points_left and not points_right:
            association.set_navigability(True, False)

    def _convert_compositions(self) -> None:
        """Turn compositions and aggregations into normal associations.

        A "1" *-- "0..*" B and B --* A are compositions with the whole A. In the XML they become a
        normal addAssociation. The whole has at most one, and without a value exactly one. An
        aggregation such as A o-- B needs no change, because its diamond is not taken over.
        """
        for position, relation in self._association_relations:
            arrow = relation.get_arrow()
            association = self._association_of_position[position]
            if arrow.startswith(COMPOSITION_ARROW_SIGN):
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
        self._diagram.add_association(UmlAssociation(
            base.get_source(), middle, EXACTLY_ONE, base.get_target_multiplicity(), base.get_name()))
        self._diagram.add_association(UmlAssociation(
            middle, base.get_target(), base.get_source_multiplicity(), EXACTLY_ONE, base.get_name()))

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
            if candidate.get_name() is None:
                base = candidate
                chosen = "without a name"
                break
        if len(candidates) > 1:
            self._add_hint(position, ASSOCIATION_CLASS, middle,
                           f"Association class {middle}: {len(candidates)} associations {end_a}-{end_b}; "
                           f"the one {chosen} is used.")
        return base

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

    def _convert_class_typed_attributes(self) -> None:
        """Turn an attribute with a class as its type, written Engine motor in class Car, into an association.

        In the XML this becomes an addAssociation element with the role name motor instead of an
        addAttribute element. If the two classes already have an association, the attribute is dropped.
        """
        for uml_class in self._diagram.get_classes():
            for attribute in uml_class.get_attributes():
                if self._diagram.has_class(attribute.get_type_name()):
                    uml_class.remove_attribute(attribute)
                    if len(self._associations_between(uml_class.get_name(), attribute.get_type_name())) == 0:
                        self._add_association_for_attribute(uml_class, attribute)

    def _add_association_for_attribute(self, uml_class: UmlClass, attribute: UmlAttribute) -> None:
        """Add the association for an attribute, which can only be navigated from the class to its type."""
        association = UmlAssociation(uml_class.get_name(), attribute.get_type_name(), ZERO_TO_MANY,
                                     attribute.get_multiplicity(), None)
        association.set_target_role(attribute.get_name())
        association.set_navigability(False, True)
        self._diagram.add_association(association)

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
            if relation.get_label() is not None and self._diagram.get_class(child).get_parent() == parent:
                self._add_hint(position, CONSTRAINT_NOT_EXPORTED, child,
                               f"Generalization constraint '{relation.get_label()}' on {child} -> {parent} is not exported.")

    def _report_note_constraints(self) -> None:
        """Report each note that is attached to two classes."""
        for index, (middle, end_a, end_b) in enumerate(self._diagram.get_association_classes()):
            if self._diagram.has_note(middle):
                self._add_hint(self._association_class_position(index), CONSTRAINT_NOT_EXPORTED, middle,
                               f"Constraint '{self._diagram.get_note_text(middle)}' on ({end_a}, {end_b}) is not exported.")

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

    def _assign_role_names(self) -> None:
        """Give every association end a name that is unique within the class that owns it.

        A "1" -- "0..*" B gets the roles a and b, which become accessSourceFromTargetName and
        accessTargetFromSourceName in the XML. This comes last, because all associations and
        attributes must be known. With the label worksFor on A --> B, the role at B is worksFor.
        """
        used_names: Dict[str, Set[str]] = {}
        for uml_class in self._diagram.get_classes():
            names = set()
            for attribute in uml_class.get_attributes():
                names.add(attribute.get_name())
            used_names[uml_class.get_name()] = names
        for association in self._diagram.get_associations():
            self._assign_target_role(association, used_names[association.get_source()])
            self._assign_source_role(association, used_names[association.get_target()])

    def _assign_target_role(self, association: UmlAssociation, used: Set[str]) -> None:
        """Set the name under which the source reaches the target, unless an attribute has already set it."""
        if association.get_target_role() is not None:
            used.add(association.get_target_role())
            return
        if association.get_name() is not None and not association.is_source_navigable():
            wish = lower_first(association.get_name())
        else:
            wish = lower_first(association.get_target())
        association.set_target_role(self._unique_name(wish, association.get_name(), used))

    def _assign_source_role(self, association: UmlAssociation, used: Set[str]) -> None:
        """Set the name under which the target reaches the source."""
        wish = lower_first(association.get_source())
        association.set_source_role(self._unique_name(wish, association.get_name(), used))

    @staticmethod
    def _unique_name(wish: str, association_name: Optional[str], used: Set[str]) -> str:
        """Return the wished name. If it is taken, add the association name, then a number."""
        base = wish
        if base in used and association_name is not None:
            base = wish + association_name[:1].upper() + association_name[1:]
        candidate = base
        number = FIRST_NUMBER_FOR_UNIQUE_NAME
        while candidate in used:
            candidate = f"{base}{number}"
            number += 1
        used.add(candidate)
        return candidate
