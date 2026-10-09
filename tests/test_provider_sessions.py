import threading
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from vnresearch.api.app import create_app
from vnresearch.domain.models import Report
from vnresearch.platform.provider_sessions import ProviderSessionStore, require_loopback_same_origin
from vnresearch.platform.providers import ProviderConfig, effective_provider_config, provider_config_context
from vnresearch.platform.settings import Settings


ORIGIN = "http://testserver"


def provider_payload(llm_key="llm-secret-session-a", jev_key="jev-secret-session-a"):
    return {"providers": {
        "llm": {"base_url": "https://llm.example.test/v1", "api_key": llm_key, "model": "gpt-test"},
        "jev": {"base_url": "https://jev.example.test/v1/systemone", "api_key": jev_key, "model": "jev-test"},
    }}


def test_provider_sessions_return_status_only_and_are_owner_scoped(tmp_path):
    settings = Settings(tmp_path, user_api_tokens={"alice": "alice-app-token", "bob": "bob-app-token"})
    app = create_app(settings)
    alice_headers = {"X-API-Key": "alice-app-token", "Origin": ORIGIN}
    bob_headers = {"X-API-Key": "bob-app-token", "Origin": ORIGIN}
    payload = provider_payload()

    with TestClient(app) as client:
        response = client.post("/api/provider-sessions", json=payload, headers=alice_headers)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["llm_configured"] and result["jev_configured"]
        assert result["llm_model"] == "gpt-test" and result["jev_model"] == "jev-test"
        assert result["expires_in_seconds"] == 8 * 60 * 60
        assert result["id"] and "api_key" not in result
        assert "llm-secret-session-a" not in response.text and "jev-secret-session-a" not in response.text

        read = client.get(f"/api/provider-sessions/{result['id']}", headers=bob_headers)
        assert read.status_code == 404
        read = client.get(f"/api/provider-sessions/{result['id']}", headers=alice_headers)
        assert read.status_code == 200
        assert "llm-secret-session-a" not in read.text and "jev-secret-session-a" not in read.text

        deleted = client.delete(f"/api/provider-sessions/{result['id']}", headers=alice_headers)
        assert deleted.status_code == 200 and deleted.json() == {"status": "deleted"}
        assert client.get(f"/api/provider-sessions/{result['id']}", headers=alice_headers).status_code == 404

    for path in tmp_path.glob("jobs.sqlite3*"):
        data = path.read_bytes()
        assert b"llm-secret-session-a" not in data
        assert b"jev-secret-session-a" not in data


