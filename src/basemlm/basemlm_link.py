import xml.etree.ElementTree as ElementTree

from src.basemlm.model_element import ModelElement
from src.basemlm.basemlm_connection import BaseMlmConnection
from src.basemlm.basemlm_association import BaseMlmAssociation
from src.basemlm.basemlm_object import BaseMlmObject


class BaseMlmLink(BaseMlmConnection):
    def __init__(self, name: str):
        super().__init__(source_object=None, target_object=None, name=name, print_name=f"<{name}> LINK")
        self.association: BaseMlmAssociation = None

    def export(self, root):
        """Adds a link whose object paths match the selected export project."""
        projectName = root.attrib['path']
        model = root.find('Model')
        addLink = ElementTree.SubElement(model, 'addLink',
                                         classSource=projectName + "::" + self.source_object.name,
                                         classTarget=projectName + "::" + self.target_object.name,
                                         name=self.name, package=projectName)
        return root

    def get_association(self) -> BaseMlmAssociation:
        return self.association

    def set_association(self, association: BaseMlmAssociation):
        self.association = association

    def __repr__(self):
        return f"[LINK {self.name}] From {self.source_object.name} to {self.target_object.name}"
