from basemlm.model_member import ModelMember


class ModelPart:
    """Instances of model part serve to aggregate those model members that the deepening analysis considers fruitful
    for deepening transformation. Note that it is possible to add elements from multiple models, allowing, in the future,
    to integrate multiple models into a single multi-level model."""

    def __init__(self):
        self.members: [ModelMember] = []
        pass

    def add_model_member(self, member: ModelMember):
        self.members.append(member)

    def get_model_members(self) -> [ModelMember]:
        return self.members

    def __repr__(self):
        return_str: str = ""
        for member in self.members:
            return_str += f"[{member.get_model_element_type()}] {member.get_print_name()}; "
        return return_str[:-2]
