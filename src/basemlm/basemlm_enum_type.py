import xml.etree.ElementTree as ElementTree

from basemlm.basemlm_type_spec import TypeSpec
from src.basemlm.model_member import ModelMember


class BaseMlmEnumType(ModelMember, TypeSpec):

    def __init__(self, enum_name: str):
        super().__init__(name=enum_name, print_name=enum_name)
        self.enum_values = []

    def add_enum_value(self, enum_value: str):
        self.enum_values.append(enum_value)

    def get_type_name(self) -> str:
        return self.name

    def slot_conforms_to_type(self, slot) -> bool:
        # must account for multiple values due to associations
        slot_values: [str] = slot.get_values_as_list()
        for slot_value in slot_values:
            if slot_value not in self.enum_values:
                return False
        return True

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
