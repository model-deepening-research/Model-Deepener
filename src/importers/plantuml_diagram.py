"""Simple representation of a PlantUML class diagram, used between reading, rewriting and writing XML."""
import re
from typing import Dict, List, Optional, Tuple

from src.importers.import_report import ImportAdaptation

INVALID_MULTIPLICITY = "Invalid multiplicity"
ATTRIBUTE_WITHOUT_TYPE = "Attribute without type"
UNKNOWN_TYPE = "Unknown type"
MISSING_MULTIPLICITY = "Missing multiplicity"
COMPOSITION_WHOLE_END = "Composition whole end"
ASSOCIATION_CLASS = "Association class"
N_ARY_ASSOCIATION = "N-ary association"
CONSTRAINT_NOT_EXPORTED = "Constraint not exported"
SEVERAL_PARENTS = "Several parents"
NOT_UNDERSTOOD = "Line not understood"

MANY = -1

# Recognizes everything that is not a letter, digit or underscore, for example the space in: part of
NON_WORD_PATTERN = re.compile(r"\W+")


def to_identifier(text: str) -> str:
    """Turn a text like part of or hasCoach > into a valid name, here part_of and hasCoach."""
    return NON_WORD_PATTERN.sub("_", text).strip("_")


def lower_first(text: str) -> str:
    """Return the text with a small first letter, because role names start in lower case."""
    return text[:1].lower() + text[1:]


class UmlMultiplicity:
    """A multiplicity such as 1, 0..1 or 0..*. The upper bound MANY stands for many (*)."""

    def __init__(self, lower: int, upper: int) -> None:
        """Remember the two bounds. They do not change afterwards, so a multiplicity can be shared."""
        self._lower = lower
        self._upper = upper

    def get_lower(self) -> int:
        """Return the lower bound."""
        return self._lower

    def get_upper(self) -> int:
        """Return the upper bound, which is MANY for *."""
        return self._upper

    def is_at_most_one(self) -> bool:
        """Return True if the upper bound is 0 or 1."""
        return self._upper in (0, 1)

    def get_text(self) -> str:
        """Return the multiplicity as it is written in PlantUML."""
        if self._upper == MANY:
            upper_text = "*"
        else:
            upper_text = str(self._upper)
        if self._lower == self._upper:
            return upper_text
        return f"{self._lower}..{upper_text}"


EXACTLY_ONE = UmlMultiplicity(1, 1)
ZERO_TO_MANY = UmlMultiplicity(0, MANY)


class UmlAttribute:
    """An attribute of a class, for example String name."""

    def __init__(self, name: str, type_name: str, multiplicity: UmlMultiplicity) -> None:
        """Remember the name, the type as written in PlantUML, and the multiplicity."""
        self._name = name
        self._type_name = type_name
        self._multiplicity = multiplicity

    def get_name(self) -> str:
        """Return the name of the attribute."""
        return self._name

    def get_type_name(self) -> str:
        """Return the type as it is written in PlantUML, for example String."""
        return self._type_name

    def get_multiplicity(self) -> UmlMultiplicity:
        """Return how many values the attribute can hold."""
        return self._multiplicity


class UmlParameter:
    """A parameter of an operation. A single word has no type yet, because it can also be a type name."""

    def __init__(self, name: str, type_name: Optional[str]) -> None:
        """Remember the name and the type. The type is None if only one word was written."""
        self._name = name
        self._type_name = type_name

    def get_name(self) -> str:
        """Return the name of the parameter."""
        return self._name

    def get_type_name(self) -> Optional[str]:
        """Return the type, or None if the parameter is a single word."""
        return self._type_name


class UmlOperation:
    """An operation of a class. PlantUML only provides the signature."""

    def __init__(self, name: str, parameters: List[UmlParameter], return_type: Optional[str]) -> None:
        """Remember the signature of the operation."""
        self._name = name
        self._parameters = parameters
        self._return_type = return_type

    def get_name(self) -> str:
        """Return the name of the operation."""
        return self._name

    def get_parameters(self) -> List[UmlParameter]:
        """Return a copy of the parameter list, so that only the operation can change its list."""
        return list(self._parameters)

    def get_return_type(self) -> Optional[str]:
        """Return the type of the result, or None if no type was written."""
        return self._return_type


