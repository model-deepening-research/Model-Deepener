import os.path

from src.fmmlx_mlm_structure.fm_multi_level_model import FmmlxModel
from src.testing.precedence_analysis_tester import PrecedenceAnalysisTester

#pa_tester = PrecedenceAnalysisTester(variant=2,
#                                     print_input_model=False,
 #                                    track_progress=True,
  #                                   export_precedence_graphs_as_png=False,
   #                                  print_precedence_graph=True)

model_name = os.path.join(os.getcwd()[:-4], "example_models", "Portaview_with_Objects.xml")


my_model: FmmlxModel = FmmlxModel(model_name)

print(my_model)
