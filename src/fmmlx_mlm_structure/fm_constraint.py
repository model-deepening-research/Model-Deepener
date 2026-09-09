from src.fmmlx_mlm_structure.model_property import ModelProperty


class FmmlxConstraint(ModelProperty):

    def __init__(self, constraint_name: str, inst_level: int):
        """Creates a constraint and retains its complete XModeler roundtrip expression."""
        super().__init__(name=constraint_name, print_name=constraint_name)
        self.constraint_name = constraint_name
        self.inst_level = inst_level
        self.xml_attributes = None

    def attributes_for_xml(self, project_name: str, owner_name: str):
        """Returns the original constraint or a valid default for a new one."""
        if self.xml_attributes is not None:
            attributes = dict(self.xml_attributes)
            attributes["class"] = project_name + "::" + owner_name
            attributes["package"] = project_name
            return attributes
        return {
            "body": "true",
            "constName": self.constraint_name,
            "instLevel": str(self.inst_level),
            "package": project_name,
            "reason": '"This constraint fails"',
            "class": project_name + "::" + owner_name,
        }

    def __repr__(self):
        return f"[CONST-{self.inst_level}] {self.constraint_name}"
