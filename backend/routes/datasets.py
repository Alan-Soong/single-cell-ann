from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from backend.services.data_service import data_service


datasets_bp = Blueprint("datasets", __name__)


@datasets_bp.post("/load")
def load_dataset():
    payload = request.get_json(silent=True) or {}
    data_path = Path(payload.get("path") or current_app.config["DATA_PATH"])
    summary = data_service.load_h5ad(data_path)
    return jsonify(summary)


@datasets_bp.get("/current")
def current_dataset():
    return jsonify(data_service.snapshot.summary())
