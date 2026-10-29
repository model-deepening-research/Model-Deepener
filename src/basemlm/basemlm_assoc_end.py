from basemlm.basemlm_type_spec import TypeSpec
from src.basemlm.basemlm_association import BaseMlmAssociation
from src.basemlm.basemlm_attribute import BaseMlmAttribute


class BaseMlmAssocEnd(BaseMlmAttribute):
    def __init__(self, attr_name: str, attr_type_str: str, inst_level: int, attr_type_spec: TypeSpec,
                 association: BaseMlmAssociation,
                 is_source_end: bool):
        """The type of association name is not the domain-specific type but instead the unique full object name,
        allowing to retrieve the object if required."""
        super().__init__(attr_name, attr_type_str, inst_level, attr_type_spec, False, True)
        self.attr_category = "ASSOC-END"
        self.association = association
        self.is_source_end = is_source_end

    def get_association(self) -> BaseMlmAssociation:
        return self.association

    def set_association(self, association: BaseMlmAssociation):
        self.association = association
