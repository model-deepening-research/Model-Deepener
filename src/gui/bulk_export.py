"""Export stored models to one folder, independently of the GUI."""
import os
import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.gui.app import LoadedModel

Progress = Callable[[int, int], None]


def models_newest_first(models: Sequence["LoadedModel"]) -> list["LoadedModel"]:
    """Sort ISO-formatted timestamps newest first, keeping unknown dates last."""
    return sorted(models, key=lambda model: model.last_worked_on or model.uploaded or '', reverse=True)


def constraint_failure(loaded: "LoadedModel") -> str | None:
    """Return why the model fails the constraint check, or None when it passes."""
    try:
        violations = loaded.model.validate_basemlm_integrity()
    except Exception as error:
        return 'Constraint check failed: ' + (str(error) or type(error).__name__)
    if violations:
        return 'Constraint violations: ' + '; '.join(str(v) for v in violations)
    return None


def check_models(models: Sequence["LoadedModel"], progress: Progress | None = None) -> tuple[list["LoadedModel"], list[tuple[str, str]]]:
    """Check every model without exporting; return the passed models and (name, reason) per failure."""
    passed = []
    failures = []
    for index, loaded in enumerate(models, 1):
        reason = constraint_failure(loaded)
        if reason is None:
            passed.append(loaded)
        else:
            failures.append((loaded.name, reason))
        if progress:
            progress(index, len(models))
    return passed, failures


def export_models(models: Sequence["LoadedModel"], directory: str, skip_check: bool = False,
                  progress: Progress | None = None) -> list[tuple[str, str | None, str | None]]:
    """Export each model and return its name, destination and error, if any."""
    results = []
    used = {name.casefold() for name in os.listdir(directory)}
    for index, loaded in enumerate(models, 1):
        target = None
        try:
            if not skip_check:
                reason = constraint_failure(loaded)
                if reason is not None:
                    raise ValueError(reason)
            stem = re.sub(r'[<>:"/\\\\|?*\x00-\x1f]', '_', loaded.name).strip(' .') or 'model'
            if stem.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
                stem = '_' + stem
            filename = stem + '.xml'
            number = 2
            while filename.casefold() in used:
                filename = f'{stem} ({number}).xml'
                number += 1
            used.add(filename.casefold())
            target = os.path.join(directory, filename)
            loaded.model.export_xml(target, project_name=loaded.model.path_name)
            results.append((loaded.name, target, None))
        except Exception as error:
            results.append((loaded.name, target, str(error) or type(error).__name__))
        if progress:
            progress(index, len(models))
    return results
