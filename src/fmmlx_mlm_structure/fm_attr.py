from src.fmmlx_mlm_structure.fm_enum_type import FmmlxEnumType
from src.fmmlx_mlm_structure.model_property import ModelProperty


class FmmlxAttribute(ModelProperty):
    def __init__(self, attr_name: str, attr_type: str, inst_level: int,
                 uses_enum: bool = False, uses_domain_specific_type: bool = False,
                 multiplicity=None):
        super().__init__(name=attr_name, print_name=attr_name)
        self.attr_type = attr_type
        self.attr_type_short = attr_type.split("::")[2]
        self.inst_level = inst_level
        self.uses_enum = False
        self.uses_domain_specific_type = False
        self.attr_category: str = "ATTR"  # used for printing to distinguish with ASSOC ENDs
        self.owner = None  # Owner of attribute is instance of FmmlxObject, not specified here to avoid circular imports
        self.slot_collectives: [] = []  # used for property precedence analysis, types may not be used (circ imports)
        self.proposed_inst_level: int = 0
        self.multiplicity = multiplicity

    def set_enum_type(self, enum_type: FmmlxEnumType):
        self.attr_type_short = enum_type.name
        self.uses_enum = True

    def get_attr_category(self) -> str:
        if str(type(self)) == "FmmlxAssociationEnd":
            return "ASSOC-END"
        else:
            return "ATTR"

    def get_attr_type(self) -> str:
        return self.attr_type_short

    def set_owner(self, owner):
        self.owner = owner

    def get_proposed_inst_level(self):
        return self.proposed_inst_level

    def set_proposed_inst_level(self, new_inst_level: int):
        self.proposed_inst_level = new_inst_level

    def set_inst_level(self, new_inst_level: int):
        self.inst_level = new_inst_level

    def set_inst_level_to_proposed(self):
        self.inst_level = self.proposed_inst_level

    def get_owner(self):
        return self.owner

    def add_collective_slot(self, slot_collective):
        self.slot_collectives.append(slot_collective)

    def get_collective_slots(self) -> []:
        return self.slot_collectives

    def get_slots_for_unique_values(self) -> []:
        unique_value_slots = []
        for sc in self.slot_collectives:
            unique_value_slots.append(sc.get_slots()[0]) # sufficient to grap first slots, all are identical in value
        return unique_value_slots

    def get_owner_slot_precedence_graph(self):
        return self.owner.get_slot_precedence_graph()

    def get_slot_collective_comparisons(self, other, print_progress: bool = False) -> [str]:
        """
        This method returns all comparison symbols between all slot collectives of each attribute,
        except "||" which denotes incomparability
        """
        cs_comparison_symbols: [str] = []
        self_collective_slots = self.get_collective_slots()
        other_collective_slots = other.get_collective_slots()
        for self_cs in self_collective_slots:
            for other_cs in other_collective_slots:
                comparison_symbol = self_cs.compare(other_cs)
                self.get_owner_slot_precedence_graph().add_property_relation(self_cs, other_cs, comparison_symbol)
                if print_progress:
                    print(f"{self_cs} to {other_cs}: {comparison_symbol}")
                if comparison_symbol != "||":
                    cs_comparison_symbols.append(self_cs.compare(other_cs))

        return cs_comparison_symbols

    def get_attribute_comparison_symbol(self, other, print_slots: bool = False,
                                        raise_error_for_contradiction: bool = False) -> str:
        """
        Epistemologically, this performs a (naive) inductive leap, the results should be interpreted with care.
        """

        cs_symbols = set(self.get_slot_collective_comparisons(other, print_progress=print_slots))

        if cs_symbols == {"="}:
            return "="

        if cs_symbols == {">"}:
            return ">"

        if cs_symbols == {"<"}:
            return "<"

        if cs_symbols == {">", "="}:
            return ">="

        if cs_symbols == {"<", "="}:
            return "<="

        if not raise_error_for_contradiction:
            return "?"

        raise ValueError(
            f"Cannot aggregate contradictory comparisons: {cs_symbols}"
        )

    def __lt__(self, other):
        return True if self.get_attribute_comparison_symbol(other) == ("<" or "<=") else False

    def __gt__(self, other):
        return True if self.get_attribute_comparison_symbol(other) == (">" or ">=") else False

    def __repr__(self):
        return f"[{self.attr_category}-{self.inst_level}] {self.name}:{self.attr_type_short}"
