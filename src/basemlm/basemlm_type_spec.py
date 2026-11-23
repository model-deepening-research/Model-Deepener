from abc import ABCMeta, abstractmethod
from enum import Enum


class TypeSpecEnum(Enum):
    ENUM_TYPE = "Enumeration Type"
    DOMAIN_SPECIFIC = "Domain-Specific Type"
    PREDEFINED = "Predefined Type"


class TypeSpec(metaclass=ABCMeta):
    """Abstract superclass for BaseMLM type specifications. BaseMLM distinguishes three kinds of types used for
    properties: enum types, custom objects, and predefined types."""
    @abstractmethod
    def get_type_category(self) -> TypeSpecEnum:
        ...

    @abstractmethod
    def get_type_name(self) -> str:
        ...

    @abstractmethod
    def slot_conforms_to_type(self, slot) -> bool:
        ...

