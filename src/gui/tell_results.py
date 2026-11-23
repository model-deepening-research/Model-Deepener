"""Tell definitions and result rows for single and batch analysis."""
from dataclasses import dataclass
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from src.model_deepening.tell_checker import TellChecker

if TYPE_CHECKING:
    from src.basemlm.basemlm_model import BaseMlmModel


@dataclass(frozen=True)
class TellSpec:
    """Describe a tell and its checker method."""
    identifier: str
    name: str
    indicator: str
    method: str

    @property
    def heading(self) -> str:
        """Return the identifier and full tell name."""
        return f"{self.identifier}: {self.name}"


TELL_SPECS = (
    TellSpec("TO1", "Name of Associated Class", "Emulation of Classification Relationships", "check_assoc_class_name"),
    TellSpec("TO2", "Association Name", "Emulation of Classification Relationships", "check_assoc_name"),
    TellSpec("TO3", "Association Multiplicity", "Emulation of Classification Relationships", "check_assoc_multiplicity"),
    TellSpec("OC1", "Class Name", "Overloaded Class", "check_class_name"),
    TellSpec("OC2", "Attribute Name", "Overloaded Class", "check_attribute_name"),
    TellSpec("OC3", "Enumeration Type", "Overloaded Class", "check_enum_types"),
    TellSpec("OC4", "Boolean Attributes", "Overloaded Class", "check_boolean_attributes"),
    TellSpec("OC5", "Duplicate Instance Properties", "Overloaded Class", "check_duplicate_instance_properties"),
    TellSpec("TH1", "Generalization Relationships", "Type Hierarchy", "check_generalizations"),
)
TELL_CHOICES = ("Check All Tells",) + tuple(f"Check Tell {spec.identifier}" for spec in TELL_SPECS)


@dataclass(frozen=True)
class TellResultRow:
    """Store the model part and indicators shown in one result row."""
    affected_parts: str
    indicators: str
    model_name: str = ""
    indicator_details: str = ""


def tell_columns(batch: bool) -> tuple[str, ...]:
    """Return the columns shown for the selected view."""
    columns = ("Affected Parts", "Indicators", "Transform?")
    return ("Model Name",) + columns if batch else columns


def tell_description(selection: str) -> tuple[str, str]:
    """Return the heading and indicator for a selected tell."""
    for spec in TELL_SPECS:
        if selection == f"Check Tell {spec.identifier}":
            return spec.heading, spec.indicator
    return "Check All Tells", "All Indicators"


def analyze_tells(selection: str, models: Sequence[tuple[str, "BaseMlmModel"]],
                  progress: Callable[[int, int], None] | None = None) -> list[TellResultRow]:
    """Run the selected checker methods and group results by model part."""
    specs = TELL_SPECS if selection == TELL_CHOICES[0] else tuple(
        spec for spec in TELL_SPECS if selection == f"Check Tell {spec.identifier}")
    rows = []
    for index, (model_name, model) in enumerate(models, 1):
        checker = TellChecker(model)
        parts = {}
        for spec in specs:
            for part in getattr(checker, spec.method)():
                key = id(part)
                if key not in parts:
                    parts[key] = (part, [])
                if spec not in parts[key][1]:
                    parts[key][1].append(spec)
        for part, matches in parts.values():
            rows.append(TellResultRow(part, ", ".join(item.identifier for item in matches), model_name,
                                      "\n".join(item.heading for item in matches)))
        if progress:
            progress(index, len(models))
    return rows
