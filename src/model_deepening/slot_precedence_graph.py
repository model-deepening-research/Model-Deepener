from src.basemlm.model_property_enum import ModelPropertyEnum
from src.model_deepening.precedence_graph import PropertyPrecedenceGraph


class SlotPrecedenceGraph(PropertyPrecedenceGraph):
    def __init__(self, assigned_object):
        super().__init__(assigned_object)
        self.property_type: ModelPropertyEnum = ModelPropertyEnum.SLOT
