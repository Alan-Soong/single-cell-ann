from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.routes.permissions import require_roles
from backend.services.llm_analysis_service import LlmAnalysisError, llm_analysis_service
from backend.services.search_service import search_service


search_bp = Blueprint("search", __name__)


@search_bp.post("/search")
@require_roles("normal_user", "researcher", "data_manager", "admin")
def search():
    payload = request.get_json(silent=True) or {}
    cell_id = str(payload.get("cell_id") or "").strip()
    dataset_id = str(payload.get("dataset_id") or "").strip() or None
    index_id = str(payload.get("index_id") or "").strip() or None
    top_k = int(payload.get("top_k") or current_app.config["DEFAULT_TOP_K"])
    top_k = min(top_k, current_app.config["MAX_TOP_K"])

    try:
        result = search_service.search_by_cell_id(
            cell_id,
            top_k,
            current_app.config["LOG_DIR"],
            registry_path=current_app.config["DATASET_REGISTRY_PATH"],
            dataset_id=dataset_id,
            index_id=index_id,
        )
        return jsonify(result)
    except KeyError as exc:
        return jsonify({"error": "unknown_cell", "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": "search_unavailable", "message": str(exc)}), 503


@search_bp.post("/search/analyze")
@require_roles("normal_user", "researcher", "data_manager", "admin")
def analyze_search():
    payload = request.get_json(silent=True) or {}
    search_result = payload.get("search_result")
    question = str(payload.get("question") or "").strip() or None
    enable_thinking = payload.get("enable_thinking")
    if enable_thinking is not None and not isinstance(enable_thinking, bool):
        return jsonify({"error": "invalid_request", "message": "enable_thinking must be a boolean"}), 400

    try:
        result = llm_analysis_service.analyze_search_result(
            search_result,
            current_app.config,
            user_question=question,
            enable_thinking=enable_thinking,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    except LlmAnalysisError as exc:
        return jsonify({"error": "llm_unavailable", "message": str(exc)}), 503
