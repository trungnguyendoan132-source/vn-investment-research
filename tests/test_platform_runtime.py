from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import threading
import time

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from vnresearch.api.app import create_app
from vnresearch.domain.models import AnalysisRequest, Report, Source
from vnresearch.platform.jobs import JobStore, QueueFullError, StateConflict, UploadError
from vnresearch.platform.locking import DataDirectoryLock
from vnresearch.platform.settings import Settings


REQUEST = {"ticker": "FPT", "mode": "demo", "as_of": "2026-10-09", "start_year": 2022, "end_year": 2025}
PRICE_CSV = b"ticker,date,open,high,low,close,volume,price_unit,source_url\nFPT,2026-10-08,1,1,1,1,1,VND,https://example.test/source\n"


def test_default_request_uses_automatic_providers_but_demo_remains_offline():
    automatic = AnalysisRequest(ticker="FPT")
    assert automatic.mode.value == "live" and automatic.use_ai and automatic.use_jev
    demo = AnalysisRequest(ticker="FPT", mode="demo")
    assert not demo.use_ai and not demo.use_jev
    explicit = AnalysisRequest(ticker="FPT", mode="demo", use_ai=True, use_jev=True)
    assert explicit.use_ai and explicit.use_jev
    disabled = AnalysisRequest(ticker="FPT", use_ai=False, use_jev=False)
    assert not disabled.use_ai and not disabled.use_jev


def poll(client, job, extra_headers=None):
    headers = {"X-Job-Token": job["token"], **(extra_headers or {})}
    deadline = time.monotonic() + 20
    result = None
    while time.monotonic() < deadline:
        response = client.get("/api/jobs/" + job["id"], headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] in {"completed", "failed", "interrupted"}:
            return result
        time.sleep(0.05)
    raise AssertionError(f"Job timed out; last status={result['status'] if result else None}, phase={result.get('phase') if result else None}")


def test_legacy_migration_and_no_running_replay(tmp_path):
    database = tmp_path / "jobs.sqlite3"
    job_id = "a" * 32
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE jobs(id TEXT PRIMARY KEY,token_hash TEXT,request_json TEXT,status TEXT,phase TEXT,percent INTEGER,created_at TEXT,updated_at TEXT,error TEXT)")
        connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,NULL)",
                           (job_id, hashlib.sha256(b"old-token").hexdigest(), json.dumps(REQUEST), "queued", "queued", 0, "2026-10-09", "2026-10-09"))
    connection.close()
    store = JobStore(tmp_path)
    assert store.get(job_id, "old-token", "local")["status"] == "queued"
    queued, token = store.create(json.dumps(REQUEST))
    claimed = store.claim_next("dead-instance")
    assert claimed["id"] == job_id
    store.reconcile_interrupted(include_queued=False)
    assert store.get(job_id, "old-token", "local")["status"] == "interrupted"
    assert store.get(queued, token)["status"] == "queued"
    with pytest.raises(StateConflict):
        store.update(job_id, "running", "financial", 10)


def test_atomic_claims_capacity_and_idempotency(tmp_path):
    store = JobStore(tmp_path, max_pending=4)
    first = store.create(json.dumps(REQUEST), "user:alice", "same-key")
    assert store.create(json.dumps(REQUEST), "user:alice", "same-key") == first
    for _ in range(3):
        store.create(json.dumps(REQUEST))
    with pytest.raises(QueueFullError):
        store.create(json.dumps(REQUEST))
    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(lambda i: store.claim_next(str(i)), range(8)))
    ids = [job["id"] for job in claims if job]
    assert len(ids) == len(set(ids)) == 4


def test_second_instance_cannot_interrupt_live_job_and_queue_is_bounded(tmp_path, monkeypatch, demo_report):
    entered, release = threading.Event(), threading.Event()

    def analyze(request, inputs, progress, **kwargs):
        entered.set()
        assert release.wait(5)
        return demo_report.model_copy(deep=True)

    monkeypatch.setattr("vnresearch.api.app.analyze", analyze)
    app = create_app(Settings(tmp_path, workers=1, max_pending=2))
    with TestClient(app) as client:
        first = client.post("/api/jobs", json=REQUEST, headers={"Idempotency-Key": "first"}).json()
        try:
            assert entered.wait(2)
            duplicate = client.post("/api/jobs", json=REQUEST, headers={"Idempotency-Key": "first"}).json()
            assert duplicate["id"] == first["id"] and duplicate["token"] == first["token"]
            assert client.post("/api/jobs", json={**REQUEST, "ticker": "VCB"}, headers={"Idempotency-Key": "first"}).status_code == 409
            queued = client.post("/api/jobs", json=REQUEST).json()
            assert client.post("/api/jobs", json=REQUEST).status_code == 429
            with pytest.raises(RuntimeError, match="instance"):
                with TestClient(create_app(Settings(tmp_path))):
                    pass
            assert app.state.store.get(first["id"], first["token"])["status"] == "running"
            cancelled = client.post(f"/api/jobs/{queued['id']}/cancel", headers={"X-Job-Token": queued["token"]}).json()
            assert cancelled["status"] == "failed" and cancelled["error_code"] == "JOB_CANCELLED"
        finally:
            release.set()
        assert poll(client, first)["status"] == "completed"


