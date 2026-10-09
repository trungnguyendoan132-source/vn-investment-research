import hashlib
import json
import time

from fastapi.testclient import TestClient
import pymupdf
import pytest

from vnresearch.api.app import create_app
from vnresearch.platform.jobs import JobStore
from vnresearch.platform.settings import Settings, require_local_bind
from vnresearch.reports.export import export_report


def test_persistent_jobs_are_isolated_and_reconciled(tmp_path):
    store = JobStore(tmp_path)
    first, token = store.create('{"ticker":"FPT"}')
    second, _ = store.create('{"ticker":"VCB"}')
    assert store.job_dir(first) != store.job_dir(second)
    with pytest.raises(KeyError):
        store.get(first, "wrong")
    restarted = JobStore(tmp_path)
    restarted.reconcile_interrupted()
    assert restarted.get(first, token)["status"] == "interrupted"


def test_public_bind_requires_api_key(tmp_path):
    with pytest.raises(ValueError):
        require_local_bind("0.0.0.0", Settings(tmp_path))


def test_pdf_is_real_unicode_and_manifest_matches(tmp_path, demo_report):
    manifest = export_report(demo_report, tmp_path)
    with pymupdf.open(tmp_path / "report.pdf") as document:
        text = "\n".join(page.get_text() for page in document)
        assert len(document) >= 2
        assert "MINH HỌA" in text
        assert "Tổng quan vĩ mô" in text
        assert "Phân tích ngành" in text
        assert "Danh mục nguồn" in text
        assert "\ufffd" not in text
    for name, metadata in manifest["files"].items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == metadata["sha256"]
    payload = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert payload["request"]["mode"] == "demo"


def test_api_rejects_bad_request_and_protects_job(tmp_path):
    app = create_app(Settings(tmp_path))
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 200
        assert client.post("/api/jobs", json={"ticker": "../bad"}).status_code == 422
        job_id, _ = app.state.store.create('{"ticker":"FPT"}')
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
        assert client.post("/api/uploads/private", files={"file": ("x.csv", b"a,b\n1,2")}).status_code == 400


def test_api_creates_and_downloads_real_report(tmp_path):
    app = create_app(Settings(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/jobs", json={"ticker": "VCB", "mode": "demo", "as_of": "2026-10-09", "start_year": 2022, "end_year": 2025})
        assert response.status_code == 202
        created = response.json()
        headers = {"X-Job-Token": created["token"]}
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            job = client.get("/api/jobs/" + created["id"], headers=headers).json()
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)
        assert job["status"] == "completed", job
        pdf = client.get(f"/api/jobs/{created['id']}/files/report.pdf", headers=headers)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        assert client.get(f"/api/jobs/{created['id']}/files/report.pdf").status_code == 404
        assert job["report"]["request"]["mode"] == "demo"
