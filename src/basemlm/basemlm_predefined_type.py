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

    def slot_conforms_to_type(self, slot) -> bool:
        match self.type_name:
            case BaseMlmPredefinedTypesEnum.STRING:
                return True
            case BaseMlmPredefinedTypesEnum.INTEGER:
                pass
            case BaseMlmPredefinedTypesEnum.BOOLEAN:
                pass
            case BaseMlmPredefinedTypesEnum.FLOAT:
                pass
            case BaseMlmPredefinedTypesEnum.DATE:
                pass
        return False


class StringType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.STRING)


class IntegerType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.INTEGER)


class BooleanType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.BOOLEAN)


class FloatType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.FLOAT)


class DateType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.DATE)


class UnknownType(BaseMlmPredefinedType):
    def __init__(self):
        super().__init__(BaseMlmPredefinedTypesEnum.UNSPECIFIED)

