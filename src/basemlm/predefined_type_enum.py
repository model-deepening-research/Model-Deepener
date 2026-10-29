from enum import Enum


class BaseMlmPredefinedTypesEnum(Enum):
    """Enum type for all predefined property types"""

    STRING = "String"
    INTEGER = "Integer"
    BOOLEAN = "Boolean"
    FLOAT = "Float"
    DATE = "Date"
    UNSPECIFIED = "Unspecified type"
