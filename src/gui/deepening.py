"""Deepening persistence and analysis table export."""
import copy
import csv
import pickle
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.basemlm.basemlm_model import BaseMlmModel
    from src.gui.app import LoadedModel
    from src.gui.tell_results import TellResultRow
    from src.object_database.database import Database
from src.gui.tell_results import tell_columns
from src.model_deepening.model_deepening import ModelDeepening


@dataclass
class DeepeningOutcome:
    model: "BaseMlmModel"
    applied: int = 0
    unavailable: int = 0


def _apply_property_precedence(engine, part):
    """OC5's prepared operation expects the affected flat class, not the ModelPart."""
    elements = part.get_model_elements()
    if not elements:
        raise NotImplementedError("No affected class was supplied.")
    return engine.perform_deepening_operations_for_class(elements[0])


# OC5 can be enabled after Pierre fixes its operation.
ALLOWED_TELLS = frozenset()

# No transformation operations are defined for the other tells yet.
TELL_OPERATIONS = {"OC5": _apply_property_precedence}


def perform_deepening_transformation(model: "BaseMlmModel", selected_rows: Sequence["TellResultRow"]) -> DeepeningOutcome:
    """Try each selected row on an isolated copy; keep only completed changes."""
    model, rows = copy.deepcopy((model, list(selected_rows)))
    applied = unavailable = 0
    for index in range(len(rows)):
        original_row = rows[index]
        if original_row.model_part is None:
            unavailable += 1
            continue
        operation_ids = [item.strip() for item in original_row.indicators.split(",")]
        changed = False
        for identifier in operation_ids:
            operation = TELL_OPERATIONS.get(identifier) if identifier in ALLOWED_TELLS else None
            if operation is None:
                continue
            candidate, candidate_rows = copy.deepcopy((model, rows))
            before = pickle.dumps(candidate, protocol=pickle.HIGHEST_PROTOCOL)
            try:
                operation(ModelDeepening(candidate), candidate_rows[index].model_part)
            except NotImplementedError:
                continue
            if pickle.dumps(candidate, protocol=pickle.HIGHEST_PROTOCOL) != before:
                model, rows = candidate, candidate_rows
                changed = True
        if changed:
            applied += 1
        else:
            unavailable += 1
    return DeepeningOutcome(model, applied, unavailable)


def save_deepened_models(database: "Database", loaded_models: list["LoadedModel"],
                         originals: Sequence["LoadedModel"], rows: Sequence[tuple["TellResultRow", str]],
                         batch: bool, loaded_model_class: type["LoadedModel"],
                         progress: Callable[[int, int], None] | None = None) -> list["LoadedModel"]:
    """Save independent result models together and return their new database records."""
    staged = []
    unavailable = 0
    selected_count = 0
    used = {loaded.name for loaded in loaded_models}
    try:
        for index, original in enumerate(originals, 1):
            selected = [row for row, decision in rows if decision == 'Yes'
                        and (not batch or row.model_name == original.name)]
            if not selected:
                if progress:
                    progress(index, len(originals))
                continue
            selected_count += len(selected)
            outcome = perform_deepening_transformation(original.model, selected)
            unavailable += outcome.unavailable
            if not outcome.applied:
                if progress:
                    progress(index, len(originals))
                continue
            result = outcome.model
            result.set_is_deepened(True)
            base = original.name + '_deepened'
            name = base
            number = 2
            while name in used:
                name = f'{base} ({number})'
                number += 1
            used.add(name)
            now = datetime.now().strftime('%Y-%m-%d %H:%M')
            loaded = loaded_model_class(name=name, model=result, source_file=original.source_file,
                                        file_type=original.file_type, source_path=original.source_path,
                                        selected_columns=list(original.selected_columns), uploaded=now,
                                        last_worked_on=now, last_action='Deepened')
            database.store(loaded)
            staged.append(loaded)
            if progress:
                progress(index, len(originals))
        if staged:
            database.commit()
    except Exception:
        for item in staged:
            database.delete(item.get_oid())
        raise
    loaded_models.extend(staged)
    return staged, unavailable, selected_count


def export_tell_table(path: str, rows: Sequence[tuple["TellResultRow", str]], batch: bool) -> None:
    """Write exactly the displayed columns and decisions to CSV."""
    with open(path, 'w', encoding='utf-8-sig', newline='') as output:
        writer = csv.writer(output, delimiter=";", lineterminator="\n")
        writer.writerow(tell_columns(batch))
        for row, decision in rows:
            values = [row.model_name, row.model_format, row.affected_parts, row.indicators, decision]
            writer.writerow(values)
