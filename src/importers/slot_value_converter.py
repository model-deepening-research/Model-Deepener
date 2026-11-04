"""Converts the raw value of a slot to the type of its attribute, for every importer."""
import math
import re
from datetime import date
from typing import Any

from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_enum_type import BaseMlmEnumType
from src.basemlm.basemlm_model import BaseMlmModel
from src.basemlm.basemlm_predefined_type import BooleanType, DateType, FloatType, IntegerType, StringType
from src.basemlm.basemlm_slot import BaseMlmSlot
from src.basemlm.basemlm_type_spec import TypeSpec
from src.importers.csv_reader import FLOAT_EXPRESSION, INTEGER_EXPRESSION
from src.importers.import_report import ConversionFailure, ImportReport

# Recognizes a date expression, for example: Auxiliary::Date::createDate(2024, 12, 12)
DATE_EXPRESSION = re.compile(r"Auxiliary::Date::createDate\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
EMPTY_CHARACTER_LIST = "[].asString()"
NO_VALUE_EXPRESSION = "null"
CHARACTER_LIST_END = "asString()"
PATH_SEPARATOR = "::"
# Recognizes a list of character codes, for example: [80,97].asString()
CHARACTER_LIST_EXPRESSION = re.compile(r"\[\s*(\d+\s*(,\s*\d+\s*)*)?\]\.asString\(\)")


class SlotValueConverter:
    """Converts slot values of one model and adds values that do not fit their type to the report."""

    def __init__(self, model: BaseMlmModel, report: ImportReport) -> None:
        """Remember the model, which is needed to recognize its objects, and the report for failed values."""
        self._model = model
        self._report = report

    def convert(self, slot: BaseMlmSlot) -> None:
        """Converts the raw value of a slot to the type of its attribute.

        A value that does not fit its base type is reported and keeps a readable text. A slot
        without an attribute has no type to check, so it only gets the readable text. The XML
        expression stays unchanged in xml_value.
        """
        raw_value = slot.get_value()
        attribute = slot.get_attribute()
        readable_value = self._get_readable_text(raw_value)
        if attribute is None:
            slot.set_converted_value(readable_value)
            return
        try:
            slot.set_converted_value(self._parse_slot_value(raw_value, attribute.get_type_spec()))
        except ValueError:
            self._report_failed_conversion(slot, attribute, readable_value)
            slot.set_converted_value(readable_value)

    def _get_readable_text(self, raw_value: str) -> str:
        """Returns the text of a character list. Any other expression stays as it is."""
        try:
            return self._parse_string(raw_value)
        except ValueError:
            return raw_value

    def _report_failed_conversion(self, slot: BaseMlmSlot, attribute: BaseMlmAttribute, readable_value: str) -> None:
        """Marks the slot and adds it to the import report."""
        slot.mark_conversion_failed()
        self._report.add_conversion_failure(ConversionFailure(
            slot.get_owner_object().get_name(), slot.get_name(),
            f"{attribute.get_owner().get_name()}.{attribute.get_name()}",
            slot.get_value(), attribute.get_attr_type(), readable_value))

    def _parse_slot_value(self, slot_value: str, type_spec: TypeSpec) -> Any:
        """Returns the value of a slot expression in the Python type that fits the given type.

        The expression null means no value for every type and returns None. An empty character
        list is an empty text for a String and means no value for every other type. Expressions
        of unknown types, like a MonetaryValue, stay unchanged, and so does text that is no known
        object of an object type. A ValueError means that the expression does not fit a base type.
        """
        if slot_value == NO_VALUE_EXPRESSION:
            return None
        if isinstance(type_spec, StringType):
            return self._parse_string(slot_value)
        if slot_value == EMPTY_CHARACTER_LIST:
            return None
        if isinstance(type_spec, IntegerType):
            return self._parse_integer(slot_value)
        if isinstance(type_spec, FloatType):
            return self._parse_float(slot_value)
        if isinstance(type_spec, BooleanType):
            return self._parse_boolean(slot_value)
        if isinstance(type_spec, DateType):
            return self._parse_date(slot_value)
        if isinstance(type_spec, BaseMlmEnumType):
            return self._parse_enum_value(slot_value, type_spec)
        if self._is_object_reference(slot_value):
            return slot_value.split(PATH_SEPARATOR)[-1]
        return slot_value

    def _parse_string(self, slot_value: str) -> str:
        """Returns the text of a character list. Any other text stays exactly as it is."""
        if slot_value.endswith(CHARACTER_LIST_END):
            return self._parse_character_list(slot_value)
        return slot_value

    @staticmethod
    def _parse_integer(slot_value: str) -> int:
        """Convert a whole number, also with leading zeros or a sign."""
        if INTEGER_EXPRESSION.fullmatch(slot_value.strip()) is None:
            raise ValueError(f"'{slot_value}' is not an integer.")
        return int(slot_value)

    @staticmethod
    def _parse_float(slot_value: str) -> float:
        """Accepts whole numbers and the exponent notation. A number too large for a float does not fit."""
        if FLOAT_EXPRESSION.fullmatch(slot_value.strip()) is None:
            raise ValueError(f"'{slot_value}' is not a number.")
        value = float(slot_value)
        if math.isinf(value):
            raise ValueError(f"'{slot_value}' is too large.")
        return value

    @staticmethod
    def _parse_boolean(slot_value: str) -> bool:
        """Accepts true and false in any case."""
        if slot_value.strip().lower() == "true":
            return True
        if slot_value.strip().lower() == "false":
            return False
        raise ValueError(f"'{slot_value}' is not a boolean.")

    @staticmethod
    def _parse_date(slot_value: str) -> date:
        """Converts Auxiliary::Date::createDate(year, month, day). An impossible date does not fit."""
        date_match = DATE_EXPRESSION.fullmatch(slot_value)
        if date_match is None:
            raise ValueError(f"'{slot_value}' is not a date.")
        year, month, day = date_match.groups()
        return date(int(year), int(month), int(day))

    @staticmethod
    def _parse_character_list(slot_value: str) -> str:
        """Converts an expression like [80,97].asString() to the text it contains."""
        if CHARACTER_LIST_EXPRESSION.fullmatch(slot_value) is None:
            raise ValueError(f"'{slot_value}' is not a character list.")
        sign_list = slot_value[1:].split("]")[0].split(",")
        if sign_list[0].strip() == "":
            return ""
        text = ""
        for sign_code in sign_list:
            text += chr(int(sign_code))
        return text

    def _parse_enum_value(self, slot_value: str, enum_type: BaseMlmEnumType) -> str:
        """Returns the literal of the enum that the expression names."""
        if not self._is_enum_value(slot_value, enum_type):
            raise ValueError(f"'{slot_value}' is not a literal of the enum.")
        return slot_value.split(PATH_SEPARATOR)[-1]

    @staticmethod
    def _is_enum_value(slot_value: str, enum_type: BaseMlmEnumType) -> bool:
        """Checks for a literal of the enum, written as Value or Root::Model::Enum::Value."""
        path_parts = slot_value.split(PATH_SEPARATOR)
        if len(path_parts) > 1 and path_parts[-2] != enum_type.get_name():
            return False
        return enum_type.has_enum_value(path_parts[-1])

    def _is_object_reference(self, slot_value: str) -> bool:
        """Checks for the full name of an object in this model, like Root::Model::Object."""
        for mlm_object in self._model.get_objects():
            if mlm_object.full_name == slot_value:
                return True
        return False
