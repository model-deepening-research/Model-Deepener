import re
from abc import ABCMeta, abstractmethod

from basemlm.basemlm_type_spec import TypeSpec
from basemlm.predefined_type_enum import BaseMlmPredefinedTypesEnum


class BaseMlmPredefinedType(TypeSpec, metaclass=ABCMeta):

    def __init__(self, type_name: BaseMlmPredefinedTypesEnum):
        self.instance = None
        self.type_name: BaseMlmPredefinedTypesEnum = type_name

    def get_type_name(self) -> str:
        return self.type_name.value

    def get_type_as_enum_value(self) -> BaseMlmPredefinedTypesEnum:
        return self.type_name

    @abstractmethod
    def slot_conforms_to_type(self, slot) -> bool:
        """must be overwritten in derived classes"""


class StringType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.STRING)

    def slot_conforms_to_type(self, slot) -> bool:
        return True


class IntegerType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.INTEGER)

    def slot_conforms_to_type(self, slot) -> bool:
        for value in slot.get_values_as_list():
            try:
                int(value)
            except ValueError:
                return False
        return True


class BooleanType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.BOOLEAN)

    def slot_conforms_to_type(self, slot) -> bool:
        for value in slot.get_values_as_list():
            if not (value == "true" or value == "false"):
                return False
        return True


class FloatType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.FLOAT)

    def slot_conforms_to_type(self, slot) -> bool:
        pattern = r"[-+]?[0-9]+\.[0-9]+"

        for value in slot.get_values_as_list():
            if re.fullmatch(pattern, value) is None:
                return False
        return True


class DateType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.DATE)

    def slot_conforms_to_type(self, slot) -> bool:
        pattern = r"DATE\([0-9]{2},[0-9]{2},[0-9]{4}\)"

        for value in slot.get_values_as_list():
            if re.fullmatch(pattern, value) is None:
                return False
        return True


class UnknownType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.UNSPECIFIED)

    def slot_conforms_to_type(self, slot) -> bool:
        return False

