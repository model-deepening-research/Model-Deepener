from pathlib import Path

from basemlm.model_part import ModelPart
from src.basemlm.basemlm_model import BaseMlmModel
from src.testing.precedence_analysis_tester import PrecedenceAnalysisTester

#pa_tester = PrecedenceAnalysisTester(variant=2,
#                                     print_input_model=False,
#                                     track_progress=True,
#                                     export_precedence_graphs_as_png=True,
#                                     print_precedence_graph=True)

model_name = str(Path(__file__).resolve().parents[2] / "models" / "fmmlx" / "Portaview_with_Objects.xml")


my_model: BaseMlmModel = BaseMlmModel(model_name)

for fc in my_model.get_objects():
    for slot_link in fc.get_slot_links():
        print("SLOT-LINK")
        print(slot_link)
        print(slot_link.get_links())
        print("----------------")


#print(Path.cwd().parent)
