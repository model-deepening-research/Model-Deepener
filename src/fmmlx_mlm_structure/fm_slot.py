from src.fmmlx_mlm_structure.fm_attr import FmmlxAttribute
from src.fmmlx_mlm_structure.model_property import ModelProperty


class FmmlxSlot(ModelProperty):
    """
    FmmlxSlot serves as an implementation of slots in FMMLx. Note that the attribute "owner" is of type FmmlxObject.
    Thus, the method set_attribute() can call "class_of_object".

    You MAY NOT import FmmlxObject, though. This causes a circular import.
    """
    def __init__(self, slot_name: str, value: str, xml_value: str = None):
        """
        Stores a slot's readable value and its original XModeler expression.
        """
        super().__init__(name=slot_name,print_name=f"{slot_name}:{value}")
        self.attribute = None
        self.value = value # self._import_slot_value(value) # parsing done in FmmlxModel class
        self.xml_value = xml_value
        self.imported_value = value
        self.owner = None
        self.slot_category: str = "SLOT"

    def value_for_xml(self) -> str:
        """
        Returns the value in the expression format expected by XModeler.

        An unchanged imported value keeps its original expression. New or
        edited String values use the numeric ``asString()`` representation.
        """
        if self.xml_value is not None and self.value == self.imported_value:
            return self.xml_value

        attribute_type = "" if self.attribute is None else self.attribute.attr_type_short
        if attribute_type == "String":
            character_codes = ",".join(str(ord(character)) for character in str(self.value))
            return f"[{character_codes}].asString()"
        if isinstance(self.value, bool):
            return str(self.value).lower()
        return str(self.value)

    def is_multi_valued(self):
        return "///" in str(self.value)

    def get_values_as_list(self) -> [str]:
        return str(self.value).split("///")

    def set_attribute(self, attribute: FmmlxAttribute = None):
        """Connects the slot to its matching attribute when one can be found."""
        # Beim CSV-Import kennen wir das passende Attribut schon.
        if attribute is not None:
            self.attribute = attribute
            return

        # Beim XML-Import wird das passende Attribut gesucht.
        for attr in self.owner.class_of_object.get_all_attributes():
            if attr.name == self.name:
                self.attribute = attr

    def get_attribute(self):
        return self.attribute

    def set_owner_object(self, owner):
        self.owner = owner

    def get_owner_object(self):
        return self.owner

    def get_value(self):
        return self.value

    def _import_slot_value(self, slot_value: str) -> str:
        # IMPORT STR
        if slot_value[-10:] == "asString()":
            print("STRING")
            # print(slot_value[1:-12].split(sep=","))
        else:
            if slot_value[11:].startswith("Date"):
                print("DATE")

        # MAYBE: do real type? int as int float as flot, date as date etc

        return slot_value

    def __repr__(self):
        return f"[{self.slot_category}] {self.name}: {self.value}"