def test_provider_sessions_are_partial_and_reject_blank_or_key_without_url(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://env-llm.example.test/v1")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    monkeypatch.setenv("LLM_API_KEY", "env-llm-secret")
    app = create_app(Settings(tmp_path))
    headers = {"Origin": ORIGIN}
    with TestClient(app) as client:
        response = client.post("/api/provider-sessions", json={"providers": {
            "jev": {"base_url": "https://jev.example.test", "api_key": "jev-only-secret"}
        }}, headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["llm_configured"] and result["llm_model"] == "env-model"
        assert result["jev_configured"] and "jev-only-secret" not in response.text

        missing_url = client.post("/api/provider-sessions", json={"providers": {
            "llm": {"api_key": "must-not-echo"}
        }}, headers=headers)
        assert missing_url.status_code == 422
        assert "must-not-echo" not in missing_url.text

        blank_key = client.post("/api/provider-sessions", json={"providers": {
            "llm": {"base_url": "https://llm.example.test/v1", "api_key": "   "}
        }}, headers=headers)
        assert blank_key.status_code == 400
        assert "api_key" not in blank_key.text


def test_job_provider_configs_are_isolated_and_never_persisted(tmp_path, demo_report, monkeypatch, caplog):
    from vnresearch.analysis import ai

    # The app path under test uses only the worker ContextVar and never calls a provider.
    monkeypatch.setattr(ai, "synthesize", lambda report: {"status": "unavailable", "claims": []})
    observed = []
    validation_errors = []

    def fake_analyze(request, *args, **kwargs):
        llm = effective_provider_config("llm")
        jev = effective_provider_config("jev")
        observed.append((request.ticker, llm.api_key, jev.api_key))
        time.sleep(0.02)
        report = demo_report.model_copy(deep=True, update={
            "ticker": request.ticker,
            "request": request,
            "news": [article.model_copy(update={"ticker": request.ticker}) for article in demo_report.news],
        })
        try:
            Report.model_validate(report.model_dump(mode="json"))
        except Exception as exc:
            validation_errors.append(type(exc).__name__ + ": " + str(exc))
            raise
        return report

    monkeypatch.setattr("vnresearch.api.app.analyze", fake_analyze)
    app = create_app(Settings(tmp_path, workers=2, max_pending=4))
    with TestClient(app) as client:
        jobs = []
        for ticker, suffix in (("FPT", "a"), ("VCB", "b")):
            payload = provider_payload("private-llm-" + suffix, "private-jev-" + suffix)
            session = client.post("/api/provider-sessions", json=payload,
                                  headers={"Origin": ORIGIN}).json()
            request = {"ticker": ticker, "mode": "demo", "as_of": "2026-10-09",
                       "start_year": 2022, "end_year": 2025, "use_ai": False, "use_jev": False}
            response = client.post("/api/jobs", json=request,
                                   headers={"Origin": ORIGIN, "X-Provider-Session": session["id"]})
            assert response.status_code == 202, response.text
            jobs.append(response.json())

        results = []
        for job in jobs:
            for _ in range(500):
                result = client.get(f"/api/jobs/{job['id']}", headers={"X-Job-Token": job["token"]}).json()
                if result["status"] in {"completed", "failed", "interrupted"}:
                    break
                threading.Event().wait(0.01)
            assert result["status"] == "completed", {"job": result, "observed": observed,
                                                       "validation_errors": validation_errors}
            results.append(result)
            assert app.state.provider_sessions.for_job(job["id"]) is None

    assert set(observed) == {
        ("FPT", "private-llm-a", "private-jev-a"),
        ("VCB", "private-llm-b", "private-jev-b"),
    }
    assert not any(secret in caplog.text for secret in ("private-llm-a", "private-jev-a", "private-llm-b", "private-jev-b"))
    for path in tmp_path.glob("jobs.sqlite3*"):
        data = path.read_bytes()
        for secret in ("private-llm-a", "private-jev-a", "private-llm-b", "private-jev-b"):
            assert secret.encode() not in data
    assert all("private-llm" not in str(result) and "private-jev" not in str(result) for result in results)


def test_omitted_job_provider_uses_environment_and_missing_key_stays_unconfigured(monkeypatch):
    monkeypatch.setattr("vnresearch.platform.providers.load_environment", lambda: None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("VNRESEARCH_AI_API_KEY", raising=False)
    jev = ProviderConfig("https://jev.example.test/v1/systemone", "jev-test", "jev-only-key")
    with provider_config_context({"jev": jev}):
        config = effective_provider_config("llm")
        assert not config.configured
        assert effective_provider_config("jev").api_key == "jev-only-key"


def test_provider_session_store_is_bounded_and_same_origin_guard_rejects_remote():
    store = ProviderSessionStore(session_ttl=60, job_ttl=60, max_sessions=1)
    config = {"llm": ProviderConfig("https://llm.example.test/v1", "m", "key")}
    first, _ = store.create("local", config)
    second, _ = store.create("local", config)
    with pytest.raises(KeyError):
        store.get("local", first)
    assert store.get("local", second)["llm"].api_key == "key"

    remote = SimpleNamespace(client=SimpleNamespace(host="203.0.113.5"), headers={},
                             url=SimpleNamespace(scheme="http", netloc="127.0.0.1:8000"))
    with pytest.raises(PermissionError):
        require_loopback_same_origin(remote)
    mismatched = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"),
                                 headers={"origin": "http://evil.example"},
                                 url=SimpleNamespace(scheme="http", netloc="127.0.0.1:8000"))
    with pytest.raises(PermissionError):
        require_loopback_same_origin(mismatched)
    local = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"),
                            headers={"origin": "http://127.0.0.1:8000"},
                            url=SimpleNamespace(scheme="http", netloc="127.0.0.1:8000"))
    require_loopback_same_origin(local)
