"""Summaries and CSV export for reports from multiple imported models."""
import csv
import os
from collections.abc import Sequence
from src.importers.import_report import ImportReport


PROBLEM_DESCRIPTIONS = {
    "Data type mismatch": "Values do not match their data type",
    "DataType": "Data type replaced by String",
    "EDataType": "Data type replaced by String",
    "Unknown type": "Unknown type replaced by String",
    "Unresolved type": "Unknown type replaced by String",
    "Missing type": "Missing type replaced by String",
    "Attribute without type": "Missing type replaced by String",
    "Composition whole end": "Composition multiplicity corrected",
    "Invalid multiplicity": "Invalid multiplicity corrected",
    "Missing multiplicity": "Missing multiplicity supplied",
    "Array multiplicity": "Array multiplicity adapted",
    "Interface": "Interface imported as abstract class",
    "Operation skipped": "Operations skipped",
    "Operations skipped": "Operations skipped",
    "Unresolved reference": "Reference could not be resolved",
    "Unresolved generalization": "Generalization could not be resolved",
    "Unresolved association end": "Association end could not be resolved",
    "Unresolved association type": "Association type could not be resolved",
    "Constraint not exported": "Constraint omitted",
    "Line not understood": "Unrecognized line skipped",
    "Datatype mapped to primitive": "Data type mapped to a primitive type",
    "Association class": "Association class converted",
    "N-ary association": "Association with multiple ends converted",
    "Invalid association": "Invalid association skipped",
    "No classes": "No classes found",
    "Unnamed class": "Unnamed class given a name",
    "Unnamed classifier": "Unnamed classifier skipped",
    "Unnamed attribute": "Unnamed attribute skipped",
    "Unnamed feature": "Unnamed feature skipped",
    "Duplicate classifier name": "Duplicate classifier renamed",
    "Primitive type name conflict": "Name conflicting with primitive type changed",
    "Attribute already represented by association": "Duplicate association attribute omitted",
}


def is_operation_hint(kind: str, description: str) -> bool:
    """Identify import hints that describe skipped operations."""
    category = kind.casefold()
    text = description.strip().casefold()
    return ("operation" in category or text.startswith("operation ")
            or text.startswith("operations "))


def visible_import_report(report: ImportReport) -> ImportReport:
    """Return the import report entries displayed in the interface."""
    visible = ImportReport()
    for failure in report.get_conversion_failures():
        visible.add_conversion_failure(failure)
    for problem in report.get_structure_problems():
        visible.add_structure_problem(problem)
    for adaptation in report.get_adaptations():
        if not is_operation_hint(adaptation.get_problem_type(), adaptation.get_description()):
            visible.add_adaptation(adaptation)
    return visible


def visible_import_notes(notes: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    """Return element annotations excluding operation import hints."""
    return [(text, serious) for text, serious in notes if not is_operation_hint("", text)]


def batch_report_rows(reports: Sequence[tuple[str, ImportReport]]) -> list[tuple[int, bool, str]]:
    """Prepare the model labels shown in the expandable batch report."""
    rows = []
    for index, (name, _report) in enumerate(reports):
        base = os.path.basename(name.replace("\\", "/"))
        stem, _extension = os.path.splitext(base)
        rows.append((index, True, stem))
    return rows


def batch_problem_summary(reports: Sequence[tuple[str, ImportReport]],
                          failures: Sequence[tuple[str, str]] = ()) -> list[str]:
    """Count each hint kind once per model, irrespective of its occurrences."""
    counts = {}
    for _name, original_report in reports:
        report = visible_import_report(original_report)
        kinds = set()
        if report.has_conversion_failures():
            kinds.add(ImportReport.DATA_TYPE_PROBLEM)
        kinds.update(item.get_problem_type().get_name() for item in report.get_structure_problems())
        kinds.update(item.get_problem_type() for item in report.get_adaptations())
        descriptions = {PROBLEM_DESCRIPTIONS.get(kind, kind) for kind in kinds}
        for description in sorted(descriptions):
            counts[description] = counts.get(description, 0) + 1
    lines = [f'{kind}: {count} model' + ('s' if count != 1 else '') for kind, count in counts.items()]
    return lines


def write_batch_problem_list(path: str, reports: Sequence[tuple[str, ImportReport]],
                             failures: Sequence[tuple[str, str]] = ()) -> None:
    """Write every report item with the model name and the single-import CSV columns."""
    with open(path, 'w', newline='', encoding='utf-8-sig') as output:
        writer = csv.writer(output)
        writer.writerow(['Model Name'] + ImportReport.PROBLEM_LIST_HEADER)
        for name, report in reports:
            for failure in report.get_conversion_failures():
                writer.writerow([name, ImportReport.DATA_TYPE_PROBLEM, failure.get_object_name(), failure.get_slot_name(),
                                 failure.get_class_attribute(), failure.get_raw_value(), failure.get_expected_type()])
            for problem in report.get_structure_problems():
                writer.writerow([name, problem.get_problem_type().get_name(), problem.get_object_name(), '',
                                 problem.get_class_attribute(), problem.get_raw_value(), ''])
            for item in report.get_adaptations():
                writer.writerow([name, item.get_problem_type(), item.get_object_name(), '', '', item.get_description(), ''])
        for name, reason in failures:
            writer.writerow([name, "Could not be imported", "", "", "", reason, ""])
