from abc import ABCMeta

from src.fmmlx_mlm_structure.model_element import ModelElement


class ModelConnection(ModelElement, metaclass=ABCMeta):
    """
    Superclass for model relationships, currently FmmlxAssociation and FmmlxLink.
    Each model relationship has exactly one source and one target object.
    """
    def __init__(self, source_object, target_object, name, print_name):
        super().__init__(name=name, print_name=print_name)
        self.source_object = source_object
        self.target_object = target_object

    def get_source_object(self):
        return self.source_object

    def get_target_object(self):
        return self.target_object

    def set_source_object(self, source_object):
        self.source_object = source_object

    def set_target_object(self, target_object):
        self.target_object = target_object
