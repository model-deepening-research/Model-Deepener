"""Builds a model from a PlantUML class diagram by converting it to XML for the XmlImporter."""
import os
import tempfile

from src.basemlm.basemlm_model import BaseMlmModel
from src.importers.import_report import ImportReport
from src.importers.model_importer import ModelImporter, register_importer
from src.importers.plantuml_diagram import PlantUmlDiagram
from src.importers.plantuml_normalizer import PlantUmlNormalizer
from src.importers.plantuml_reader import PlantUmlReader
from src.importers.plantuml_xml_writer import PlantUmlXmlWriter
from src.importers.xml_importer import XmlImporter

TEXT_EXTENSION = ".txt"


class PlantUmlImporter(ModelImporter):
    """Reads a PlantUML class diagram: read the text, rewrite it by the rules, create XML, import the XML.

    The XML only exists during the import. The endings .puml and .plantuml are always PlantUML; a
    .txt file only if its content is.
    """

    EXTENSIONS = (".puml", ".plantuml", TEXT_EXTENSION)
    SOURCE_FOLDER = "plantuml_files"
    FORMAT_NAME = "PlantUML"

    def import_into(self, model: BaseMlmModel, path: str) -> ImportReport:
        """Fill the given empty model with the diagram and return the problems and adaptations found.

        The adaptations are taken last, because writing the XML can still add one.
        """
        diagram = self._read_and_rewrite(path)
        xml_text = PlantUmlXmlWriter(diagram).to_xml_string()
        report = self._import_xml_text(model, diagram.get_name(), xml_text)
        for adaptation in diagram.get_adaptations():
            report.add_adaptation(adaptation)
        return report

    @staticmethod
    def _read_and_rewrite(path: str) -> PlantUmlDiagram:
        """Read the diagram from the file and rewrite it to what the XML format knows."""
        diagram = PlantUmlReader(path).read_diagram()
        PlantUmlNormalizer(diagram).normalize()
        return diagram

    @staticmethod
    def _import_xml_text(model: BaseMlmModel, model_name: str, xml_text: str) -> ImportReport:
        """Import the XML text with the XmlImporter over a temporary file, which is deleted afterwards."""
        with tempfile.TemporaryDirectory() as folder:
            xml_path = os.path.join(folder, f"{model_name}.xml")
            with open(xml_path, "w", encoding="utf-8", newline="") as file:
                file.write(xml_text)
            return XmlImporter().import_into(model, xml_path)

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

    def convert_to_xml(self, path: str) -> str:
        """Return the XML text that the PlantUML file is converted to."""
        diagram = self._read_and_rewrite(path)
        return PlantUmlXmlWriter(diagram).to_xml_string()


register_importer(PlantUmlImporter)
