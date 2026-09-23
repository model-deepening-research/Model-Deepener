from typing import Any, List


def get_ancestors(obj: Any) -> List[Any]:
    """Return all generalization and instance-of ancestors of an object.

    The search follows ``parent_classes`` and ``class_of_object``. It remembers
    visited objects, so it also finishes when the model contains a cycle.
    """
    ancestors = []
    visited = set()
    pending = list(getattr(obj, "parent_classes", []))
    class_of_object = getattr(obj, "class_of_object", None)
    if class_of_object is not None:
        pending.append(class_of_object)

    while pending:
        ancestor = pending.pop(0)
        marker = id(ancestor)
        if ancestor is None or marker in visited:
            continue
        visited.add(marker)
        ancestors.append(ancestor)
        pending.extend(getattr(ancestor, "parent_classes", []))
        ancestor_class = getattr(ancestor, "class_of_object", None)
        if ancestor_class is not None:
            pending.append(ancestor_class)
    return ancestors


def get_descendants(model: Any, obj: Any) -> List[Any]:
    """Return all generalization children and instances below an object."""
    descendants = []
    visited = set()
    pending = list(getattr(obj, "instances", []))
    pending.extend(
        candidate
        for candidate in getattr(model, "mlm_objects", [])
        if obj in getattr(candidate, "parent_classes", [])
    )

    while pending:
        descendant = pending.pop(0)
        marker = id(descendant)
        if descendant is None or marker in visited:
            continue
        visited.add(marker)
        descendants.append(descendant)
        pending.extend(getattr(descendant, "instances", []))
        pending.extend(
            candidate
            for candidate in getattr(model, "mlm_objects", [])
            if descendant in getattr(candidate, "parent_classes", [])
        )
    return descendants
