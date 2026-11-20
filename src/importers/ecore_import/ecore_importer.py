"""Import Ecore metamodels into BaseMLM."""
import os
from src.basemlm.basemlm_model import BaseMlmModel
from src.importers.class_diagram_builder import ClassDiagramBuilder
from src.importers.class_diagram_normalizer import ClassDiagramNormalizer
from src.importers.ecore_import.ecore_reader import EcoreReader
from src.importers.import_report import ImportReport
from src.importers.model_importer import ModelImporter, register_importer


class EcoreImporter(ModelImporter):
    """Import Ecore metamodels as class diagrams."""
    EXTENSIONS = ('.ecore',)
    SOURCE_FOLDER = os.path.join('models', 'ecore')
    FORMAT_NAME = 'Ecore'

    def import_into(self, model: BaseMlmModel, path: str) -> ImportReport:
        """Read, normalize and import an Ecore model."""
        diagram = EcoreReader(path).read_diagram()
        ClassDiagramNormalizer(diagram).normalize()
        return self._finish_import(model, ClassDiagramBuilder().build(model, diagram))


register_importer(EcoreImporter)
