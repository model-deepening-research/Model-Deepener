class Multiplicity:
    def __init__(self, min_multiplicity: int, max_multiplicity: int, is_unbounded: bool = False) -> None:
        self.min_multiplicity = min_multiplicity
        self.max_multiplicity = max_multiplicity
        self.is_unbounded = is_unbounded

    def __repr__(self):
        max_card_str = "*" if self.is_unbounded else f"{self.max_multiplicity}"
        return f"({self.min_multiplicity}..{max_card_str})"

    def is_exactly_one(self) -> bool:
        if self.min_multiplicity == 1 and self.max_multiplicity == 1:
            return True
        else:
            return False