class UmlClass:
    """A class, which can be abstract, with attributes, operations and at most one parent."""

    def __init__(self, name: str) -> None:
        """Create a concrete class without attributes, operations and parent."""
        self._name = name
        self._is_abstract = False
        self._attributes: List[UmlAttribute] = []
        self._operations: List[UmlOperation] = []
        self._parent: Optional[str] = None

    def get_name(self) -> str:
        """Return the name of the class."""
        return self._name

    def is_abstract(self) -> bool:
        """Return True if the class is abstract."""
        return self._is_abstract

    def set_abstract(self, is_abstract: bool) -> None:
        """Set whether the class is abstract."""
        self._is_abstract = is_abstract

    def get_attributes(self) -> List[UmlAttribute]:
        """Return a copy of the attributes, so that a loop over them can remove an attribute safely."""
        return list(self._attributes)

    def add_attribute(self, attribute: UmlAttribute) -> None:
        """Add an attribute at the end of the class."""
        self._attributes.append(attribute)

    def remove_attribute(self, attribute: UmlAttribute) -> None:
        """Remove an attribute from the class."""
        self._attributes.remove(attribute)

    def get_operations(self) -> List[UmlOperation]:
        """Return a copy of the operations, so that only the class can change its list."""
        return list(self._operations)

    def add_operation(self, operation: UmlOperation) -> None:
        """Add an operation at the end of the class."""
        self._operations.append(operation)

    def get_parent(self) -> Optional[str]:
        """Return the name of the parent class, or None if the class has no parent."""
        return self._parent

    def set_parent(self, parent: str) -> None:
        """Set the name of the parent class."""
        self._parent = parent


class UmlEnum:
    """An enumeration with its literals."""

    def __init__(self, name: str) -> None:
        """Create an enumeration without literals."""
        self._name = name
        self._literals: List[str] = []

    def get_name(self) -> str:
        """Return the name of the enumeration."""
        return self._name

    def get_literals(self) -> List[str]:
        """Return a copy of the literals, so that only the enumeration can change its list."""
        return list(self._literals)

    def add_literal(self, literal: str) -> None:
        """Add a literal at the end of the enumeration."""
        self._literals.append(literal)


class UmlAssociation:
    """A binary association between two classes.

    The source multiplicity is written at the source class and the target multiplicity at the
    target class. The target role is the name under which the source reaches the target, and the
    source role is the name under which the target reaches the source.
    """

    def __init__(self, source: str, target: str, source_multiplicity: Optional[UmlMultiplicity],
                 target_multiplicity: Optional[UmlMultiplicity], name: Optional[str] = None) -> None:
        """Create an association that can be navigated in both directions and has no role names yet."""
        self._source = source
        self._target = target
        self._source_multiplicity = source_multiplicity
        self._target_multiplicity = target_multiplicity
        self._name = name
        self._source_role: Optional[str] = None
        self._target_role: Optional[str] = None
        self._source_navigable = True
        self._target_navigable = True

    def get_source(self) -> str:
        """Return the name of the source class."""
        return self._source

    def get_target(self) -> str:
        """Return the name of the target class."""
        return self._target

    def get_source_multiplicity(self) -> Optional[UmlMultiplicity]:
        """Return the multiplicity at the source class, or None if nothing was written."""
        return self._source_multiplicity

    def set_source_multiplicity(self, multiplicity: UmlMultiplicity) -> None:
        """Set the multiplicity at the source class."""
        self._source_multiplicity = multiplicity

    def get_target_multiplicity(self) -> Optional[UmlMultiplicity]:
        """Return the multiplicity at the target class, or None if nothing was written."""
        return self._target_multiplicity

    def set_target_multiplicity(self, multiplicity: UmlMultiplicity) -> None:
        """Set the multiplicity at the target class."""
        self._target_multiplicity = multiplicity

    def get_name(self) -> Optional[str]:
        """Return the name of the association, or None if it has none."""
        return self._name

    def get_source_role(self) -> Optional[str]:
        """Return the name under which the target reaches the source."""
        return self._source_role

    def set_source_role(self, role: str) -> None:
        """Set the name under which the target reaches the source."""
        self._source_role = role

    def get_target_role(self) -> Optional[str]:
        """Return the name under which the source reaches the target."""
        return self._target_role

    def set_target_role(self, role: str) -> None:
        """Set the name under which the source reaches the target."""
        self._target_role = role

    def is_source_navigable(self) -> bool:
        """Return True if the source can be reached from the target."""
        return self._source_navigable

    def is_target_navigable(self) -> bool:
        """Return True if the target can be reached from the source."""
        return self._target_navigable

    def set_navigability(self, source_navigable: bool, target_navigable: bool) -> None:
        """Set in which directions the association can be navigated."""
        self._source_navigable = source_navigable
        self._target_navigable = target_navigable

    def connects(self, class_a: str, class_b: str) -> bool:
        """Return True if the association links the two classes, in any direction."""
        return {self._source, self._target} == {class_a, class_b}


