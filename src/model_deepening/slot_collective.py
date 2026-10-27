"""
Slot collectives are used in property-precedence analysis. Instances of slot collectives represent groupings of slots
for unique values within a specific attribute.
"""
from src.basemlm.basemlm_attribute import BaseMlmAttribute
from src.basemlm.basemlm_slot import BaseMlmSlot
from src.basemlm.basemlm_property import BaseMlmProperty


class SlotCollective(BaseMlmProperty):
    def __init__(self, value: str, attribute: BaseMlmAttribute):
        if attribute.get_attr_type() == "Boolean":
            print_value = "is " + attribute.get_name() if value == "true" \
                else "is not " + attribute.get_name()
        else:
            print_value: str = value[:10]  # as a precaution only first 10 characters for printing,
        # too long names cause unreadable graphs
        super().__init__(f"{print_value}")
        self.value: str = value
        self.attribute: BaseMlmAttribute = attribute
        self.slots: [BaseMlmSlot] = []
        self.scope_list: [] = []
        self.scope_set: set = set()

    def get_class(self):
        return self.attribute.get_owner()

    def add_object_to_scope(self, fm_object):
        self.scope_list.append(fm_object)

    def get_attribute(self) -> BaseMlmAttribute:
        return self.attribute

    def get_value(self) -> str:
        return self.value

    def add_slot(self, slot: BaseMlmSlot):
        self.slots.append(slot)

    def get_slots(self) -> [BaseMlmSlot]:
        return self.slots

    def get_scope_set(self) -> set:
        return set(self.scope_list)

    def get_owner_object(self):
        """returns an instance of FmmlxObject"""
        return self.attribute.get_owner()

    def __le__(self, other):
        """
        <= operator implemented to return slot precedence a <= b, reads as a precedes b (if b, then a)
        """
        return self.get_scope_set() <= other.get_scope_set()

    def __ge__(self, other):
        return self.get_scope_set() >= other.get_scope_set()

    def __gt__(self, other):
        return self.get_scope_set() > other.get_scope_set()

    def __lt__(self, other):
        return self.get_scope_set() < other.get_scope_set()

    def compare(self, other) -> str:
        """
        the compare method compares two SlotCollective instances and returns the respective comparison symbol
        """
        if self < other:
            return "<"
        elif self > other:
            return ">"
        elif self >= other >= self:
            return "="
        else:
            return "||"  # || in this context means disjoint, indicating incomparability

    def pretty_print_scope(self) -> str:
        pp_scope: str = ""
        for fm_object in self.scope_list:
            pp_scope += fm_object.get_name() if pp_scope == "" else ", " + fm_object.get_name()
        return pp_scope

    def __repr__(self):
        return f"[SlotCollective] {self.attribute.name}:\"{self.value}\": {{{self.pretty_print_scope()}}}"
