from src.basemlm.model_property_enum import ModelPropertyEnum
from src.model_deepening.precedence_graph import PropertyPrecedenceGraph


class AttributePrecedenceGraph(PropertyPrecedenceGraph):

    def __init__(self, assigned_object):
        super().__init__(assigned_object)
        self.property_type = ModelPropertyEnum.ATTRIBUTE
        self.max_level: int = 0

    def set_inst_levels_for_attributes(self):
        inst_level: int = 0
        for pg_list in self.get_topological_generations():
            for pg in pg_list:
                for attr in pg.get_model_properties():
                    attr.set_proposed_inst_level(inst_level)
            inst_level += 1
        self.max_level = inst_level - 1

    def has_deepening_potential(self) -> bool:
        return self.max_level > 0

    def get_max_level(self) -> int:
        return self.max_level
