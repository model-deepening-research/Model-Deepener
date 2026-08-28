from src.fmmlx_mlm_structure.model_property import ModelProperty


class FmmlxConstraint(ModelProperty):

    def __init__(self, constraint_name: str, inst_level: int):
        super().__init__(name=constraint_name, print_name=constraint_name)
        self.constraint_name = constraint_name
        self.inst_level = inst_level

    def __repr__(self):
        return f"[CONST-{self.inst_level}] {self.constraint_name}"
