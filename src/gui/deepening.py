"""Deepening placeholder and persistence for the analysis table."""
import copy
import csv
from datetime import datetime
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.basemlm.basemlm_model import BaseMlmModel
    from src.gui.app import LoadedModel
    from src.gui.tell_results import TellResultRow
    from src.object_database.database import Database
from src.gui.tell_results import tell_columns


def perform_deepening_transformation(model: "BaseMlmModel", selected_rows: Sequence["TellResultRow"]) -> "BaseMlmModel":
    """Return the model unchanged without applying transformations."""
    return model


def save_deepened_models(database: "Database", loaded_models: list["LoadedModel"],
                         originals: Sequence["LoadedModel"], rows: Sequence[tuple["TellResultRow", str]],
                         batch: bool, loaded_model_class: type["LoadedModel"],
                         progress: Callable[[int, int], None] | None = None) -> list["LoadedModel"]:
    """Save independent result models together and return their new database records."""
    staged = []
    used = {loaded.name for loaded in loaded_models}
    try:
        for index, original in enumerate(originals, 1):
            selected = [row for row, decision in rows if decision == 'Yes'
                        and (not batch or row.model_name == original.name)]
            result = perform_deepening_transformation(copy.deepcopy(original.model), selected)
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
        database.commit()
    except Exception:
        for item in staged:
            database.delete(item.get_oid())
        raise
    loaded_models.extend(staged)
    return staged


def export_tell_table(path: str, rows: Sequence[tuple["TellResultRow", str]], batch: bool) -> None:
    """Write exactly the displayed columns and decisions to CSV."""
    with open(path, 'w', encoding='utf-8-sig', newline='') as output:
        writer = csv.writer(output)
        writer.writerow(tell_columns(batch))
        for row, decision in rows:
            values = ([row.model_name] if batch else []) + [row.affected_parts, row.indicators, decision]
            writer.writerow(values)
