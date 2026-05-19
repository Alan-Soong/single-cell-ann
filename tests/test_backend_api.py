from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.app import create_app
from backend.config import Config
from backend.faiss_runtime import inspect_faiss_runtime


@contextmanager
def runtime_tmpdir():
    root = Path(__file__).resolve().parents[1] / "runtime" / "pytest"
    root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="case-", dir=root) as name:
        yield Path(name)


def make_test_config(tmp_path: Path):
    class TestConfig(Config):
        DATASET_REGISTRY_PATH = tmp_path / "registry.json"
        USERS_PATH = tmp_path / "users.json"
        INDEX_DIR = tmp_path / "indexes"
        LOG_DIR = tmp_path / "logs"

    return TestConfig


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


def test_auth_register_login_me_and_logout():
    with runtime_tmpdir() as tmp_path:
        app = create_app(make_test_config(tmp_path))
        client = app.test_client()

        register = client.post(
            "/api/auth/register",
            json={"username": "demo_user", "password": "secret123", "role": "researcher"},
        )
        assert register.status_code == 201
        assert register.get_json()["user"]["role"] == "researcher"

        login = client.post("/api/auth/login", json={"username": "demo_user", "password": "secret123"})
        assert login.status_code == 200
        token = login.get_json()["token"]

        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.get_json()["authenticated"] is True
        assert me.get_json()["user"]["username"] == "demo_user"

        logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logout.status_code == 200
        assert logout.get_json()["authenticated"] is False


def test_dataset_registry_scan_validate_and_list():
    with runtime_tmpdir() as tmp_path:
        app = create_app(make_test_config(tmp_path))
        client = app.test_client()

        scan = client.post("/api/datasets/scan")
        assert scan.status_code == 200
        assert scan.get_json()["count"] >= 1

        validate = client.post("/api/datasets/validate", json={"dataset_ids": ["liver"]})
        assert validate.status_code == 200
        payload = validate.get_json()
        assert payload["validated_count"] == 1
        assert payload["datasets"][0]["cell_count"] == 69032
        assert payload["datasets"][0]["vector_dim"] == 30

        datasets = client.get("/api/datasets")
        assert datasets.status_code == 200
        liver = next(item for item in datasets.get_json()["datasets"] if item["dataset_id"] == "liver")
        assert liver["status"] == "validated"
        assert "cell_type" in liver["metadata_fields"]


def test_combined_and_separate_indexes_return_dataset_aware_results():
    runtime = inspect_faiss_runtime()
    if not runtime.available:
        pytest.skip("FAISS is unavailable in this Python environment")

    with runtime_tmpdir() as tmp_path:
        app = create_app(make_test_config(tmp_path))
        client = app.test_client()

        client.post("/api/datasets/scan")
        dataset = client.post("/api/datasets/load", json={"dataset_id": "liver"}).get_json()
        sample_cell_id = dataset["sample_cell_ids"][0]

        combined = client.post(
            "/api/index/build",
            json={"dataset_ids": ["liver"], "mode": "combined", "nlist": 64, "nprobe": 8},
        )
        assert combined.status_code == 200
        assert combined.get_json()["ready"] is True
        assert combined.get_json()["dataset_ids"] == ["liver"]

        search = client.post(
            "/api/search",
            json={"cell_id": sample_cell_id, "dataset_id": "liver", "top_k": 3},
        )
        assert search.status_code == 200
        result = search.get_json()
        assert result["result_count"] == 3
        assert result["query_cell"]["dataset_id"] == "liver"
        assert all(hit["dataset_id"] == "liver" for hit in result["hits"])

        separate = client.post(
            "/api/index/build",
            json={"dataset_ids": ["liver"], "mode": "separate", "nlist": 64, "nprobe": 8},
        )
        assert separate.status_code == 200
        assert separate.get_json()["built_indexes"][0]["build_mode"] == "separate"
