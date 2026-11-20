"""Name conversion shared by model importers."""
import re


def normalized_name(name: str, *, attribute: bool = False, association: bool = False) -> str:
    """Return a name with unsupported characters removed or replaced."""
    result = re.sub(r"[^\w]", "_" if association else "", name, flags=re.UNICODE)
    if not result:
        return name
    if attribute:
        result = result[:1].lower() + result[1:]
    if result[0].isdigit():
        result = "_" + result
    return result


def unique_name(name: str, used: set[str]) -> str:
    """Return a name with a numeric suffix when needed."""
    result = name
    number = 1
    while result in used:
        result = f"{name}{number}"
        number += 1
    used.add(result)
    return result


def make_inherited_names_unique(objects: list) -> None:
    """Make each object's properties unique across its inherited properties."""
    def ancestors(obj) -> list:
        found = []
        pending = list(obj.get_parents())
        seen = {id(obj)}
        while pending:
            parent = pending.pop()
            if id(parent) not in seen:
                seen.add(id(parent))
                found.append(parent)
                pending.extend(parent.get_parents())
        return found

    inherited_by: dict[int, set[int]] = {id(obj): set() for obj in objects}
    ancestor_map = {id(obj): ancestors(obj) for obj in objects}
    for descendant in objects:
        for item in [descendant, *ancestor_map[id(descendant)]]:
            inherited_by.setdefault(id(item), set()).add(id(descendant))
    processed = []
    for obj in sorted(objects, key=lambda item: len(ancestor_map[id(item)])):
        used = {attribute.get_name() for other in processed
                if inherited_by[id(obj)] & inherited_by[id(other)]
                for attribute in other.get_all_attributes()}
        for attribute in obj.get_all_attributes():
            old_name = attribute.get_name()
            name = unique_name(old_name, used)
            if name != old_name:
                attribute.add_import_note(f"{old_name} \u2192 {name}")
            attribute.set_name(name)
            if attribute.is_assoc_end():
                association = attribute.get_association()
                if attribute.is_source_end:
                    association.source_access_name = attribute.get_name()
                else:
                    association.target_access_name = attribute.get_name()
        processed.append(obj)
