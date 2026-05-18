from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.data_service import data_service
from backend.services.index_service import index_service


class SearchService:
    def search_by_cell_id(self, cell_id: str, top_k: int, log_dir: Path) -> dict[str, Any]:
        started = time.perf_counter()
        request_log: dict[str, Any] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "query_type": "ANN",
            "query_object": cell_id,
            "top_k": top_k,
            "status": "failed",
        }

        try:
            if not cell_id:
                raise ValueError("cell_id is required")
            if top_k <= 0:
                raise ValueError("top_k must be positive")

            query_vector = data_service.get_vector_by_cell_id(cell_id)
            distances, indices = index_service.search(query_vector, top_k + 1)

            hits = []
            for distance, idx in zip(distances.tolist(), indices.tolist()):
                if idx < 0:
                    continue
                meta = data_service.get_cell_metadata(int(idx))
                if meta["cell_id"] == cell_id:
                    continue
                hits.append(
                    {
                        "rank": len(hits) + 1,
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
                    "top_k": top_k,
                },
                "query_time_ms": round(elapsed_ms, 3),
                "index": index_service.snapshot.summary(),
                "result_count": len(hits),
                "hits": hits,
            }

            request_log.update(
                {
                    "status": "success",
                    "latency_ms": result["query_time_ms"],
                    "result_count": len(hits),
                    "index_mode": index_service.snapshot.mode,
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
