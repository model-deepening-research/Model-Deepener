from basemlm.model_element import ModelElement


class ModelPart:
    """Instances of model part serve to aggregate those model members that the deepening analysis considers fruitful
    for deepening transformation. Note that it is possible to add elements from multiple models, allowing, in the future,
    to integrate multiple models into a single multi-level model."""

    def __init__(self, *args):
        """Initializes model parts, *args can be used to add elements to model part"""
        self.elements: [ModelElement] = []
        for element in args:
            self.elements.append(element)
        pass

    def add_model_member(self, member: ModelElement):
        self.elements.append(member)

    def get_model_members(self) -> [ModelElement]:
        return self.elements

    def __repr__(self):
        return_str: str = ""
        for element in self.elements:
            return_str += f"[{element.get_model_element_type()}] {element.get_name()}; "
        return return_str[:-2]
