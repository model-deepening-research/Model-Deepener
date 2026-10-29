from abc import ABCMeta, abstractmethod


class TypeSpec(metaclass=ABCMeta):
    """Abstract superclass for BaseMLM type specifications. BaseMLM distinguishes three kinds of types used for
    properties: enum types, custom objects, and predefined types."""
    @abstractmethod
    def get_type_name(self) -> str:
        ...

    @abstractmethod
    def slot_conforms_to_type(self, slot) -> bool:
        ...
