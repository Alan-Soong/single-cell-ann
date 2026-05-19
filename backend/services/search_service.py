from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.data_service import data_service
from backend.services.index_service import index_service


class SearchService:
    def search_by_cell_id(
        self,
        cell_id: str,
        top_k: int,
        log_dir: Path,
        *,
        registry_path: Path,
        dataset_id: str | None = None,
        index_id: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        request_log: dict[str, Any] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "query_type": "ANN",
            "query_object": cell_id,
            "dataset_id": dataset_id,
            "index_id": index_id,
            "top_k": top_k,
            "status": "failed",
        }

        try:
            if not cell_id:
                raise ValueError("cell_id is required")
            if top_k <= 0:
                raise ValueError("top_k must be positive")

            active_index = index_service.snapshot
            if not active_index.ready:
                raise RuntimeError("Index has not been built")

            query_snapshot, query_row_index = data_service.resolve_cell(
                cell_id,
                active_index.dataset_ids,
                registry_path=registry_path,
                dataset_id=dataset_id,
            )
            query_vector = query_snapshot.vectors[query_row_index]
            distances, indices, bundle = index_service.search(query_vector, top_k + 1, index_id)

            hits = []
            for distance, idx in zip(distances.tolist(), indices.tolist()):
                if idx < 0:
                    continue
                cell_ref = bundle.index_to_cell[int(idx)]
                meta = data_service.get_cell_metadata(
                    cell_ref.row_index,
                    dataset_id=cell_ref.dataset_id,
                    registry_path=registry_path,
                )
                if meta["dataset_id"] == query_snapshot.dataset_id and meta["cell_id"] == cell_id:
                    continue
                hits.append(
                    {
                        "rank": len(hits) + 1,
                        "dataset_id": meta["dataset_id"],
                        "dataset_name": meta["dataset_name"],
                        "cell_id": meta["cell_id"],
                        "distance": float(distance),
                        "similarity": float(1.0 / (1.0 + max(float(distance), 0.0))),
                        "cell_type": meta.get("cell_type"),
                        "disease": meta.get("disease"),
                        "AgeGroup": meta.get("AgeGroup"),
                        "tissue": meta.get("tissue"),
                        "umap": meta.get("umap"),
                    }
                )
                if len(hits) >= top_k:
                    break

            elapsed_ms = (time.perf_counter() - started) * 1000
            result = {
                "query": {
                    "cell_id": cell_id,
                    "dataset_id": query_snapshot.dataset_id,
                    "index_id": bundle.snapshot.index_id,
                    "top_k": top_k,
                },
                "query_cell": data_service.get_cell_metadata(
                    query_row_index,
                    dataset_id=query_snapshot.dataset_id,
                    registry_path=registry_path,
                ),
                "query_time_ms": round(elapsed_ms, 3),
                "index": bundle.snapshot.summary(),
                "result_count": len(hits),
                "hits": hits,
            }

            request_log.update(
                {
                    "status": "success",
                    "latency_ms": result["query_time_ms"],
                    "result_count": len(hits),
                    "index_id": bundle.snapshot.index_id,
                    "index_mode": bundle.snapshot.mode,
                }
            )
            return result
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            request_log.update(
                {
                    "latency_ms": round(elapsed_ms, 3),
                    "result_count": 0,
                    "error": str(exc),
                    "index_mode": index_service.snapshot.mode,
                }
            )
            raise
        finally:
            self._write_query_log(log_dir, request_log)

    @staticmethod
    def _write_query_log(log_dir: Path, record: dict[str, Any]) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "query_log.jsonl"
        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


search_service = SearchService()
