from src.model_deepening.attribute_precedence_graph import AttributePrecedenceGraph
from src.basemlm.basemlm_model import *
from src.model_deepening.image_file_format_enum import ImageFileFormat
from src.model_deepening.model_deepening_stage_enum import ModelDeepeningStage


class ModelDeepening:

    # init only accepts single MLM file currently, may be expanded to multiple files in the future
    def __init__(self, input_model: BaseMlmModel = None):
        self.fmmlx_model: BaseMlmModel = input_model
        self.stage: ModelDeepeningStage = ModelDeepeningStage.ORIGINAL
        self.num_of_applied_suggestions: int = 0

    def set_input_model(self, input_model: BaseMlmModel):
        assert self.fmmlx_model is None, "Input model for model deepening may not be changed mid-process"
        self.fmmlx_model: BaseMlmModel = input_model

    def get_fmmlx_model(self) -> BaseMlmModel:
        return self.fmmlx_model

    def export_fmmlx_model_as_xml(self):
        assert self.fmmlx_model is not None, "No output model is specified"
        self.fmmlx_model.export_xml()

    def get_flat_classes(self) -> [BaseMlmObject]:
        return self.fmmlx_model.get_all_flat_classes()

    def get_pure_objects(self) -> [BaseMlmObject]:
        return self.fmmlx_model.get_all_pure_objects()

    """
    The following methods specify the various model-deepening analysis methods.
    """

    """
    Instances of this class serve to coordinate/execute the precedence analysis. 
    The core idea of the precedence analysis can be described as follows:
    1. identify and construct slot collectives
    2. compare scope of slot collectives to determine precedence relation between each
    3. perform inductive leap: apply precedence relation from slots to attributes
    """

    def perform_property_precedence_analysis(self, print_slot_collectives: bool = False,
                                             print_attribute_relations: bool = False,
                                             print_slot_comparisons: bool = False,
                                             export_graphs_as_png: bool = False,
                                             print_precedence_graph: bool = False):
        """
        The core of property precedence analysis lies in the specification of slot collectives. Accessing the
        scopes of a slot collective allows comparing slot collectives. The built-in set comparisons from Python
        here already return the precedence relation between two slot collectives.

        After having created the slot collectives, the main task is to compare all slot collectives of the
        given attributes in order to induce the precedence relation between attributes.
        """
        print_any: bool = print_slot_collectives | print_attribute_relations | print_slot_comparisons
        for flat_class in self.get_flat_classes():
            if print_any:
                print("PROPERTY PRECEDENCE ANALYSIS FOR " + flat_class.name + "\n")
            flat_class.create_slot_collectives(ignore_case=True, print_progress=print_slot_collectives)
            flat_class.create_property_precedence_graphs(print_attr_relations=print_attribute_relations,
                                                         print_slots=print_slot_comparisons)
            attr_precedence_graph: AttributePrecedenceGraph = flat_class.get_attribute_precedence_graph()
            spg = flat_class.get_slot_precedence_graph()
            if export_graphs_as_png:
                attr_precedence_graph.export_graph_as_image(flat_class.name, ImageFileFormat.SVG)
                spg.export_graph_as_image(flat_class.name, ImageFileFormat.SVG)

            if print_precedence_graph:
                print(attr_precedence_graph)
                print(attr_precedence_graph.return_edges_for_print())
                print(spg)
                print(spg.return_edges_for_print())

            #  attr_precedence_graph.set_inst_levels_for_attributes()
            if attr_precedence_graph.has_deepening_potential():
                #self.output_model.perform_change_operations_for_precedence_analysis(flat_class)
                print("\n---------------------OUTPUT MODEL------------------------")
                #print(self.output_model)
            if print_any:
                print("\n-------------------------------------------------------------------\n")
        print("DONE")
        return self.fmmlx_model

    def perform_deepening_operations_for_class(self, flat_class: BaseMlmObject):
        """This method performs the required change operations on the output model, the original model remains
        unchanged. Currently tailored to property-precedence analysis only, needs to be tailored to further
        deepening analysis techniques"""
        assert flat_class.level == 1, "Change operations performed on L1 classes only"
        assert flat_class.attribute_precedence_graph is not None, ("Precedence graph not detected, "
                                                         "precedence analysis must be performed first")
        max_inst_level: int = flat_class.get_attribute_precedence_graph().get_max_level()
        flat_class.promote_to_level_x(max_inst_level + 1)
        flat_class.promote_attributes()
        print(flat_class)
        while max_inst_level >= 0:

            max_inst_level -= max_inst_level



