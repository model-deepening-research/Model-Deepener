import xml.etree.ElementTree as ElementTree

from src.fmmlx_mlm_structure.model_element import ModelElement
from src.fmmlx_mlm_structure.model_entity import ModelEntity


class FmmlxEnumType(ModelEntity):
    def __init__(self, enum_name: str):
        super().__init__(name=enum_name, print_name=enum_name)
        self.enum_values = []

    def add_enum_value(self, enum_value: str):
        self.enum_values.append(enum_value)

    def __repr__(self):
        enum_print: str = ""
        enum_print = f"[ENUM] {self.name}: "
        for enum_value in self.enum_values:
            enum_print += f"{enum_value}, "
        return enum_print[:-2]

    def export(self, root: ElementTree.Element):
        model = root.find('Model')
        addEnum = ElementTree.SubElement(model, 'addEnumeration', name=self.name)
        for value in self.enum_values:
            addEnumValue = ElementTree.SubElement(model, 'addEnumerationValue', enum_name=self.name,
                                                  enum_value_name=str(value))
        return root
