from src.basemlm.basemlm_property import BaseMlmProperty


class PropertyGroup:
    """Property groups are a collection of properties. Property groups are required for property-precedence analysis,
    where groups are created every time two properties are concormitant to each other"""
    def __init__(self, *model_properties: BaseMlmProperty):
        self.model_properties: [BaseMlmProperty] = []
        for arg in model_properties:
            self.model_properties.append(arg)

    def get_print_name(self) -> str:
        assert len(self.model_properties) > 0, "Property group is empty"
        print_name = ""
        for model_property in self.model_properties:
            print_name += model_property.get_print_name() + ", "
        print_name = print_name[:-2]  # remove last comma and white space
        return print_name

    def get_property_type(self):
        assert len(self.model_properties) > 0, "Property group is empty"
        return type(self.model_properties[0])

    def merge_other_property_groups(self, *other_pgs):
        for other_pg in other_pgs:
            for model_property in other_pg.get_model_properties():
                self.add_model_property(model_property)

    def get_model_properties(self) -> [BaseMlmProperty]:
        return self.model_properties

    def add_model_property(self, model_property: BaseMlmProperty):
        self.model_properties.append(model_property)

    def includes_model_property(self, model_property: BaseMlmProperty):
        return model_property in self.model_properties

    def __eq__(self, other):
        """The equality operator = is overwritten for property groups because property groups are created every time
        a property is added to a property precedence graph."""
        if len(self.model_properties) != len(other.model_properties):
            return False
        else:
            for p1, p2 in zip(self.model_properties, other.model_properties):
                if p1 != p2:
                    return False
        return True

    def __hash__(self):
        """Note that hash must be overwritten due to changed equality function"""
        return hash(tuple(self.model_properties))

    def __len__(self):
        return len(self.model_properties)

    def __lt__(self, other):
        return self.model_properties[0] < other.model_properties[0]

    def __gt__(self, other):
        return self.model_properties[0] < other.model_properties[0]

    def __le__(self, other):
        return self.model_properties[0] <= other.model_properties[0]

    def __ge__(self, other):
        return self.model_properties[0] >= other.model_properties[0]

    def __contains__(self, other):
        """Contains operator 'in' overwritten to allow to check whether a list of model properties is contained.
        If the console points to this line in an exception, it is like that properties groups have been added to a
        property group instead of using the merge_other_property_groups function
        """
        return set(other).issubset(set(self.model_properties))

    def __repr__(self):
        return_str: str = f"("
        for m_property in self.model_properties:
            return_str += "" + m_property.__repr__() + ", "
        return_str = return_str[:-2]
        return_str += ")"
        return return_str

