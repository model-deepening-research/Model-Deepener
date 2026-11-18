from datetime import date
from typing import Any

from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_property import BaseMlmProperty


class BaseMlmSlot(BaseMlmProperty):
    """
    BaseMlmSlot serves as an implementation of slots in FMMLx. Note that the attribute "owner" is of type BaseMlmObject.
    Thus, the method set_attribute() can call "class_of_object".

    You MAY NOT import BaseMlmObject, though. This causes a circular import.

    The value has the Python type that fits the attribute: str, int, float, bool, or date.
    None means that the slot has no value. A value that could not be converted stays a str
    and the slot is marked. The class attribute is the default for slots stored without a mark.
    """
    _conversion_failed: bool = False

    def __init__(self, slot_name: str, value: str, xml_value: str = None):
        """
        Stores a slot's readable value and its original XModeler expression.
        """
        super().__init__(name=slot_name, print_name=f"{slot_name}:{value}")
        self.attribute = None
        self.value = value
        self.xml_value = xml_value
        self.imported_value = value
        self.owner = None
        self.slot_category: str = "SLOT"

    def is_regular_slot(self) -> bool:
        return True if self.slot_category == "SLOT" else False

    def is_slot_link(self) -> bool:
        return False if self.slot_category == "SLOT" else True

    def conforms_to_type_spec(self) -> bool:
        if self.get_attribute().get_type_spec().slot_conforms_to_type(self):
            return True
        return False

    def conforms_to_multiplicity(self) -> bool:
        multiplicity = self.get_attribute().get_multiplicity()
        value_count = len(self.get_values_as_list())

        return (value_count >= multiplicity.get_lower_bound() and
                (multiplicity.is_unbounded() or value_count <= multiplicity.get_upper_bound()))

    def value_for_xml(self) -> str:
        """
        Returns the value in the expression format expected by XModeler.

        An unchanged imported value keeps its original expression. New or
        edited String values use the numeric ``asString()`` representation.
        """
        if self.xml_value is not None and self.value == self.imported_value:
            return self.xml_value

        attribute_type = "" if self.attribute is None else self.attribute.attr_type_str_short
        if attribute_type == "String":
            character_codes = ",".join(str(ord(character)) for character in str(self.value))
            return f"[{character_codes}].asString()"
        if isinstance(self.value, bool):
            return str(self.value).lower()
        return str(self.value)

    def is_multi_valued(self):
        return "///" in str(self.value)

    def get_values_as_list(self) -> [str]:
        """Return the values in the form used to check their type. A slot without a value has an empty list."""
        if self.value is None:
            return []
        return self._get_value_for_type_check().split("///")

    def get_value_as_text(self) -> str:
        """Return the value in the readable form shown to the user. A date is written as 2023-10-18."""
        if self.value is None:
            return "null"
        if isinstance(self.value, bool):
            return str(self.value).lower()
        if isinstance(self.value, date):
            return self.value.isoformat()
        return str(self.value)

    def _get_value_for_type_check(self) -> str:
        """Return the value in the form the type specifications check. A date is written as DATE(18,10,2023)."""
        if isinstance(self.value, date):
            return f"DATE({self.value.day:02d},{self.value.month:02d},{self.value.year:04d})"
        return self.get_value_as_text()

    def set_converted_value(self, value: Any) -> None:
        """Store the converted value. An unchanged converted value keeps its XML expression on export."""
        self.value = value
        self.imported_value = value

    def mark_conversion_failed(self) -> None:
        """Remember that the value does not fit the type of the attribute."""
        self._conversion_failed = True

    def has_conversion_failed(self) -> bool:
        """Return True if the value does not fit the type of the attribute."""
        return self._conversion_failed

    def add_value_of(self, other_slot: "BaseMlmSlot") -> None:
        """Append the value of another slot with the same name, as text separated by ///."""
        self.value = self._get_value_for_type_check() + "///" + other_slot._get_value_for_type_check()
        if other_slot.has_conversion_failed():
            self.mark_conversion_failed()

    def set_attribute(self, attribute: BaseMlmAttribute = None) -> None:
        """Connects the slot to its matching attribute when one can be found.

        The CSV import passes the attribute of the column. The XML import searches the class of
        the owner, then upwards through the parents and the classification chain, the class of
        the class and so on, because an attribute can be instantiated several levels below.
        """
        if attribute is not None:
            self.attribute = attribute
            return

        pending = [self.owner.class_of_object]
        visited = set()
        while pending and self.attribute is None:
            current = pending.pop(0)
            if current is None or id(current) in visited:
                continue
            visited.add(id(current))
            for attr in current.get_all_attributes():
                if attr.name == self.name:
                    self.attribute = attr
                    return
            pending.extend(current.get_parents())
            pending.append(current.get_meta_class())

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
