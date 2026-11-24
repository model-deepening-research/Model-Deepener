from abc import ABCMeta

from src.basemlm.model_element import ModelElement


class ModelMember(ModelElement, metaclass=ABCMeta):
    """Model member serves as an abstract superclass all members of a model: connections, objects, and enum types"""

    def __init__(self, name, print_name):
        super().__init__(name=name, print_name=print_name)
