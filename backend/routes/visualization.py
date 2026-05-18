from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.services.data_service import data_service


visualization_bp = Blueprint("visualization", __name__)


@visualization_bp.get("/cells")
def cells():
    raw_limit = request.args.get("limit", current_app.config["DEFAULT_VIS_LIMIT"])
    limit = min(int(raw_limit), current_app.config["DEFAULT_VIS_LIMIT"])
    return jsonify(data_service.sample_visualization_points(limit))
