from enum import Enum


class ModelPropertyEnum(Enum):
    """This enum is used to categorize and identify different kinds of precedence graphs"""
    SLOT = "Slot"
    ATTRIBUTE = "Attribute"
    OPERATION = "Operation"
    ASSOCIATION = "Association"
    LINK = "Link"
    CONSTRAINT = "Constraint"
    UNDEFINED = "Undefined"
