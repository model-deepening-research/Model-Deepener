from abc import ABCMeta


class ModelElement(metaclass=ABCMeta):
    """The abstract class ModelElement serves as a superclass to any element (property or entity) contained in a model.
    This generalization is required for change suggestions in model deepening"""
    def __init__(self, name: str, print_name: str):
        self.name = name
        self.print_name = print_name
        pass

    def get_name(self) -> str:
        return self.name

    def set_name(self, name: str):
        self.name = name

    def get_model_element_type(self) -> str:
        return type(self).__name__.lower()

    def get_print_name(self):
        return self.print_name

    def set_print_name(self, print_name: str):
        self.print_name = print_name
