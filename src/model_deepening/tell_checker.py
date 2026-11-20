from basemlm.basemlm_model import BaseMlmModel
from basemlm.model_part import ModelPart


class TellChecker:
    """Tell Checker receives single model, can check for single or multiple tells and returns all affected model
    parts"""

    def __init__(self, model: BaseMlmModel):
        self.model: BaseMlmModel = model
        self.taxonomic_nouns: [str] = ("type", "kind", "category", "class", "classification", "taxonomy",
                                       "species", "description", "specification", "definition", "protocol",
                                       "scheme", "typ", "cat")

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
        """Tell TO1"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            if flat_class.get_name().lower().endswith(self.taxonomic_nouns):
                affected_parts.append(flat_class)
        return affected_parts

    def check_assoc_name(self) -> [ModelPart]:
        """Tell TO2"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            if flat_class.get_name().lower().endswith(self.taxonomic_nouns):
                affected_parts.append(flat_class)
        return affected_parts

    def check_assoc_multiplicity(self) -> [ModelPart]:
        """Tell TO3"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            if flat_class.get_name().lower().endswith(self.taxonomic_nouns):
                affected_parts.append(flat_class)
        return affected_parts

    def check_class_name(self) -> [ModelPart]:
        """Tell OC1"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            if flat_class.get_name().lower().endswith(self.taxonomic_nouns):
                affected_parts.append(flat_class)
        return affected_parts

    def check_attribute_name(self) -> [ModelPart]:
        """Tell OC2"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            if flat_class.get_name().lower().endswith(self.taxonomic_nouns):
                affected_parts.append(flat_class)
        return affected_parts

    def check_enum_types(self) -> [ModelPart]:
        """Tell OC3"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            if flat_class.get_name().lower().endswith(self.taxonomic_nouns):
                affected_parts.append(flat_class)
        return affected_parts

    def check_boolean_attributes(self) -> [ModelPart]:
        """Tell OC4"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            if flat_class.get_name().lower().endswith(self.taxonomic_nouns):
                affected_parts.append(flat_class)
        return affected_parts

    def check_duplicate_instance_properties(self) -> [ModelPart]:
        """Tell OC5"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            if flat_class.get_name().lower().endswith(self.taxonomic_nouns):
                affected_parts.append(flat_class)
        return affected_parts

    def check_generalizations(self) -> [ModelPart]:
        """Tell TH1"""
        affected_parts: [ModelPart] = []
        for flat_class in self.model.get_all_flat_classes():
            if flat_class.get_name().lower().endswith(self.taxonomic_nouns):
                affected_parts.append(flat_class)
        return affected_parts
