from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from backend.services.data_service import METADATA_FIELDS, DatasetSnapshot, data_service


COLOR_FIELDS = ("dataset", "cell_type", "disease", "AgeGroup", "tissue")
NUMERIC_OBS_CANDIDATES = ("G2M.Score", "S.Score")


@dataclass(frozen=True)
class GeneMatch:
    dataset_id: str
    gene_index: int
    gene_id: str
    gene_name: str
    feature_type: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "gene_index": self.gene_index,
            "gene_id": self.gene_id,
            "gene_name": self.gene_name,
            "feature_type": self.feature_type,
        }


class VisualizationService:
    def cells(
        self,
        *,
        dataset_ids: list[str],
        limit: int,
        registry_path: Path,
        color_by: str = "cell_type",
        filters: dict[str, list[str]] | None = None,
        sample_strategy: str = "even",
    ) -> dict[str, Any]:
        if limit <= 0:
            raise ValueError("limit must be positive")

        snapshots = self._resolve_snapshots(dataset_ids, registry_path)
        filters = filters or {}
        color_by = color_by or "cell_type"

        selected_rows_by_dataset = {
            snapshot.dataset_id: self._filtered_indices(snapshot, filters) for snapshot in snapshots
        }
        total_visible = int(sum(len(rows) for rows in selected_rows_by_dataset.values()))
        sampled_rows_by_dataset = self._sample_rows(selected_rows_by_dataset, limit, sample_strategy)

        gene_matches: dict[str, GeneMatch] = {}
        if color_by.startswith("gene:"):
            gene_query = color_by.split(":", 1)[1].strip()
            if not gene_query:
                raise ValueError("gene color_by requires a gene name or id")
            gene_matches = {
                snapshot.dataset_id: self.resolve_gene(snapshot, gene_query) for snapshot in snapshots
            }

        points: list[dict[str, Any]] = []
        for snapshot in snapshots:
            row_indices = sampled_rows_by_dataset[snapshot.dataset_id]
            expression_values: dict[int, float] = {}
            gene_match = gene_matches.get(snapshot.dataset_id)
            if gene_match is not None:
                expression_values = self._read_gene_expression(
                    Path(snapshot.data_path),
                    gene_match.gene_index,
                    row_indices,
                )

            for row_index in row_indices:
                meta = data_service.get_cell_metadata(
                    int(row_index),
                    dataset_id=snapshot.dataset_id,
                    registry_path=registry_path,
                )
                color_value = self._color_value(meta, color_by, expression_values.get(int(row_index)))
                point = {
                    "index": int(row_index),
                    "row_index": int(row_index),
                    "dataset_id": meta["dataset_id"],
                    "dataset_name": meta["dataset_name"],
                    "cell_id": meta["cell_id"],
                    "x": meta["umap"][0],
                    "y": meta["umap"][1],
                    "cell_type": meta.get("cell_type"),
                    "disease": meta.get("disease"),
                    "AgeGroup": meta.get("AgeGroup"),
                    "tissue": meta.get("tissue"),
                    "color_value": color_value,
                }
                if gene_match is not None:
                    point["expression"] = color_value
                    point["gene"] = gene_match.summary()
                points.append(point)

        points = points[:limit]
        return {
            "dataset": snapshots[0].summary() if len(snapshots) == 1 else None,
            "datasets": [snapshot.summary() for snapshot in snapshots],
            "limit": int(limit),
            "total": int(sum(snapshot.cell_count for snapshot in snapshots)),
            "visible_total": total_visible,
            "sample_strategy": sample_strategy,
            "color_by": color_by,
            "filters": filters,
            "gene": [match.summary() for match in gene_matches.values()],
            "stats": self._view_stats(points, snapshots, total_visible, color_by),
            "points": points,
        }

    def options(
        self,
        *,
        dataset_ids: list[str],
        registry_path: Path,
        gene_query: str = "",
        gene_limit: int = 20,
    ) -> dict[str, Any]:
        snapshots = self._resolve_snapshots(dataset_ids, registry_path)
        categorical_fields: dict[str, list[dict[str, Any]]] = {}
        for field_name in METADATA_FIELDS:
            counts = Counter()
            for snapshot in snapshots:
                counts.update(snapshot.metadata.get(field_name, []))
            categorical_fields[field_name] = [
                {"value": value, "count": int(count)} for value, count in counts.most_common(80)
            ]

        numeric_fields = sorted(
            {
                field_name
                for snapshot in snapshots
                for field_name in self._numeric_obs_fields(Path(snapshot.data_path))
            }
        )

        return {
            "datasets": [snapshot.summary() for snapshot in snapshots],
            "color_fields": list(COLOR_FIELDS) + ["gene:<gene_name_or_id>"],
            "categorical_fields": categorical_fields,
            "numeric_fields": numeric_fields,
            "gene_matches": self.search_genes(snapshots, gene_query, gene_limit) if gene_query else [],
        }

    def search_genes(self, snapshots: list[DatasetSnapshot], query: str, limit: int) -> list[dict[str, Any]]:
        query = query.strip().lower()
        if not query:
            return []

        matches: list[dict[str, Any]] = []
        for snapshot in snapshots:
            for match in self._iter_gene_matches(Path(snapshot.data_path), query, limit):
                matches.append({**match.summary(), "dataset_name": snapshot.name})
                if len(matches) >= limit:
                    return matches
        return matches

    def resolve_gene(self, snapshot: DatasetSnapshot, query: str) -> GeneMatch:
        normalized_query = query.strip().lower()
        if not normalized_query:
            raise ValueError("gene query is required")

        with h5py.File(snapshot.data_path, "r") as h5:
            gene_ids = self._read_string_or_categorical(h5["var"]["_index"])
            gene_names = self._read_string_or_categorical(h5["var"]["feature_name"]) if "feature_name" in h5["var"] else gene_ids
            feature_types = (
                self._read_string_or_categorical(h5["var"]["feature_type"])
                if "feature_type" in h5["var"]
                else [""] * len(gene_ids)
            )

        for idx, (gene_id, gene_name) in enumerate(zip(gene_ids, gene_names)):
            if normalized_query in {gene_id.lower(), gene_name.lower()}:
                return GeneMatch(
                    dataset_id=snapshot.dataset_id,
                    gene_index=idx,
                    gene_id=gene_id,
                    gene_name=gene_name,
                    feature_type=feature_types[idx] or None,
                )

        raise KeyError(f"Gene not found in dataset {snapshot.dataset_id}: {query}")

    def _resolve_snapshots(self, dataset_ids: list[str], registry_path: Path) -> list[DatasetSnapshot]:
        clean_dataset_ids = [item.strip() for item in dataset_ids if item.strip()]
        if clean_dataset_ids:
            return [data_service.get_snapshot(dataset_id, registry_path=registry_path) for dataset_id in clean_dataset_ids]
        return [data_service.get_snapshot(registry_path=registry_path)]

    def _filtered_indices(self, snapshot: DatasetSnapshot, filters: dict[str, list[str]]) -> np.ndarray:
        if not filters:
            return np.arange(snapshot.cell_count, dtype=np.int64)

        mask = np.ones(snapshot.cell_count, dtype=bool)
        for field_name, allowed_values in filters.items():
            if not allowed_values or field_name not in snapshot.metadata:
                continue
            allowed = {str(value) for value in allowed_values if str(value)}
            if not allowed:
                continue
            values = np.asarray(snapshot.metadata[field_name], dtype=object)
            mask &= np.isin(values, list(allowed))
        return np.flatnonzero(mask).astype(np.int64, copy=False)

    def _sample_rows(
        self,
        rows_by_dataset: dict[str, np.ndarray],
        limit: int,
        sample_strategy: str,
    ) -> dict[str, list[int]]:
        total_rows = sum(len(rows) for rows in rows_by_dataset.values())
        if total_rows <= limit:
            return {dataset_id: rows.astype(int).tolist() for dataset_id, rows in rows_by_dataset.items()}

        sampled: dict[str, list[int]] = {}
        remaining = limit
        items = list(rows_by_dataset.items())
        for idx, (dataset_id, rows) in enumerate(items):
            if idx == len(items) - 1:
                quota = remaining
            else:
                quota = max(1, int(round(limit * (len(rows) / total_rows)))) if len(rows) else 0
                quota = min(quota, remaining)
            remaining -= quota
            sampled[dataset_id] = self._sample_array(rows, quota, sample_strategy)
        return sampled

    @staticmethod
    def _sample_array(rows: np.ndarray, quota: int, sample_strategy: str) -> list[int]:
        if quota <= 0 or len(rows) == 0:
            return []
        if quota >= len(rows):
            return rows.astype(int).tolist()
        if sample_strategy == "random":
            rng = np.random.default_rng(42)
            return sorted(rng.choice(rows, size=quota, replace=False).astype(int).tolist())
        positions = np.linspace(0, len(rows) - 1, quota, dtype=np.int64)
        return rows[positions].astype(int).tolist()

    @staticmethod
    def _color_value(meta: dict[str, Any], color_by: str, expression: float | None) -> Any:
        if color_by == "dataset":
            return meta.get("dataset_name") or meta.get("dataset_id")
        if color_by.startswith("gene:"):
            return float(expression or 0.0)
        return meta.get(color_by)

    @staticmethod
    def _read_gene_expression(path: Path, gene_index: int, row_indices: list[int]) -> dict[int, float]:
        values: dict[int, float] = {}
        with h5py.File(path, "r") as h5:
            x_group = h5["X"]
            if x_group.attrs.get("encoding-type") != "csr_matrix":
                raise ValueError("Only CSR matrix expression storage is supported")
            data = x_group["data"]
            indices = x_group["indices"]
            indptr = x_group["indptr"]
            for row_index in row_indices:
                start = int(indptr[row_index])
                end = int(indptr[row_index + 1])
                row_gene_indices = indices[start:end]
                matches = np.flatnonzero(row_gene_indices == gene_index)
                values[int(row_index)] = float(data[start + int(matches[0])]) if len(matches) else 0.0
        return values

    @staticmethod
    def _view_stats(
        points: list[dict[str, Any]],
        snapshots: list[DatasetSnapshot],
        visible_total: int,
        color_by: str,
    ) -> dict[str, Any]:
        dataset_counts = Counter(point["dataset_name"] or point["dataset_id"] for point in points)
        color_counts = Counter(str(point.get("color_value") or "") for point in points if not color_by.startswith("gene:"))
        metadata_counts = {
            field_name: [
                {"value": value, "count": int(count)}
                for value, count in Counter(point.get(field_name) or "" for point in points).most_common(20)
            ]
            for field_name in METADATA_FIELDS
        }

        expression_values = [
            float(point["expression"])
            for point in points
            if isinstance(point.get("expression"), (int, float))
        ]
        expression_stats = None
        if expression_values:
            values = np.asarray(expression_values, dtype=np.float64)
            expression_stats = {
                "min": float(np.min(values)),
                "max": float(np.max(values)),
                "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "expressing_count": int(np.count_nonzero(values > 0)),
                "expressing_fraction": float(np.count_nonzero(values > 0) / len(values)),
            }

        xs = [point["x"] for point in points]
        ys = [point["y"] for point in points]
        bounds = None
        if xs and ys:
            bounds = {
                "x_min": float(min(xs)),
                "x_max": float(max(xs)),
                "y_min": float(min(ys)),
                "y_max": float(max(ys)),
            }

        return {
            "dataset_count": len(snapshots),
            "total_cells": int(sum(snapshot.cell_count for snapshot in snapshots)),
            "visible_cells": int(visible_total),
            "sampled_points": len(points),
            "sample_fraction": float(len(points) / visible_total) if visible_total else 0.0,
            "by_dataset": [{"value": value, "count": int(count)} for value, count in dataset_counts.most_common()],
            "by_color": [{"value": value, "count": int(count)} for value, count in color_counts.most_common(30)],
            "metadata_counts": metadata_counts,
            "expression": expression_stats,
            "bounds": bounds,
        }

    def _iter_gene_matches(self, path: Path, query: str, limit: int) -> list[GeneMatch]:
        with h5py.File(path, "r") as h5:
            gene_ids = self._read_string_or_categorical(h5["var"]["_index"])
            gene_names = self._read_string_or_categorical(h5["var"]["feature_name"]) if "feature_name" in h5["var"] else gene_ids
            feature_types = (
                self._read_string_or_categorical(h5["var"]["feature_type"])
                if "feature_type" in h5["var"]
                else [""] * len(gene_ids)
            )

        matches = []
        dataset_id = path.stem
        for idx, (gene_id, gene_name) in enumerate(zip(gene_ids, gene_names)):
            if query in gene_id.lower() or query in gene_name.lower():
                matches.append(
                    GeneMatch(
                        dataset_id=dataset_id,
                        gene_index=idx,
                        gene_id=gene_id,
                        gene_name=gene_name,
                        feature_type=feature_types[idx] or None,
                    )
                )
                if len(matches) >= limit:
                    return matches
        return matches

    @staticmethod
    def _numeric_obs_fields(path: Path) -> list[str]:
        fields = []
        with h5py.File(path, "r") as h5:
            for field_name in NUMERIC_OBS_CANDIDATES:
                if field_name in h5["obs"] and isinstance(h5["obs"][field_name], h5py.Dataset):
                    fields.append(field_name)
        return fields

    @classmethod
    def _read_string_or_categorical(cls, obj: h5py.Dataset | h5py.Group) -> list[str]:
        if isinstance(obj, h5py.Dataset):
            return [cls._decode(value) for value in obj[:]]
        if {"categories", "codes"}.issubset(obj.keys()):
            categories = [cls._decode(value) for value in obj["categories"][:]]
            codes = obj["codes"][:]
            return [categories[int(code)] if int(code) >= 0 else "" for code in codes]
        raise TypeError(f"Unsupported field encoding for {obj.name}")

    @staticmethod
    def _decode(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)


visualization_service = VisualizationService()
