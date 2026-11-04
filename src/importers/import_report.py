"""Collects the problems found while a model is imported, independently of the user interface."""
import csv


class ConversionFailure:
    """One slot value that could not be converted to the type of its attribute."""

    def __init__(self, object_name: str, slot_name: str, class_attribute: str,
                 raw_value: str, expected_type: str, readable_value: str) -> None:
        """Remember where the value was found, the value itself and the type it should have."""
        self._readable_value = readable_value
        self._object_name = object_name
        self._slot_name = slot_name
        self._class_attribute = class_attribute
        self._raw_value = raw_value
        self._expected_type = expected_type

    def get_object_name(self) -> str:
        """Return the name of the object that owns the slot."""
        return self._object_name

    def get_slot_name(self) -> str:
        """Return the name of the slot."""
        return self._slot_name

    def get_class_attribute(self) -> str:
        """Return the attribute in the form Class.Attribute."""
        return self._class_attribute

    def get_raw_value(self) -> str:
        """Return the value exactly as it is written in the file."""
        return self._raw_value

    def get_readable_value(self) -> str:
        """Return the value as text that a person can read."""
        return self._readable_value

    def get_expected_type(self) -> str:
        """Return the type that the attribute asks for."""
        return self._expected_type


class StructureProblemType:
    """One kind of element in a file that could not be resolved, with what happens to it during the import."""

    def __init__(self, singular: str, plural: str, consequence: str) -> None:
        """Remember the two word forms for the summary and what the import does with such an element."""
        self._singular = singular
        self._plural = plural
        self._consequence = consequence

    def get_name(self) -> str:
        """Return the name of this kind with a capital first letter, for the problem list."""
        return self._singular[0].upper() + self._singular[1:]

    def get_summary_line(self, count: int) -> str:
        """Return a line like "2 instances without class (skipped)"."""
        if count == 1:
            name = self._singular
        else:
            name = self._plural
        return f"{count} {name} ({self._consequence})"


INSTANCE_WITHOUT_CLASS = StructureProblemType("instance without class", "instances without class", "skipped")
LINK_WITHOUT_ASSOCIATION = StructureProblemType("link without association", "links without association", "skipped")
LINK_WITHOUT_OBJECT = StructureProblemType("link without object", "links without object", "skipped")
ASSOCIATION_WITHOUT_CLASS = StructureProblemType("association without class", "associations without class", "skipped")
UNKNOWN_PARENT = StructureProblemType("unknown parent", "unknown parents", "generalization missing")
UNKNOWN_SUBCLASS = StructureProblemType("unknown subclass", "unknown subclasses", "generalization missing")
UNKNOWN_ATTRIBUTE_TYPE = StructureProblemType("attribute with unknown type", "attributes with unknown type",
                                              "loaded with unknown type")
ATTRIBUTE_TYPE_WITHOUT_PATH = StructureProblemType("attribute type without ::", "attribute types without ::",
                                                   "loaded with unknown type")


class StructureProblem:
    """One element of a file that could not be resolved. The raw value is the reference that has no target."""

    def __init__(self, problem_type: StructureProblemType, object_name: str, class_attribute: str,
                 raw_value: str) -> None:
        """Remember the kind of problem, the element it belongs to and the reference without a target."""
        self._problem_type = problem_type
        self._object_name = object_name
        self._class_attribute = class_attribute
        self._raw_value = raw_value

    def get_problem_type(self) -> StructureProblemType:
        """Return the kind of problem."""
        return self._problem_type

    def get_object_name(self) -> str:
        """Return the name of the element."""
        return self._object_name

    def get_class_attribute(self) -> str:
        """Return the attribute in the form Class.Attribute, or an empty text if there is none."""
        return self._class_attribute

    def get_raw_value(self) -> str:
        """Return the reference that has no target."""
        return self._raw_value


class ImportAdaptation:
    """One change the import made because the source format has no direct counterpart for an element."""

    def __init__(self, problem_type: str, object_name: str, description: str) -> None:
        """Remember the kind of change, the element it belongs to and a text for the user."""
        self._problem_type = problem_type
        self._object_name = object_name
        self._description = description

    def get_problem_type(self) -> str:
        """Return the kind of change."""
        return self._problem_type

    def get_object_name(self) -> str:
        """Return the name of the element, or an empty text if the change is not about one element."""
        return self._object_name

    def get_description(self) -> str:
        """Return the text for the user."""
        return self._description


