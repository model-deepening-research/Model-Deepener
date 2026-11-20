"""Import UML XMI models into BaseMLM."""
import os
from src.basemlm.basemlm_model import BaseMlmModel
from src.importers.class_diagram_builder import ClassDiagramBuilder
from src.importers.class_diagram_normalizer import ClassDiagramNormalizer
from src.importers.import_report import ImportReport
from src.importers.model_importer import ModelImporter, register_importer
from src.importers.xmi_import.xmi_reader import XmiReader


class XmiImporter(ModelImporter):
    """Import UML XMI class models."""
    EXTENSIONS = ('.xmi',)
    SOURCE_FOLDER = os.path.join('models', 'xmi')
    FORMAT_NAME = 'UML-XMI'

    def import_into(self, model: BaseMlmModel, path: str) -> ImportReport:
        """Read and import an XMI model when it contains classes."""
        diagram = XmiReader(path).read_diagram()
        if not diagram.get_classes():
            return self._finish_import(model, ClassDiagramBuilder._create_import_report(diagram))
        ClassDiagramNormalizer(diagram).normalize()
        return self._finish_import(model, ClassDiagramBuilder().build(model, diagram))


register_importer(XmiImporter)
