import xml.etree.ElementTree as ElementTree
from typing import List

from src.fmmlx_mlm_structure.model_entity import ModelEntity
from src.model_deepening.attribute_precedence_graph import AttributePrecedenceGraph
from src.fmmlx_mlm_structure.fm_attr import FmmlxAttribute
from src.fmmlx_mlm_structure.fm_constraint import FmmlxConstraint
from src.fmmlx_mlm_structure.fm_operation import FmmlxOperation
from src.fmmlx_mlm_structure.fm_slot import FmmlxSlot
from src.model_deepening.slot_collective import SlotCollective
from src.model_deepening.slot_precedence_graph import SlotPrecedenceGraph


class FmmlxObject(ModelEntity):
    def __init__(self, full_name: str, object_name: str, level: str, class_of_object, is_abstract: str, model=None):
        super().__init__(name=object_name, print_name=object_name)
        self.full_name = full_name
        self.level: int = int(level)
        self.attr_list = []
        self.slot_list = []
        self.operations_list = []
        self.constraints_list = []
        self.class_of_object = class_of_object
        self.is_abstract: bool = True if is_abstract == "true" else False
        self.parent_classes = []
        self.instances = []
        self.slot_collectives: [SlotCollective] = []
        self.attribute_precedence_graph: AttributePrecedenceGraph = AttributePrecedenceGraph(self)
        self.slot_precedence_graph: SlotPrecedenceGraph = SlotPrecedenceGraph(self)
        self.model = model

    def __repr__(self):
        # class_str = f"[CLASS] {self.name}"
        # attr_str = ""
        # for attr in self.attr_list:
        #    attr_str  += ""
        print("ABSTRACT CLASS") if self.is_abstract else None
        print(f"[L{self.level}-OBJECT] {self.name} [of {self.class_of_object.name}]")
        print(f"HAS {len(self.parent_classes)} PARENTS") if self.parent_classes else None
        print(*self.attr_list, sep="\n")
        print(*self.slot_list, sep="\n")
        print(*self.operations_list, sep="\n")
        print(*self.constraints_list, sep="\n")
        return ""

    @classmethod
    def meta_class(cls):
        return cls("MetaClass", "MetaClass", "99",
                   FmmlxObject("MetaClass", "MetaClass", "100", None, "False")
                   , "False")

    @classmethod
    def get_shell_class(cls, base_class):
        return cls(base_class.full_name, base_class.name, "0", cls.meta_class(), "false")

    def get_model(self):
        return self.model

    def get_model_name(self) -> str:
        try:
            return self.full_name.split("::")[1]
        except:
            return "NO MODEL NAME"

    def get_all_slots(self) -> List[FmmlxSlot]:
        return self.slot_list

    def get_slot_by_attribute(self, mlm_attr: FmmlxAttribute) -> FmmlxSlot:
        for slot in self.slot_list:
            if slot.get_attribute() == mlm_attr:
                return slot

    def get_all_attributes(self) -> List[FmmlxAttribute]:
        return self.attr_list

    def get_attributes_at_inst_level_x(self, inst_level: int) -> List[FmmlxAttribute]:
        attr_list_at_inst_level = []
        for attr in self.attr_list:
            if attr.inst_level == inst_level:
                attr_list_at_inst_level.append(attr)
        return attr_list_at_inst_level

    def set_class_of_object(self, new_class_of_object):
        self.class_of_object = new_class_of_object
        self.level = int(new_class_of_object.level) - 1

    def add_object_instance(self):
        """This operation adds an instance to an existing class. It is required for performing the necessary change
        operations in model deepening"""
        assert self.level > 0, "new instances can only be created for objects on level > 0"

    def add_attr(self, attr: FmmlxAttribute):
        self.attr_list.append(attr)

    def add_slot(self, new_slot: FmmlxSlot):
        """support fot multiplicity (for now only for slot links): This operation checks whether a slot with the
        same name is already in the object and then adds the value to the slot"""
        slot_found: bool = False
        for slot in self.slot_list:
            if slot.name == new_slot.name:
                slot.value += "///" + new_slot.value
                slot_found = True
        if not slot_found:
            self.slot_list.append(new_slot)

    def add_operation(self, operation: FmmlxOperation):
        self.operations_list.append(operation)

    def add_constraint(self, constraint: FmmlxConstraint):
        self.constraints_list.append(constraint)

    def set_level(self, level: int):
        self.level = level

    def add_instance(self, instance):
        self.instances.append(instance)

    def get_slot_collectives(self):
        return self.slot_collectives

    def get_attribute_precedence_graph(self) -> AttributePrecedenceGraph:
        return self.attribute_precedence_graph

    def get_slot_precedence_graph(self) -> SlotPrecedenceGraph:
        return self.slot_precedence_graph

    def set_slot_precedence_graph(self, slot_precedence_graph: SlotPrecedenceGraph):
        self.slot_precedence_graph = slot_precedence_graph

    def get_slot_collective_by_attribute_and_value(self, attribute: FmmlxAttribute, value: str):
        for slot_collective in self.slot_collectives:
            if slot_collective.get_attribute() == attribute and slot_collective.get_value() == value:
                return slot_collective

    def create_slot_collectives(self, ignore_case: bool = True, print_progress: bool = False):
        assert self.level == 1, "Slot collectives can currently only be created for L0 instances of L1 classes"
        for attr in self.attr_list:
            encountered_slot_values: [str] = []
            for instance in self.instances:
                slot: FmmlxSlot = instance.get_slot_by_attribute(attr)
                slot_values: [str] = slot.get_values_as_list()
                slot_collective: SlotCollective
                for slot_value in slot_values:
                    if ignore_case:
                        slot_value = slot_value.lower()
                    if slot_value not in encountered_slot_values:
                        slot_collective = SlotCollective(slot_value, attr)
                        encountered_slot_values.append(slot_value)
                        self.slot_collectives.append(slot_collective)
                        attr.add_collective_slot(slot_collective)
                    else:
                        slot_collective = self.get_slot_collective_by_attribute_and_value(attr, slot_value)
                    slot_collective.add_slot(slot)
                    slot_collective.add_object_to_scope(instance)
        if print_progress:
            print(*self.slot_collectives, sep="\n")

    def create_property_precedence_graphs(self, print_attr_relations: bool = False, print_slots: bool = False):
        assert self.level == 1, "Attribute precedence can only be induced for L1 classes"
        assert len(self.attr_list) > 1, "Attribute precedence can only be induced when multiple attributes are present"
        assert len(self.attr_list[0].get_collective_slots()) > 0, ("Attribute precedence analysis "
                                                                   "requires collective slots")
        for outer_i in range(len(self.attr_list)):
            outer_attr: FmmlxAttribute = self.attr_list[outer_i]
            for inner_in in range(outer_i+1, len(self.attr_list)):
                inner_attr: FmmlxAttribute = self.attr_list[inner_in]
                attr_comparison_symbol: str = outer_attr.get_attribute_comparison_symbol(inner_attr)
                self.attribute_precedence_graph.add_property_relation(
                    outer_attr, inner_attr, attr_comparison_symbol)
                if print_attr_relations:
                    print(f"[Attr Relation] {outer_attr.name} to {inner_attr.name}: {attr_comparison_symbol}")
                    if print_slots:
                        print(f"{outer_attr.get_attribute_comparison_symbol(inner_attr, print_slots=True)}")
                        print("\n--------------------------------------------------------------\n")

    def promote_to_level_x(self, new_level: int):
        """This operation serves to promote a class to a higher level. Properties remain unchanged"""
        assert new_level > self.level, "promotion requires higher classification level"
        self.level = new_level

    def promote_attributes(self):
        """This operation promotes all attributes of a class, should be preceded by promotion of class.
        New instantiantion levels for attributes must be set before -- cannot be checked via assertion"""
        for attr in self.attr_list:
            attr.set_inst_level_to_proposed()

    def export(self, root):
        """
        Adds this object's classes, attributes, slots, and rules to the XML.

        A slot keeps its saved name even if its attribute could not be resolved
        during import, so the original slot does not make the export fail.
        Starting diagram coordinates are replaced by the later layout step.
        MetaClass elements become classes; other elements become instances.
        Association ends and slot links are exported by their relationship
        commands instead of being duplicated as attributes or ordinary slots.
        Empty slot expressions are omitted because XModeler cannot parse them.
        """
        projectName = root.attrib['path']
        diagrams = root.find('Diagrams')
        diagram = diagrams.find('Diagram')
        instances = diagram.find('Instances')
        ElementTree.SubElement(instances, 'Instance', hidden='false', path=projectName + "::" + self.name,
                               xCoordinate='0', yCoordinate='0')

        model = root.find('Model')

        if self.class_of_object is None or self.class_of_object.name == 'MetaClass':
            ElementTree.SubElement(model, 'addMetaClass', abstract='false', level=str(self.level),
                                   maxLevel=str(self.level), name=self.name, package=projectName,
                                   singleton='false')
        else:
            class_path = projectName + "::" + self.class_of_object.full_name.split("::")[2]
            ElementTree.SubElement(model, 'addInstance', abstract='false', level=str(self.level),
                                   maxLevel=str(self.level), name=self.name, of=class_path,
                                   package=projectName, singleton='false')

        for attr in self.attr_list:
            if attr.attr_category == "ASSOC-END":
                continue
            attribute = ElementTree.SubElement(model, 'addAttribute', level=str(attr.inst_level),
                                               multiplicity='Seq{1,1,true,false}', name=attr.name,
                                               package=projectName, type=attr.attr_type)
            # this attr has to be set separetly because of the keyword class and cannot be used in the prior operation
            attribute.set('class', projectName + "::" + self.name)

        for slot in self.slot_list:
            if slot.slot_category == "SLOT-LINK":
                continue
            if slot.value == "":
                continue
            slot_element = ElementTree.SubElement(model, 'changeSlotValue', package=projectName,
                                                  slotName=slot.name, valueToBeParsed=slot.value_for_xml())
            # this attr has to be set separetly because of the keyword class and cannot be used in the prior operation
            slot_element.set('class', projectName + "::" + self.name)

        for constraint in self.constraints_list:
            ElementTree.SubElement(
                model,
                'addConstraint',
                **constraint.attributes_for_xml(projectName, self.name),
            )

        for operation in self.operations_list:
            ElementTree.SubElement(
                model,
                'addOperation',
                **operation.attributes_for_xml(projectName, self.name),
            )

        for parent in self.parent_classes:
            parent = ElementTree.SubElement(model, 'changeParent', new=projectName + "::" + parent.name, old="",
                                            package=projectName)
            parent.set('class', projectName + "::" + self.name)

    def set_is_abstract(self, is_abstract: bool):
        self.is_abstract = is_abstract

    def add_parent_class(self, parent_class):
        self.parent_classes.append(parent_class)

    def is_specialization(self) -> bool:
        return not self.parent_classes
