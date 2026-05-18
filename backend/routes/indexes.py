from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.services.index_service import index_service


index_bp = Blueprint("index", __name__)


@index_bp.post("/build")
def build_index():
    payload = request.get_json(silent=True) or {}
    nlist = int(payload.get("nlist") or current_app.config["FAISS_NLIST"])
    nprobe = int(payload.get("nprobe") or current_app.config["FAISS_NPROBE"])
    try:
        summary = index_service.build_ivf_flat(current_app.config["INDEX_DIR"], nlist=nlist, nprobe=nprobe)
        return jsonify(summary)
    except RuntimeError as exc:
        return jsonify({"error": "index_build_failed", "message": str(exc), **index_service.snapshot.summary()}), 503


@index_bp.get("/status")
def index_status():
    return jsonify(index_service.snapshot.summary())
