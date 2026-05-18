from __future__ import annotations

from backend.app import create_app


def test_health_endpoint_reports_data_path():
    app = create_app()
    client = app.test_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["data_exists"] is True
    assert "faiss" in payload


def test_dataset_load_reads_pca_vectors_and_metadata():
    app = create_app()
    client = app.test_client()

    response = client.post("/api/datasets/load", json={})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["loaded"] is True
    assert payload["cell_count"] == 69032
    assert payload["vector_dim"] == 30
    assert "cell_type" in payload["metadata_fields"]
    assert payload["sample_cell_ids"]


def test_cors_allows_vite_fallback_port():
    app = create_app()
    client = app.test_client()

    response = client.get("/api/health", headers={"Origin": "http://127.0.0.1:5174"})

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5174"
