import xml.etree.ElementTree as ElementTree

from src.fmmlx_mlm_structure.model_element import ModelElement
from src.fmmlx_mlm_structure.model_connection import ModelConnection
from src.fmmlx_mlm_structure.fm_association import FmmlxAssociation
from src.fmmlx_mlm_structure.fm_object import FmmlxObject


class FmmlxLink(ModelConnection):
    def __init__(self, name: str):
        super().__init__(source_object=None, target_object=None, name=name, print_name=f"<{name}> LINK")
        self.association: FmmlxAssociation = None

    def export(self, root):
        """Adds a link whose object paths match the selected export project."""
        projectName = root.attrib['path']
        model = root.find('Model')
        addLink = ElementTree.SubElement(model, 'addLink',
                                         classSource=projectName + "::" + self.source_object.name,
                                         classTarget=projectName + "::" + self.target_object.name,
                                         name=self.name, package=projectName)
        return root

    def get_association(self) -> FmmlxAssociation:
        return self.association

    def set_association(self, association: FmmlxAssociation):
        self.association = association

    def __repr__(self):
        return f"[LINK {self.name}] From {self.source_object.name} to {self.target_object.name}"