class ImportReport:
    """Keeps the failed slot conversions, the structure problems and the adaptations of one import.

    The report only prepares its texts and writes its list. Showing them is the job of the user interface.
    """

    DATA_TYPE_PROBLEM = "Data type mismatch"
    PROBLEM_LIST_HEADER = ["Problem type", "Object", "Slot", "Class.Attribute", "Raw value", "Expected type"]

    MAX_GROUPS = 10
    MAX_EXAMPLES = 3
    MAX_EXAMPLE_LENGTH = 40

    def __init__(self) -> None:
        """Create an empty report."""
        self._conversion_failures: list[ConversionFailure] = []
        self._structure_problems: list[StructureProblem] = []
        self._adaptations: list[ImportAdaptation] = []

    def add_conversion_failure(self, failure: ConversionFailure) -> None:
        """Add a value that does not fit its type."""
        self._conversion_failures.append(failure)

    def add_structure_problem(self, problem: StructureProblem) -> None:
        """Add an element that could not be resolved."""
        self._structure_problems.append(problem)

    def add_adaptation(self, adaptation: ImportAdaptation) -> None:
        """Add a change that the import made."""
        self._adaptations.append(adaptation)

    def has_problems(self) -> bool:
        """Return True if the report holds anything at all."""
        return self.has_conversion_failures() or self.has_structure_problems() or self.has_adaptations()

    def has_adaptations(self) -> bool:
        """Return True if the import changed something."""
        return len(self._adaptations) > 0

    def get_adaptations(self) -> list[ImportAdaptation]:
        """Return a copy of the adaptations, so that only the report can change its list."""
        return list(self._adaptations)

    def has_structure_problems(self) -> bool:
        """Return True if an element could not be resolved."""
        return len(self._structure_problems) > 0

    def has_conversion_failures(self) -> bool:
        """Return True if a value does not fit its type."""
        return len(self._conversion_failures) > 0

    def get_conversion_failures(self) -> list[ConversionFailure]:
        """Return a copy of the failed conversions, so that only the report can change its list."""
        return list(self._conversion_failures)

    def get_structure_problems(self) -> list[StructureProblem]:
        """Return a copy of the structure problems, so that only the report can change its list."""
        return list(self._structure_problems)

    def get_structure_summary_lines(self) -> list[str]:
        """Return one line per kind of structure problem, in the order the kinds were found."""
        counts: dict[StructureProblemType, int] = {}
        for problem in self._structure_problems:
            problem_type = problem.get_problem_type()
            counts[problem_type] = counts.get(problem_type, 0) + 1
        lines = []
        for problem_type, count in counts.items():
            lines.append(problem_type.get_summary_line(count))
        return lines

    def get_conversion_summary_lines(self) -> list[str]:
        """Return one line per Class.Attribute and expected type, the largest groups first.

        At most MAX_GROUPS groups are listed. The remaining groups share one last line.
        """
        groups = self._group_conversion_failures()
        sorted_keys = self._keys_with_largest_group_first(groups)
        lines = []
        for key in sorted_keys[:self.MAX_GROUPS]:
            lines.append(self._group_line(key[0], key[1], groups[key]))
        remaining_keys = sorted_keys[self.MAX_GROUPS:]
        if remaining_keys:
            lines.append(self._remaining_groups_line(remaining_keys, groups))
        return lines

    def write_problem_list(self, file_path: str) -> None:
        """Write every problem to a CSV file that spreadsheet programs can open.

        The raw value of an adaptation is its description.
        """
        with open(file_path, "w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(self.PROBLEM_LIST_HEADER)
            for failure in self._conversion_failures:
                writer.writerow([self.DATA_TYPE_PROBLEM, failure.get_object_name(), failure.get_slot_name(),
                                 failure.get_class_attribute(), failure.get_raw_value(),
                                 failure.get_expected_type()])
            for problem in self._structure_problems:
                writer.writerow([problem.get_problem_type().get_name(), problem.get_object_name(), "",
                                 problem.get_class_attribute(), problem.get_raw_value(), ""])
            for adaptation in self._adaptations:
                writer.writerow([adaptation.get_problem_type(), adaptation.get_object_name(), "", "",
                                 adaptation.get_description(), ""])

    def _group_conversion_failures(self) -> dict[tuple[str, str], list[str]]:
        """Return the readable values of the failed conversions per Class.Attribute and expected type."""
        groups: dict[tuple[str, str], list[str]] = {}
        for failure in self._conversion_failures:
            key = (failure.get_class_attribute(), failure.get_expected_type())
            if key not in groups:
                groups[key] = []
            groups[key].append(failure.get_readable_value())
        return groups

    @staticmethod
    def _keys_with_largest_group_first(groups: dict[tuple[str, str], list[str]]) -> list[tuple[str, str]]:
        """Return the group keys sorted by size, and by name within the same size.

        Sorting pairs of the negative size and the key puts the largest group first.
        """
        size_and_key_pairs = []
        for key, values in groups.items():
            size_and_key_pairs.append((-len(values), key))
        size_and_key_pairs.sort()
        sorted_keys = []
        for _negative_size, key in size_and_key_pairs:
            sorted_keys.append(key)
        return sorted_keys

    def _remaining_groups_line(self, remaining_keys: list[tuple[str, str]],
                               groups: dict[tuple[str, str], list[str]]) -> str:
        """Build the last line, which counts the groups that are not listed."""
        remaining_values = 0
        for key in remaining_keys:
            remaining_values += len(groups[key])
        if len(remaining_keys) == 1:
            group_word = "group"
        else:
            group_word = "groups"
        return f"... and {len(remaining_keys)} more {group_word} ({self._count_text(remaining_values)} in total)"

    def _group_line(self, class_attribute: str, expected_type: str, values: list[str]) -> str:
        """Build the line of one group with its count and its first different values."""
        examples = []
        for value in values:
            example = self._shorten(value)
            if example not in examples and len(examples) < self.MAX_EXAMPLES:
                examples.append(example)
        example_text = ", ".join(examples)
        return (f"{class_attribute} (expected: {expected_type}): "
                f"{self._count_text(len(values))}, e.g. {example_text}")

    def _shorten(self, value: str) -> str:
        """Return a value in one short line, so a long value cannot fill the list."""
        one_line = " ".join(value.split())
        if len(one_line) > self.MAX_EXAMPLE_LENGTH:
            one_line = one_line[:self.MAX_EXAMPLE_LENGTH] + "..."
        return f"'{one_line}'"

    @staticmethod
    def _count_text(count: int) -> str:
        """Return a text like 1 value or 3 values."""
        if count == 1:
            return "1 value"
        return f"{count} values"
