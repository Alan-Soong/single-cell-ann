from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

import h5py
import numpy as np


METADATA_FIELDS = ("cell_type", "disease", "AgeGroup", "tissue")


@dataclass
class DatasetSnapshot:
    dataset_id: str = "liver"
    name: str = "Human pediatric liver"
    status: str = "not_loaded"
    data_path: str | None = None
    embedding_method: str = "obsm/X_pca"
    visualization_method: str = "obsm/X_umap"
    vectors: np.ndarray | None = None
    umap: np.ndarray | None = None
    cell_ids: list[str] = field(default_factory=list)
    metadata: dict[str, list[str]] = field(default_factory=dict)
    cell_id_to_index: dict[str, int] = field(default_factory=dict)
    error: str | None = None

    @property
    def loaded(self) -> bool:
        return self.status == "loaded" and self.vectors is not None

    @property
    def cell_count(self) -> int:
        return len(self.cell_ids)

    @property
    def vector_dim(self) -> int:
        if self.vectors is None:
            return 0
        return int(self.vectors.shape[1])

    def summary(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "status": self.status,
            "data_path": self.data_path,
            "loaded": self.loaded,
            "cell_count": self.cell_count,
            "vector_dim": self.vector_dim,
            "embedding_method": self.embedding_method,
            "visualization_method": self.visualization_method,
            "metadata_fields": list(self.metadata.keys()),
            "sample_cell_ids": self.cell_ids[:5],
            "error": self.error,
        }


class DataService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._snapshot = DatasetSnapshot()

    @property
    def snapshot(self) -> DatasetSnapshot:
        return self._snapshot

    def load_h5ad(self, path: Path) -> dict[str, Any]:
        with self._lock:
            resolved = path.resolve()
            if not resolved.exists():
                self._snapshot.status = "error"
                self._snapshot.error = f"Data file not found: {resolved}"
                raise FileNotFoundError(self._snapshot.error)

            try:
                with h5py.File(resolved, "r") as h5:
                    vectors = self._read_required_array(h5, "obsm/X_pca").astype("float32", copy=False)
                    umap = self._read_required_array(h5, "obsm/X_umap").astype("float32", copy=False)
                    cell_ids = self._read_string_or_categorical(h5["obs"]["_index"])
                    metadata = {
                        field_name: self._read_string_or_categorical(h5["obs"][field_name])
                        for field_name in METADATA_FIELDS
                        if field_name in h5["obs"]
                    }

                self._validate_loaded_data(vectors, umap, cell_ids, metadata)
                self._snapshot = DatasetSnapshot(
                    status="loaded",
                    data_path=str(resolved),
                    vectors=np.ascontiguousarray(vectors),
                    umap=np.ascontiguousarray(umap),
                    cell_ids=cell_ids,
                    metadata=metadata,
                    cell_id_to_index={cell_id: idx for idx, cell_id in enumerate(cell_ids)},
                    error=None,
                )
                return self._snapshot.summary()
            except Exception as exc:
                self._snapshot.status = "error"
                self._snapshot.data_path = str(resolved)
                self._snapshot.error = str(exc)
                raise

    def get_vector_by_cell_id(self, cell_id: str) -> np.ndarray:
        snapshot = self._require_loaded()
        try:
            idx = snapshot.cell_id_to_index[cell_id]
        except KeyError as exc:
            raise KeyError(f"Unknown cell_id: {cell_id}") from exc
        return snapshot.vectors[idx]

    def get_cell_metadata(self, idx: int) -> dict[str, Any]:
        snapshot = self._require_loaded()
        return {
            "cell_id": snapshot.cell_ids[idx],
            **{field_name: values[idx] for field_name, values in snapshot.metadata.items()},
            "umap": [float(snapshot.umap[idx, 0]), float(snapshot.umap[idx, 1])] if snapshot.umap is not None else None,
        }

    def sample_visualization_points(self, limit: int) -> dict[str, Any]:
        snapshot = self._require_loaded()
        if limit <= 0:
            raise ValueError("limit must be positive")

        count = snapshot.cell_count
        if limit >= count:
            indices = np.arange(count)
        else:
            indices = np.linspace(0, count - 1, limit, dtype=np.int64)

        points = []
        for idx in indices.tolist():
            meta = self.get_cell_metadata(idx)
            points.append(
                {
                    "index": int(idx),
                    "cell_id": meta["cell_id"],
                    "x": meta["umap"][0],
                    "y": meta["umap"][1],
                    "cell_type": meta.get("cell_type"),
                    "disease": meta.get("disease"),
                    "AgeGroup": meta.get("AgeGroup"),
                    "tissue": meta.get("tissue"),
                }
            )

        return {
            "dataset": snapshot.summary(),
            "limit": int(limit),
            "total": count,
            "points": points,
        }

    def _require_loaded(self) -> DatasetSnapshot:
        if not self._snapshot.loaded:
            raise RuntimeError("Dataset has not been loaded")
        return self._snapshot

    @staticmethod
    def _read_required_array(h5: h5py.File, key: str) -> np.ndarray:
        if key not in h5:
            raise KeyError(f"Required H5AD field missing: {key}")
        data = h5[key][:]
        if data.ndim != 2 or data.shape[0] == 0 or data.shape[1] == 0:
            raise ValueError(f"Invalid array shape for {key}: {data.shape}")
        return data

    @classmethod
    def _read_string_or_categorical(cls, obj: h5py.Dataset | h5py.Group) -> list[str]:
        if isinstance(obj, h5py.Dataset):
            return [cls._decode(value) for value in obj[:]]

        if {"categories", "codes"}.issubset(obj.keys()):
            categories = [cls._decode(value) for value in obj["categories"][:]]
            codes = obj["codes"][:]
            return [categories[int(code)] if int(code) >= 0 else "" for code in codes]

        raise TypeError(f"Unsupported obs field encoding for {obj.name}")

    @staticmethod
    def _decode(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    @staticmethod
    def _validate_loaded_data(
        vectors: np.ndarray,
        umap: np.ndarray,
        cell_ids: list[str],
        metadata: dict[str, list[str]],
    ) -> None:
        row_count = vectors.shape[0]
        if umap.shape[0] != row_count:
            raise ValueError("PCA and UMAP row counts do not match")
        if len(cell_ids) != row_count:
            raise ValueError("cell_id count does not match vector row count")
        for field_name, values in metadata.items():
            if len(values) != row_count:
                raise ValueError(f"metadata field {field_name} has invalid length")


data_service = DataService()