def test_owner_bound_upload_job_and_malformed_auth(tmp_path, monkeypatch, demo_report):
    monkeypatch.setattr("vnresearch.api.app.analyze", lambda request, *a, **kw: demo_report.model_copy(deep=True, update={"request": request}))
    settings = Settings(tmp_path, user_api_tokens={"alice": "alice-test-token", "bob": "bob-test-token"})
    assert "alice-test-token" not in repr(settings)
    alice, bob = {"X-API-Key": "alice-test-token"}, {"X-API-Key": "bob-test-token"}
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        assert client.get("/api/companies", headers=[(b"X-API-Key", b"\xff")]).status_code == 401
        assert client.post("/api/uploads/prices", headers=alice, files={"file": ("bad.csv", b"plain text")}).status_code == 400
        uploaded = client.post("/api/uploads/prices", headers=alice, files={"file": ("prices.csv", PRICE_CSV)}).json()
        request = {**REQUEST, "datasets": {"prices": uploaded["id"]}}
        assert client.post("/api/jobs", headers=bob, json=request).status_code == 400
        job = client.post("/api/jobs", headers=alice, json=request).json()
        assert client.get("/api/jobs/" + job["id"], headers={**bob, "X-Job-Token": job["token"]}).status_code == 404
        assert poll(client, job, alice)["status"] == "completed"


def test_body_cap_precedes_multipart_spooling(tmp_path, monkeypatch):
    spooled = []
    monkeypatch.setattr("starlette.formparsers.SpooledTemporaryFile", lambda *a, **kw: spooled.append(True))
    with TestClient(create_app(Settings(tmp_path))) as client:
        response = client.post("/api/uploads/prices", files={"file": ("large.csv", b"x" * (3 * 1024 * 1024))})
        assert response.status_code == 413
        assert not spooled
        chunked = client.post("/api/uploads/prices", content=(b"x" * 1048576 for _ in range(3)),
                              headers={"Content-Type": "multipart/form-data; boundary=testing"})
        assert chunked.status_code == 413 and not spooled


def test_artifact_corruption_and_readiness(tmp_path):
    app = create_app(Settings(tmp_path))
    with TestClient(app) as client:
        assert client.get("/api/health/ready").status_code == 200
        job = client.post("/api/jobs", json=REQUEST).json()
        assert poll(client, job)["status"] == "completed"
        (app.state.store.job_dir(job["id"]) / "report.json").write_text("{}", encoding="utf-8")
        status = client.get("/api/jobs/" + job["id"], headers={"X-Job-Token": job["token"]}).json()
        assert status["status"] == "failed" and status["error_code"] == "ARTIFACT_UNAVAILABLE"
        assert client.get(f"/api/jobs/{job['id']}/files/report.pdf", headers={"X-Job-Token": job["token"]}).status_code == 409
        app.state.dispatcher.stop_event.set()
        assert client.get("/api/health/ready").status_code == 503
        assert client.get("/api/health/live").status_code == 200


def test_metadata_is_unknown_until_evidence_supplied(demo_report):
    source = Source(id="test", title="Test", url="https://example.test", kind="snapshot",
                    retrieved_at=datetime.now(timezone.utc))
    assert source.verification_status == "unknown" and source.published_at is None
    assert source.publication_precision == "unknown" and source.report_basis == "unknown"
    with pytest.raises(ValidationError):
        Source(id="", title="Test", url="", kind="snapshot", retrieved_at=datetime.now())
    for value in (None, True, 123):
        with pytest.raises(ValidationError):
            AnalysisRequest(ticker=value)
    invalid = demo_report.model_dump(mode="json")
    invalid["ticker"] = "VCB"
    with pytest.raises(ValidationError):
        Report.model_validate(invalid)
    invalid["ticker"] = "FPT"
    invalid["ai"] = {"status": "ok", "claims": [{"text": "Unknown source.", "source_ids": ["missing"]}]}
    with pytest.raises(ValidationError):
        Report.model_validate(invalid)