class RawRelation:
    """One relation line exactly as written in PlantUML."""

    def __init__(self, left: str, left_multiplicity: Optional[str], arrow: str,
                 right_multiplicity: Optional[str], right: str, label: Optional[str]) -> None:
        """Remember the parts of the line A "1" *-- "0..*" B : label."""
        self._left = left
        self._left_multiplicity = left_multiplicity
        self._arrow = arrow
        self._right_multiplicity = right_multiplicity
        self._right = right
        self._label = label

    def get_left(self) -> str:
        """Return the name on the left side of the arrow."""
        return self._left

    def get_left_multiplicity(self) -> Optional[str]:
        """Return the multiplicity text on the left side, or None if nothing was written."""
        return self._left_multiplicity

    def get_arrow(self) -> str:
        """Return the arrow, for example *-- or -->."""
        return self._arrow

    def get_right_multiplicity(self) -> Optional[str]:
        """Return the multiplicity text on the right side, or None if nothing was written."""
        return self._right_multiplicity

    def get_right(self) -> str:
        """Return the name on the right side of the arrow."""
        return self._right

    def get_label(self) -> Optional[str]:
        """Return the text after the colon, or None if there is none."""
        return self._label

    def is_generalization(self) -> bool:
        """Return True for an arrow with a triangle, such as <|-- or --|>."""
        return "|" in self._arrow


class PlantUmlDiagram:
    """The content of one diagram and the adaptations that reading and rewriting it made.

    The reader fills the classes, enums and the raw parts. The normalizer turns the raw parts
    into associations, attributes and parents.
    """

    def __init__(self, name: str) -> None:
        """Create an empty diagram. Classes and enums keep the order in which they were added."""
        self._name = name
        self._classes: Dict[str, UmlClass] = {}
        self._enums: Dict[str, UmlEnum] = {}
        self._associations: List[UmlAssociation] = []
        self._relations: List[RawRelation] = []
        self._association_classes: List[Tuple[str, str, str]] = []
        self._diamonds: List[str] = []
        self._notes: Dict[str, str] = {}
        self._adaptations: List[ImportAdaptation] = []

    def get_name(self) -> str:
        """Return the name of the model."""
        return self._name

    def get_classes(self) -> List[UmlClass]:
        """Return all classes in the order in which they were added."""
        return list(self._classes.values())

    def has_class(self, name: str) -> bool:
        """Return True if there is a class with this name."""
        return name in self._classes

    def get_class(self, name: str) -> UmlClass:
        """Return the class with this name, which must exist."""
        return self._classes[name]

    def get_or_create_class(self, name: str) -> UmlClass:
        """Return the class with this name and create it if the diagram only uses it in a relation."""
        if name not in self._classes:
            self._classes[name] = UmlClass(name)
        return self._classes[name]

    def get_enums(self) -> List[UmlEnum]:
        """Return all enumerations in the order in which they were added."""
        return list(self._enums.values())

    def has_enum(self, name: str) -> bool:
        """Return True if there is an enumeration with this name."""
        return name in self._enums

    def add_enum(self, uml_enum: UmlEnum) -> None:
        """Add an enumeration. A second one with the same name replaces the first."""
        self._enums[uml_enum.get_name()] = uml_enum

    def get_associations(self) -> List[UmlAssociation]:
        """Return a copy of the associations, so that only the diagram can change its list."""
        return list(self._associations)

    def add_association(self, association: UmlAssociation) -> None:
        """Add an association at the end of the list."""
        self._associations.append(association)

    def remove_association(self, association: UmlAssociation) -> None:
        """Remove an association from the list."""
        self._associations.remove(association)

    def get_relations(self) -> List[RawRelation]:
        """Return a copy of the relation lines in the order of the text."""
        return list(self._relations)

    def add_relation(self, relation: RawRelation) -> None:
        """Add a relation line."""
        self._relations.append(relation)

    def get_association_classes(self) -> List[Tuple[str, str, str]]:
        """Return tuples of the association class and the two classes it connects."""
        return list(self._association_classes)

    def add_association_class(self, middle: str, end_a: str, end_b: str) -> None:
        """Add an association class and the two classes it connects."""
        self._association_classes.append((middle, end_a, end_b))

    def get_diamonds(self) -> List[str]:
        """Return a copy of the names of the n-ary diamonds."""
        return list(self._diamonds)

    def add_diamond(self, name: str) -> None:
        """Add the name of an n-ary diamond."""
        self._diamonds.append(name)

    def has_note(self, alias: str) -> bool:
        """Return True if there is a note with this alias."""
        return alias in self._notes

    def get_note_text(self, alias: str) -> str:
        """Return the text of the note with this alias."""
        return self._notes[alias]

    def add_note(self, alias: str, text: str) -> None:
        """Add a note. A second one with the same alias replaces the first."""
        self._notes[alias] = text

    def get_adaptations(self) -> List[ImportAdaptation]:
        """Return a copy of the adaptations in the order in which they are shown to the user."""
        return list(self._adaptations)

    def add_adaptation(self, problem_type: str, object_name: str, description: str) -> None:
        """Add a note for the user about something that was changed or left out."""
        self._adaptations.append(ImportAdaptation(problem_type, object_name, description))
