"""Build a model directly from a PlantUML class diagram."""
import os

from src.basemlm.basemlm_model import BaseMlmModel
from src.importers.import_report import ImportReport
from src.importers.class_diagram_builder import ClassDiagramBuilder
from src.importers.model_importer import ModelImporter, register_importer
from src.importers.class_diagram import ClassDiagram
from src.importers.plantuml_import.plantuml_normalizer import PlantUmlNormalizer
from src.importers.plantuml_import.plantuml_reader import PlantUmlReader


TEXT_EXTENSION = ".txt"


class PlantUmlImporter(ModelImporter):
    """Import PlantUML text into model objects."""

    EXTENSIONS = (".puml", ".plantuml", TEXT_EXTENSION)
    SOURCE_FOLDER = os.path.join("models", "plantuml")
    FORMAT_NAME = "PlantUML"

    def import_into(self, model: BaseMlmModel, path: str) -> ImportReport:
        """Import a normalized PlantUML diagram into the model."""
        return ClassDiagramBuilder().build(model, self._read_and_rewrite(path))

    @staticmethod
    def _read_and_rewrite(path: str) -> ClassDiagram:
        """Read and normalize a PlantUML diagram."""
        diagram = PlantUmlReader(path).read_diagram()
        PlantUmlNormalizer(diagram).normalize()
        return diagram

    @classmethod
    def can_read(cls, path: str) -> bool:
        """Inspect TXT contents; otherwise trust the ending already selected by the importer registry."""
        if os.path.splitext(path)[1].lower() == TEXT_EXTENSION:
            return PlantUmlReader.is_plantuml_text_file(path)
        return True

    def source_file_name(self, path: str) -> str:
        """Return the name of the kept copy, which is the name of the model."""
        return f"{PlantUmlReader.get_model_name(path)}{TEXT_EXTENSION}"

    def copy_source_file(self, source_path: str, target_path: str) -> None:
        """Write the PlantUML text, because the text of an empty file comes from an image."""
        with open(target_path, "w", encoding="utf-8", newline="") as file:
            file.write(PlantUmlReader(source_path).read_text())



register_importer(PlantUmlImporter)
