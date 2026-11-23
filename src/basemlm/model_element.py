from abc import ABCMeta

from basemlm.model_part import ModelPart


class ModelElement(metaclass=ABCMeta):
    """The abstract class ModelElement serves as a superclass to any element (property or entity) contained in a model.
    This generalization is required for change suggestions in model deepening"""
    def __init__(self, name: str, print_name: str):
        self.name = name
        self.print_name = print_name
        self.model_parts = []
        pass

    def add_import_note(self, description: str, serious: bool = False, field: str = "name") -> None:
        """Record an import adaptation on this element."""
        notes = getattr(self, "_import_notes", None)
        if notes is None:
            notes = []
            self._import_notes = notes
        note = (description, serious)
        if note not in notes:
            notes.append(note)
        fields = getattr(self, "_import_note_fields", None)
        if fields is None:
            fields = []
            self._import_note_fields = fields
        entry = (description, serious, field)
        if entry not in fields:
            fields.append(entry)

    def get_import_notes_for(self, field: str) -> list[tuple[str, bool]]:
        """Return import adaptations affecting one displayed field."""
        fields = getattr(self, "_import_note_fields", ())
        result = [(text, serious) for text, serious, target in fields if target == field]
        recorded = {(text, serious) for text, serious, _target in fields}
        for text, serious in self.get_import_notes():
            if (text, serious) in recorded:
                continue
            lowered = text.lower()
            target = ("multiplicity" if "multiplicity" in lowered or "uses []" in lowered else
                      "name" if "\u2192" in text else
                      "type" if "type" in lowered or "datatype" in lowered else "name")
            if target == field:
                result.append((text, serious))
        return result

    def get_import_notes(self) -> list[tuple[str, bool]]:
        """Return the import adaptations recorded on this element."""
        return list(getattr(self, "_import_notes", ()))

    def get_name(self) -> str:
        return self.name

    def set_name(self, name: str):
        self.name = name

    def get_model_element_type(self) -> str:
        return type(self).__name__.lower()

    def get_print_name(self):
        return self.print_name

    def set_print_name(self, print_name: str):
        self.print_name = print_name

    def add_model_part(self, model_part):
        self.model_parts.append(model_part)

    def get_model_parts(self):
        return self.model_parts

    def is_name_valid(self):
        return self.name != ""