def test_process_death_releases_lock_without_replaying_running_attempt(tmp_path, monkeypatch, demo_report):
    program = """
import json, os, sys, threading
from pathlib import Path
from fastapi.testclient import TestClient
import vnresearch.api.app as api_module
from vnresearch.platform.jobs import atomic_json
from vnresearch.platform.settings import Settings
root = Path(sys.argv[1])
entered = threading.Event()
def blocked_analyze(request, inputs, progress):
    progress('llm', 85)
    entered.set()
    threading.Event().wait()
api_module.analyze = blocked_analyze
with TestClient(api_module.create_app(Settings(root, workers=1))) as client:
    request = json.loads(sys.argv[2])
    running = client.post('/api/jobs', json={**request,'use_ai':True}).json()
    if not entered.wait(5):
        raise RuntimeError('Worker did not enter running state')
    queued = client.post('/api/jobs', json=request).json()
    atomic_json(root / 'kill-ready.json', {'pid': os.getpid(),'running': running,'queued': queued})
    threading.Event().wait()
"""
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    process = subprocess.Popen([sys.executable, "-B", "-c", program, str(tmp_path), json.dumps(REQUEST)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
    try:
        deadline = time.monotonic() + 15
        ready_file = tmp_path / "kill-ready.json"
        while not ready_file.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready_file.exists(), "Child API did not become ready before process termination"
        ready = json.loads(ready_file.read_text(encoding="utf-8"))
    finally:
        if process.poll() is None:
            os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
        process.stdout.close()
        process.stderr.close()
    lock = DataDirectoryLock(tmp_path)
    for attempt in range(20):
        try:
            lock.acquire()
            break
        except RuntimeError:
            if attempt == 19:
                raise
            time.sleep(0.05)
    lock.release()
    executed = []

    def restarted_analyze(request, inputs, progress):
        executed.append(request.use_ai)
        return demo_report.model_copy(deep=True, update={"request": request})

    monkeypatch.setattr("vnresearch.api.app.analyze", restarted_analyze)
    app = create_app(Settings(tmp_path, workers=1))
    with TestClient(app) as client:
        running, queued = ready["running"], ready["queued"]
        interrupted = app.state.store.get(running["id"], running["token"])
        assert interrupted["status"] == "interrupted" and interrupted["percent"] == 85
        assert poll(client, queued)["status"] == "completed"
        assert executed == [False]
        with app.state.store.connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM attempts WHERE job_id=?", (running["id"],)).fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM attempts WHERE job_id=?", (queued["id"],)).fetchone()[0] == 1


def test_upload_expiry_preserves_accepted_job_input(tmp_path):
    store = JobStore(tmp_path)
    upload = store.register_upload("local", "prices", PRICE_CSV, 1)
    request = {**REQUEST, "datasets": {"prices": upload["id"]}}
    job, token = store.create(json.dumps(request))
    with store.connection() as connection:
        connection.execute("UPDATE uploads SET expires_at='2000-01-01T00:00:00+00:00'")
    store.cleanup(30)
    assert store.resolve_inputs("local", request["datasets"], for_job=job)["prices"].is_file()
    with pytest.raises(UploadError, match="hết hạn"):
        store.create(json.dumps(request))
    store.cancel(job, token, "local")
    store.cleanup(30)
    assert not (tmp_path / "uploads" / f"{upload['id']}-prices.csv").exists()


def test_api_errors_are_sanitized_and_correlatable(tmp_path, monkeypatch):
    def broken_universe():
        raise RuntimeError("mock-private-provider-key and private directory")

    monkeypatch.setattr("vnresearch.api.app.company_universe", broken_universe)
    with TestClient(create_app(Settings(tmp_path)), raise_server_exceptions=False) as client:
        validation = client.post("/api/jobs", json={"ticker": "mock-private-input"})
        assert validation.status_code == 422 and validation.json()["code"] == "INVALID_REQUEST"
        assert "mock-private-input" not in validation.text
        malformed = client.post("/api/uploads/prices", content=b"malformed",
                                headers={"Content-Type": "multipart/form-data"})
        assert malformed.status_code == 400
        unexpected = client.get("/api/companies")
        assert unexpected.status_code == 500 and unexpected.json()["code"] == "SERVER_ERROR"
        assert "mock-private-provider-key" not in unexpected.text
        for response in (validation, malformed, unexpected):
            assert response.headers["X-Request-ID"] == response.json()["request_id"]
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_network_access_and_duplicate_headers_are_rejected(tmp_path):
    with TestClient(create_app(Settings(tmp_path)), client=("192.0.2.1", 45000)) as client:
        assert client.get("/api/health/live").status_code == 200
        blocked = client.get("/api/companies")
        assert blocked.status_code == 403 and blocked.json()["code"] == "LOCAL_ONLY"
    with TestClient(create_app(Settings(tmp_path, api_key="test-access-key"))) as client:
        response = client.get("/api/companies", headers=[("X-API-Key", "test-access-key"),
                                                       ("X-API-Key", "test-access-key")])
        assert response.status_code == 400 and response.json()["code"] == "DUPLICATE_HEADER"


def test_retry_creates_new_attempt_and_retention_expires_artifacts(tmp_path, monkeypatch, demo_report):
    calls = []

    def transient_pipeline(request, inputs, progress):
        calls.append(request)
        progress("financial", 20)
        if len(calls) == 1:
            raise RuntimeError("mock-private-failure")
        return demo_report.model_copy(deep=True, update={"request": request})

    monkeypatch.setattr("vnresearch.api.app.analyze", transient_pipeline)
    app = create_app(Settings(tmp_path, workers=1))
    with TestClient(app) as client:
        first = client.post("/api/jobs", json=REQUEST).json()
        failure = poll(client, first)
        assert failure["error_code"] == "PIPELINE_FAILED" and failure["percent"] == 20
        assert "mock-private-failure" not in json.dumps(failure)
        retry_path = f"/api/jobs/{first['id']}/retry"
        headers = {"X-Job-Token": first["token"], "Idempotency-Key": "explicit-retry"}
        second = client.post(retry_path, headers=headers).json()
        assert second["id"] != first["id"] and second["token"] != first["token"]
        assert client.post(retry_path, headers=headers).json()["id"] == second["id"]
        complete = poll(client, second)
        assert complete["status"] == "completed" and complete["parent_job_id"] == first["id"]
        assert len(calls) == 2
        with app.state.store.connection() as connection:
            connection.execute("UPDATE jobs SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (second["id"],))
        app.state.store.cleanup(30)
        expired = client.get(f"/api/jobs/{second['id']}/files/report.pdf", headers={"X-Job-Token": second["token"]})
        assert expired.status_code == 410 and expired.json()["code"] == "ARTIFACT_EXPIRED"


def test_legacy_failure_is_redacted_on_migration(tmp_path):
    identifier = "b" * 32
    with sqlite3.connect(tmp_path / "jobs.sqlite3") as connection:
        connection.execute("CREATE TABLE jobs(id TEXT PRIMARY KEY,token_hash TEXT,request_json TEXT,status TEXT,phase TEXT,percent INTEGER,created_at TEXT,updated_at TEXT,error TEXT)")
        connection.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)",
                           (identifier, hashlib.sha256(b"old-token").hexdigest(), json.dumps(REQUEST),
                            "failed", "failed", 20, "2026-10-09", "2026-10-09", "mock-private-legacy-key"))
    store = JobStore(tmp_path)
    result = store.get(identifier, "old-token", "local")
    assert result["error_code"] == "LEGACY_FAILURE" and "mock-private-legacy-key" not in result["error"]
    with store.connection() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_capability_secret_must_be_restored_with_ledger(tmp_path):
    store = JobStore(tmp_path)
    job, token = store.create(json.dumps(REQUEST), idempotency_key="stable-request")
    secret_path = tmp_path / ".token-secret"
    original = secret_path.read_bytes()
    secret_path.unlink()
    with pytest.raises(RuntimeError, match="Thiếu khóa"):
        JobStore(tmp_path)
    assert not secret_path.exists()
    secret_path.write_bytes(b"x" * 32)
    with pytest.raises(RuntimeError, match="không khớp"):
        JobStore(tmp_path)
    secret_path.write_bytes(original)
    restored = JobStore(tmp_path)
    assert restored.create(json.dumps(REQUEST), idempotency_key="stable-request") == (job, token)


def test_retention_runs_while_service_remains_alive(tmp_path):
    app = create_app(Settings(tmp_path, workers=1))
    app.state.dispatcher.maintenance_interval = 0.05
    uploaded = app.state.store.register_upload("local", "prices", PRICE_CSV, 1)
    path = tmp_path / "uploads" / f"{uploaded['id']}-prices.csv"
    with TestClient(app) as client:
        with app.state.store.connection() as connection:
            connection.execute("UPDATE uploads SET expires_at='2000-01-01T00:00:00+00:00'")
        deadline = time.monotonic() + 3
        while path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not path.exists()
        assert client.get("/api/health/ready").status_code == 200
