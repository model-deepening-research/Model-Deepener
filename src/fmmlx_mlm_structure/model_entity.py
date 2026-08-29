from abc import ABCMeta

from src.fmmlx_mlm_structure.model_element import ModelElement


class ModelEntity(ModelElement, metaclass=ABCMeta):
    """Model entity serves as an abstract superclass to the classes FmmlxObject and FmmlxEnumType"""

    def __init__(self, name, print_name):
        super().__init__(name=name, print_name=print_name)
