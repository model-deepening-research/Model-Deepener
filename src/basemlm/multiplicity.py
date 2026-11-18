class Multiplicity:
    def __init__(self, min_multiplicity: int, max_multiplicity: int, unbound: bool = False) -> None:
        self.min_multiplicity = min_multiplicity
        self.max_multiplicity = max_multiplicity
        self.unbound = unbound

    def __repr__(self):
        max_card_str = "*" if self.unbound else f"{self.max_multiplicity}"
        return f"({self.min_multiplicity}..{max_card_str})"

    def get_lower_bound(self) -> int:
        return self.min_multiplicity

    def get_upper_bound(self) -> int:
        return self.max_multiplicity

    def is_unbounded(self) -> bool:
        return self.unbound

    def to_xml(self) -> str:
        """Write XModeler bounds with hasUpperBound, using -1 and false for an unbounded end."""
        upper = self.max_multiplicity
        has_upper_bound = "true"
        if self.unbound or upper == -1:
            upper = -1
            has_upper_bound = "false"
        return f"Seq{{{self.min_multiplicity},{upper},{has_upper_bound},false}}"

    def is_exactly_one(self) -> bool:
        if self.min_multiplicity == 1 and self.max_multiplicity == 1:
            return True
        else:
            return False

    def valid_multiplicity(self) -> bool:
        if (self.min_multiplicity < 0) or ((self.max_multiplicity < self.min_multiplicity) and (not self.is_unbounded())):
            return False
        return True
