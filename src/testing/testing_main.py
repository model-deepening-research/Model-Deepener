import os.path

from src.basemlm.basemlm_model import BaseMlmModel
from src.testing.precedence_analysis_tester import PrecedenceAnalysisTester

#pa_tester = PrecedenceAnalysisTester(variant=2,
#                                     print_input_model=False,
 #                                    track_progress=True,
  #                                   export_precedence_graphs_as_png=False,
   #                                  print_precedence_graph=True)

model_name = os.path.join(os.getcwd()[:-4], "example_models", "Portaview_with_Objects.xml")


my_model: BaseMlmModel = BaseMlmModel(model_name)

print(my_model.get_mlm_object_by_shortname("user3").get_descendants())

print(my_model.get_mlm_object_by_shortname("AbstractVideo").get_descendants())
