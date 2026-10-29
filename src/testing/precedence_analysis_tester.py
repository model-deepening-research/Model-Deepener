from src.testing.tester import Tester
from src.basemlm.basemlm_model import BaseMlmModel


class PrecedenceAnalysisTester(Tester):
    def __init__(self, variant: int = 1, track_progress: bool = True, export_precedence_graphs_as_png: bool = False,
                 print_input_model: bool = False, export_model: bool = False, print_precedence_graph: bool = False):
        super().__init__()
        self.set_input_file_sub_path("../../mlm_files/prop-precedence\\")
        self.variant: int = variant
        self.track_progress: bool = track_progress
        self.export_precedence_graphs_as_png: bool = export_precedence_graphs_as_png
        self.print_input_model: bool = print_input_model
        self.export_model: bool = export_model
        self.print_precedence_graph: bool = print_precedence_graph
        self.init_simple_precedence_test()

    def init_simple_precedence_test(self):
        csv_columns: [str] = []
        match self.variant:
            case 1:
                self.init_test("MD_CarSimple.xml")
            case 2:
                self.init_test("CarSimple-v5.xml")
            case 3:
                self.init_test("standard-oc-small.xml")
            case 4:
                selected_columns_supermarket = ["Invoice_ID", "Branch", "City", "Customer_type", "Gender", "Product_line"]
                self.init_test("supermarket_sales.csv", csv_columns=selected_columns_supermarket)
            case 5:
                self.init_test("Car_TO_1.xml")
            case 6:
                self.init_test("Car_TO_1_with_luxury.xml")
            case _:
                raise Exception("Invalid test variant (variant number: " + str(self.variant) + ") unspecified")
        self.md_instance.perform_property_precedence_analysis(print_attribute_relations=self.track_progress,
                                                              print_slot_comparisons=self.track_progress,
                                                              export_graphs_as_png=self.export_precedence_graphs_as_png,
                                                              print_precedence_graph=self.print_precedence_graph)
        if self.export_model:
            self.export_model_xml()

    def init_test(self, model_xml_name: str, csv_columns: [str] = None):
        self.set_file_name(model_xml_name)
        self.md_instance.set_input_model(BaseMlmModel(self.get_original_model_path(), csv_columns))
        if self.print_input_model:
            print(self.get_md_instance().get_original_model())

    def export_model_xml(self):
        self.md_instance.export_multi_level_model_as_xml()
