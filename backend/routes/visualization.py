from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.services.visualization_service import visualization_service


visualization_bp = Blueprint("visualization", __name__)


@visualization_bp.get("/cells")
def cells():
    raw_limit = request.args.get("limit", current_app.config["DEFAULT_VIS_LIMIT"])
    limit = min(int(raw_limit), current_app.config["DEFAULT_VIS_LIMIT"])
    dataset_ids = [item.strip() for item in request.args.getlist("dataset_id") if item.strip()]
    if not dataset_ids:
        csv_dataset_ids = request.args.get("dataset_ids", "")
        dataset_ids = [item.strip() for item in csv_dataset_ids.split(",") if item.strip()]
    color_by = request.args.get("color_by", "cell_type")
    sample_strategy = request.args.get("sample_strategy", "even")
    filters = _parse_filters()

    try:
        return jsonify(
            visualization_service.cells(
                dataset_ids=dataset_ids,
                limit=limit,
                registry_path=current_app.config["DATASET_REGISTRY_PATH"],
                color_by=color_by,
                filters=filters,
                sample_strategy=sample_strategy,
            )
        )
    except KeyError as exc:
        return jsonify({"error": "not_found", "message": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
    except ValueError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400


@visualization_bp.get("/options")
def options():
    dataset_ids = [item.strip() for item in request.args.getlist("dataset_id") if item.strip()]
    if not dataset_ids:
        csv_dataset_ids = request.args.get("dataset_ids", "")
        dataset_ids = [item.strip() for item in csv_dataset_ids.split(",") if item.strip()]
    gene_query = request.args.get("gene_query", request.args.get("q", ""))
    gene_limit = min(int(request.args.get("gene_limit", 20)), 100)

    try:
        return jsonify(
            visualization_service.options(
                dataset_ids=dataset_ids,
                registry_path=current_app.config["DATASET_REGISTRY_PATH"],
                gene_query=gene_query,
                gene_limit=gene_limit,
            )
        )
    except KeyError as exc:
        return jsonify({"error": "not_found", "message": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
    except ValueError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400


def _parse_filters() -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for field_name in ("cell_type", "disease", "AgeGroup", "tissue"):
        values = request.args.getlist(field_name)
        csv_values = request.args.get(f"filter_{field_name}", "")
        if csv_values:
            values.extend(csv_values.split(","))
        clean_values = [value.strip() for value in values if value.strip()]
        if clean_values:
            filters[field_name] = clean_values
    return filters
