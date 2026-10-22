"""Prototype persistence repository for complete :class:`FmmlxModel` objects."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Iterator

from src.fmmlx_mlm_structure.fm_multi_level_model import FmmlxModel


class PrototypeObjectDatabase:
    """A small database-like wrapper around local pickle snapshots."""

    FILE_SUFFIX = ".prototype.pkl"

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, model_id: str, model: FmmlxModel) -> Path:
        self._validate_id(model_id)
        if not isinstance(model, FmmlxModel):
            raise TypeError("model must be an FmmlxModel instance")
        target = self._path_for(model_id)
        temporary = target.with_suffix(target.suffix + ".tmp")
        with temporary.open("wb") as file:
            pickle.dump(model, file, protocol=pickle.HIGHEST_PROTOCOL)
        temporary.replace(target)
        return target

    def load(self, model_id: str) -> FmmlxModel:
        self._validate_id(model_id)
        with self._path_for(model_id).open("rb") as file:
            model = pickle.load(file)
        if not isinstance(model, FmmlxModel):
            raise TypeError("stored value is not an FmmlxModel instance")
        return model

    def delete(self, model_id: str) -> bool:
        self._validate_id(model_id)
        try:
            self._path_for(model_id).unlink()
        except FileNotFoundError:
            return False
        return True

    def list_ids(self) -> Iterator[str]:
        for path in sorted(self.directory.glob(f"*{self.FILE_SUFFIX}")):
            yield path.name[: -len(self.FILE_SUFFIX)]

    def _path_for(self, model_id: str) -> Path:
        return self.directory / f"{model_id}{self.FILE_SUFFIX}"

    @staticmethod
    def _validate_id(model_id: str) -> None:
        if not model_id or Path(model_id).name != model_id:
            raise ValueError("model_id must be a non-empty file name without directories")
