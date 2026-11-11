"""Defines the common form of all importers and finds the importer that reads a file."""
import os
import shutil
from abc import ABC, abstractmethod
from typing import List, Tuple, Type

from src.basemlm.basemlm_model import BaseMlmModel
from src.importers.import_report import ImportReport


class ModelImporter(ABC):
    """Reads one file format and builds a model from it.

    A subclass names its file endings, its format and the folder for imported source files,
    implements import_into, and registers itself with register_importer.
    """

    EXTENSIONS: Tuple[str, ...] = ()
    SOURCE_FOLDER: str = ""
    FORMAT_NAME: str = ""

    @classmethod
    def can_read(cls, path: str) -> bool:
        """Accept the path without inspecting it; importer_for checks the registered ending first."""
        return True

    def source_file_name(self, path: str) -> str:
        """Return the file name for the copy that is kept in the source folder."""
        return os.path.basename(path)

    def copy_source_file(self, source_path: str, target_path: str) -> None:
        """Write the copy that is kept in the source folder."""
        shutil.copy2(source_path, target_path)

    def import_file(self, path: str) -> Tuple[BaseMlmModel, ImportReport]:
        """Return a new model with the content of the file, and the problems found in the file."""
        model = BaseMlmModel()
        report = self.import_into(model, path)
        return model, report

    @abstractmethod
    def import_into(self, model: BaseMlmModel, path: str) -> ImportReport:
        """Fill the given empty model with the content of the file and return the problems found."""

    def select_columns(self, columns: List[str]) -> None:
        """Choose the columns to import. Formats without columns ignore the selection."""


_IMPORTERS: dict[str, Type[ModelImporter]] = {}


def register_importer(importer_class: Type[ModelImporter]) -> None:
    """Register all endings atomically, rejecting conflicts with an existing format."""
    extensions = []
    for extension in importer_class.EXTENSIONS:
        extension = extension.lower()
        if extension in _IMPORTERS or extension in extensions:
            raise ValueError(f"An importer is already registered for the file ending '{extension}'.")
        extensions.append(extension)
    for extension in extensions:
        _IMPORTERS[extension] = importer_class


def supported_extensions() -> List[str]:
    """Return all file endings that can be imported, like .csv, in alphabetical order."""
    return sorted(_IMPORTERS)


def _format_name_for_sorting(importer_class: Type[ModelImporter]) -> str:
    """Return the format name in small letters, so that upper case does not change the order."""
    return importer_class.FORMAT_NAME.lower()


def supported_importers() -> List[Type[ModelImporter]]:
    """Return every importer once, in the alphabetical order of the format names."""
    importers = []
    for importer_class in _IMPORTERS.values():
        if importer_class not in importers:
            importers.append(importer_class)
    return sorted(importers, key=_format_name_for_sorting)


def supported_formats_text(last_separator: str) -> str:
    """Return the names of all formats as a list, like "CSV, PlantUML or XML"."""
    names = []
    for importer_class in supported_importers():
        names.append(importer_class.FORMAT_NAME)
    if len(names) == 0:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + last_separator + names[-1]


def importer_for(path: str) -> ModelImporter:
    """Return a new importer for the file. A ValueError means that no importer reads this file."""
    extension = os.path.splitext(path)[1].lower()
    if extension not in _IMPORTERS or not _IMPORTERS[extension].can_read(path):
        raise ValueError(f"File '{path}' must be a {supported_formats_text(' or ')} file.")
    return _IMPORTERS[extension]()
