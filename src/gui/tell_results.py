"""Tell definitions and result rows for single and batch analysis."""
from dataclasses import dataclass, field
import hashlib
import pickle
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
    key: tuple = field(default=(), compare=False, repr=False)
    model_format: str = ""
    model_part: object = field(default=None, compare=False, repr=False)
    is_placeholder: bool = field(default=False, compare=False)



class TellRows(list):
    """Prepared rows and failures for the selected checks."""
    def __init__(self):
        super().__init__()
        self.failures = []


class TellDecision:
    """A decision stored without creating a Tk variable for every row."""
    def __init__(self, cache, key):
        self.cache = cache
        self.key = key
        self.value = "No"

    def get(self):
        return self.cache.decisions.get(self.key, "No") if self.cache is not None and self.key else self.value

    def set(self, value):
        if self.cache is not None and self.key:
            self.cache.decisions[self.key] = value
        else:
            self.value = value

def tell_columns(batch: bool) -> tuple[str, ...]:
    """Return the columns shown for the selected view."""
    return ("Model Name", "Format", "Affected Parts", "Tell", "Transform?")


def tell_description(selection: str) -> tuple[str, str]:
    """Return the heading and indicator for a selected tell."""
    for spec in TELL_SPECS:
        if selection == f"Check Tell {spec.identifier}":
            return spec.heading, spec.indicator
    return "Check All Tells", "All Indicators"


class TellAnalysisCache:
    """Keep analysis and decisions in memory, invalidating changed model graphs."""

    def __init__(self):
        self.models = {}
        self.decisions = {}
        self.prepared = {}

    @staticmethod
    def fingerprint(model):
        return hashlib.sha256(pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL)).digest()

    def invalidate(self, model):
        key = id(model)
        self.models.pop(key, None)
        self.prepared.clear()
        for row_key in [row_key for row_key in self.decisions if row_key[0] == key]:
            del self.decisions[row_key]

    def entry(self, model):
        key = id(model)
        fingerprint = self.fingerprint(model)
        entry = self.models.get(key)
        if entry is None or entry[0] is not model or entry[1] != fingerprint:
            self.invalidate(model)
            entry = [model, fingerprint, {}]
            self.models[key] = entry
        return entry

    @staticmethod
    def selection_key(selection, models):
        return selection, tuple((item[0], id(item[1]), item[2] if len(item) > 2 else "") for item in models)

    def get_prepared(self, selection, models):
        return self.prepared.get(self.selection_key(selection, models))



def _prepare_tell_rows(model, model_name, results, model_format=""):
    """Group completed checks into display rows without touching Tk."""
    parts = {}
    for spec, hits in results:
        for part in hits:
            elements = part.get_model_elements()
            key = tuple(id(element) for element in elements)
            if key not in parts:
                parts[key] = (part, [])
            if spec not in parts[key][1]:
                parts[key][1].append(spec)
    return [TellResultRow(", ".join(element.get_name() for element in part.get_model_elements()),
                          ", ".join(item.identifier for item in matches), model_name,
                          "\n".join(item.heading for item in matches), (id(model), part_key), model_format, part)
            for part_key, (part, matches) in parts.items()]


def _append_model_rows(rows, model_name, model, model_format, results, failures):
    prepared = _prepare_tell_rows(model, model_name, results, model_format)
    rows.extend(prepared)
    for identifier, reason in failures:
        rows.failures.append((model_name, identifier, reason))
        rows.append(TellResultRow(f"{identifier} failed: {reason}", identifier, model_name,
                                  model_format=model_format, is_placeholder=True))
    if not prepared and not failures:
        rows.append(TellResultRow("No affected parts found.", "", model_name,
                                  model_format=model_format, is_placeholder=True))

def analyze_tells(selection: str, models: Sequence[tuple[str, "BaseMlmModel"]],
                  progress: Callable[[int, int], None] | None = None,
                  cache: TellAnalysisCache | None = None) -> list[TellResultRow]:
    """Run the selected checker methods and group results by model part."""
    specs = TELL_SPECS if selection == TELL_CHOICES[0] else tuple(
        spec for spec in TELL_SPECS if selection == f"Check Tell {spec.identifier}")
    rows = TellRows()
    for index, item in enumerate(models, 1):
        model_name, model = item[:2]
        model_format = item[2] if len(item) > 2 else ""
        entry = cache.entry(model) if cache is not None else None
        checker = None
        results = []
        failures = []
        for spec in specs:
            if entry is not None and spec.identifier in entry[2]:
                hits, failure = entry[2][spec.identifier]
            else:
                try:
                    if checker is None:
                        checker = TellChecker(model)
                    hits = list(getattr(checker, spec.method)())
                    failure = None
                except Exception as error:
                    hits = []
                    failure = f"{type(error).__name__}: {error}"
                if entry is not None:
                    entry[2][spec.identifier] = (hits, failure)
            if failure is not None:
                failures.append((spec.identifier, failure))
            results.append((spec, hits))
        if entry is not None:
            entry[1] = cache.fingerprint(model)
        _append_model_rows(rows, model_name, model, model_format, results, failures)
        if progress:
            progress(index, len(models))
    if cache is not None:
        cache.prepared[cache.selection_key(selection, models)] = rows
        if selection == TELL_CHOICES[0]:
            for spec in TELL_SPECS:
                single = TellRows()
                for item in models:
                    name, model = item[:2]
                    model_format = item[2] if len(item) > 2 else ""
                    hits, failure = cache.models[id(model)][2][spec.identifier]
                    failures = [(spec.identifier, failure)] if failure is not None else []
                    _append_model_rows(single, name, model, model_format, [(spec, hits)], failures)
                cache.prepared[cache.selection_key(f"Check Tell {spec.identifier}", models)] = single
    return rows
