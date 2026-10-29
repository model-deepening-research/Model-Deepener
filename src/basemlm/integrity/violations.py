from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConstraintViolation:
    """A single failed BaseMLM integrity constraint."""

    constraint: str
    message: str
    element: Any = None

    def __str__(self) -> str:
        if self.element is None:
            return f"{self.constraint}: {self.message}"
        return f"{self.constraint}: {self.message} ({self.element})"
