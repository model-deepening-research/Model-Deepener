from basemlm.basemlm_association import BaseMlmAssociation
from basemlm.basemlm_attribute import BaseMlmAttribute
from basemlm.basemlm_model import BaseMlmModel
from basemlm.basemlm_type_spec import TypeSpecEnum
from basemlm.model_part import ModelPart
from basemlm.predefined_type_enum import BaseMlmPredefinedTypesEnum
from model_deepening.model_deepening import ModelDeepening


class TellChecker:
    """Tell Checker receives single model, can check for single or multiple tells and returns all affected model
    parts"""

    def __init__(self, model: BaseMlmModel):
        self.model: BaseMlmModel = model
        self.classification_nouns: [str] = ("type", "kind", "category", "class", "classification", "taxonomy",
                                            "species", "description", "specification", "definition", "protocol",
                                            "scheme", "typ") # 'cat' yields location
        self.instance_nouns: [str] = ("instance", "item", "unit", "copy", "exemplar", "individual", "piece", "case",
                                      "record", "entry")
        self.instance_to_class_assoc_names: [str] = ("is_a", "is_an", "is_of", "has_type", "has_kind", "has_category",
                                                     "has_class", "instance_of", "is_instance_of", "type_of", "kind_of",
                                                     "typed_by", "classified_by", "categorized_by", "categorised_by",
                                                     "described_by", "specified_by", "defined_by", "conforms_to",
                                                     "of_type", "of_kind", "of_category")
        self.class_to_instance_assoc_names: [str] = ("has_instance", "has_instances", "instantiated_by", "instances",
                                                     "classifies", "categorizes", "categorises", "types",
                                                     "describes", "specifies", "defines",
                                                     "classification_for", "type_for", "category_for")

    """
    List of indicators and tells:
    
    Indicator #1: Emulation of Classification Relationships (TO)
    - TO1 Name of Associated Class
    - TO2 Association Name
    - TO3 Association Multiplicity
    
    Indicator #2: Overloaded Class (OC)
    - OC1 Class Name
    - OC2 Attribute Name
    - OC3 Enumeration Type
    - OC4 Duplicate Instance Properties
    ...
    
    Indicator #3: Type Hierarchy (TH)
    - TH1 Generalization Relationships
    ..    
    
    """

    def check_assoc_class_name(self) -> [ModelPart]:
        """Tell TO1: check names of associated classes, performed by iterating through assoc ends,
        parts in following order:
        type-class, instance-class, association"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            for assoc_end in flat_class.get_assoc_ends():
                assoc: BaseMlmAssociation = assoc_end.get_association()
                # Option 1: classification noun identified
                if assoc_end.get_owner().get_name().lower().endswith(self.classification_nouns):
                    affected_parts.append(ModelPart(assoc.get_target_object(), assoc.get_source_object(), assoc))
                if assoc_end.get_owner().get_name().lower().endswith(self.instance_nouns):
                    affected_parts.append(ModelPart(assoc.get_source_object(), assoc.get_target_object(), assoc))
        return affected_parts

    def check_assoc_name(self) -> [ModelPart]:
        """Tell TO2": checks association names, model parts are always added in the following order:
        type-class, instance-class, association"""
        affected_parts: [ModelPart] = []
        for assoc in self.model.get_associations():
            # Option 1: instance-to-class name, src is instance, tgt is class
            if assoc.get_name().lower().startswith(self.instance_to_class_assoc_names):
                affected_parts.append(ModelPart(assoc.get_target_object(), assoc.get_source_object(), assoc))
            # Option 2: class-to-instance name, src is type, tgt is instance
            if assoc.get_name().lower().startswith(self.class_to_instance_assoc_names):
                affected_parts.append(ModelPart(assoc.get_source_object(), assoc.get_target_object(), assoc))
        return affected_parts

    def check_assoc_multiplicity(self) -> [ModelPart]:
        """Tell TO3: check multiplicities of associations, multiplicity checker implemented in association"""
        affected_parts: [ModelPart] = []
        for assoc in self.model.get_associations():
            if assoc.is_classification_indicator():
                affected_parts.append(ModelPart(assoc.get_source_object(), assoc.get_target_object(), assoc))
            if assoc.is_instantiation_indicator():
                affected_parts.append(ModelPart(assoc.get_target_object(), assoc.get_source_object(), assoc))
        return affected_parts

    def check_class_name(self) -> [ModelPart]:
        """Tell OC1: check whether class may be overloaded, only need to check classification nouns"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            if flat_class.get_name().lower().endswith(self.classification_nouns):
                affected_parts.append(ModelPart(flat_class))
        return affected_parts

    def check_attribute_name(self) -> [ModelPart]:
        """Tell OC2: check attribute names, using the same classification_nouns list,
        returns class + list of detected attributes"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            detected_attributes: [BaseMlmAttribute] = []
            for attr in flat_class.get_regular_attributes():
                attr_detected: bool = False
                for name_tell in self.classification_nouns:
                    if not attr_detected and name_tell in attr.get_name().lower():
                        detected_attributes.append(attr)
                        attr_detected = True
            if len(detected_attributes) > 0:
                affected_parts.append(ModelPart(flat_class, *detected_attributes))
        return affected_parts

    def check_enum_types(self) -> [ModelPart]:
        """Tell OC3: returns all uses of enum types in class, returns class + list of detected attribute"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            detected_attributes: [BaseMlmAttribute] = []
            for attr in flat_class.get_regular_attributes():
                if attr.get_type_spec_category() == TypeSpecEnum.ENUM_TYPE:
                    detected_attributes.append(attr)
            if len(detected_attributes) > 0:
                affected_parts.append(ModelPart(flat_class, *detected_attributes))
        return affected_parts

    def check_boolean_attributes(self) -> [ModelPart]:
        """Tell OC4: checks for Boolean attributes in class, returns class + list of detected attributes"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            detected_attributes: [BaseMlmAttribute] = []
            for attr in flat_class.get_regular_attributes():
                if attr.get_type_spec().get_type_name() == BaseMlmPredefinedTypesEnum.BOOLEAN.value:
                    detected_attributes.append(attr)
            if len(detected_attributes) > 0:
                affected_parts.append(ModelPart(flat_class, *detected_attributes))
        return affected_parts

    def check_duplicate_instance_properties(self) -> [ModelPart]:
        """Tell OC5: property-precedence analysis required"""
        affected_parts: [ModelPart] = []
        # if self.model.has_instances():
           # md_instance: ModelDeepening = ModelDeepening(self.model)
            # md_instance.perform_property_precedence_analysis()
            # affected_parts = md_instance.return_affected_classes_as_parts()
        return affected_parts

    def check_generalizations(self) -> [ModelPart]:
        """Tell TH1: checks for generalization relationships, part consists of child, parent"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            for parent in flat_class.get_parents():
                affected_parts.append(ModelPart(flat_class, parent))
        return affected_parts
