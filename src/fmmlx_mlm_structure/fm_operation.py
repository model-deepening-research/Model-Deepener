from src.fmmlx_mlm_structure.model_property import ModelProperty


class FmmlxOperation(ModelProperty):
    def __init__(self, operation_name: str, inst_level: int, return_type: str):
        """Creates an operation and retains its complete executable XModeler definition."""
        super().__init__(name=operation_name, print_name=operation_name)
        self.operation_name = operation_name
        self.inst_level = inst_level
        self.return_type = return_type
        self.xml_attributes = None

    def attributes_for_xml(self, project_name: str, owner_name: str):
        """
        Returns valid XModeler attributes for an imported or new operation.

        Imported operations keep their exact body, parameters, monitoring
        setting, and return type. New operations receive a minimal valid body.
        """
        if self.xml_attributes is not None:
            attributes = dict(self.xml_attributes)
            attributes["class"] = project_name + "::" + owner_name
            attributes["package"] = project_name
            return attributes

        short_return_type = self.return_type.split("::")[-1]
        return {
            "body": f"@Operation {self.operation_name}[monitor=false,delToClassAllowed=false]():{short_return_type}\n  null\nend",
            "level": str(self.inst_level),
            "monitored": "false",
            "name": self.operation_name,
            "package": project_name,
            "paramNames": "",
            "paramTypes": "",
            "type": self.return_type,
            "class": project_name + "::" + owner_name,
        }

    def __repr__(self):
        return f"[OP-{self.inst_level}] {self.operation_name}():{self.return_type}"
