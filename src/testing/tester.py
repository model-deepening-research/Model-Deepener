import os
from pathlib import Path

from src.model_deepening.model_deepening import ModelDeepening


class Tester:
    """(Indirect) instances of the tester class support testing model-deepening functionalities without using the GUI"""

    def __init__(self, input_file_sub_path: str = "", file_name: str = ""):
        self.test_name: str = "Name of Test"
        self.files_base_path: str = os.path.join(Path.cwd().parent, "models", "fmmlx")
        self.input_file_sub_path: str = input_file_sub_path
        self.input_file_folder_path: str = os.path.join(self.files_base_path, self.input_file_sub_path)
        self.file_name: str = ""
        self.complete_path: str = os.path.join(self.input_file_folder_path, self.file_name)
        self.md_instance: ModelDeepening = ModelDeepening()

    def set_file_name(self, file_name: str):
        self.file_name = file_name
        self.update_path()

    def set_input_file_sub_path(self, input_file_sub_path: str):
        self.input_file_sub_path = input_file_sub_path
        self.update_path()

    def update_path(self):
        self.input_file_folder_path = os.path.join(self.files_base_path, self.input_file_sub_path)
        self.complete_path = os.path.join(self.input_file_folder_path, self.file_name)

    def get_original_model_path(self):
        return self.complete_path

    def get_md_instance(self):
        return self.md_instance
