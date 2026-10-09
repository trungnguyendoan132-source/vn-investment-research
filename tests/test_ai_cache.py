import json

from vnresearch.analysis import ai


def provider(monkeypatch, report):
    monkeypatch.setenv("LLM_API_KEY", "cache-unit-test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://cache.example.test/v1")
    monkeypatch.setenv("LLM_MODEL", "cache-test-model")
    calls = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            content = {"claims": [{"text": "Nguồn dữ liệu cần được đối chiếu trước khi kết luận.",
                                    "source_ids": [report.sources[0].id]}]}
            return {"choices": [{"message": {"content": json.dumps(content)}}]}

    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        assert kwargs["allow_redirects"] is False
        return Response()

    monkeypatch.setattr(ai.requests, "post", post)
    return calls


def test_same_evidence_cache_hit_does_not_expose_mutable_claims(monkeypatch, demo_report):
    calls = provider(monkeypatch, demo_report)
    first = ai.synthesize(demo_report)
    assert first["status"] == "ok" and first["cache_hit"] is False
    first["claims"][0]["text"] = "Caller changed the result"
    second = ai.synthesize(demo_report)
    assert len(calls) == 1 and second["cache_hit"] is True
    assert second["latency_seconds"] == 0
    assert "Caller changed" not in second["claims"][0]["text"]
    second["claims"].clear()
    assert len(ai.synthesize(demo_report)["claims"]) == 1


def test_source_version_and_user_request_changes_invalidate_cache(monkeypatch, demo_report):
    calls = provider(monkeypatch, demo_report)
    report = demo_report.model_copy(deep=True)
    ai.synthesize(report)
    report.sources[0].sha256 = "a" * 64
    assert ai.synthesize(report)["cache_hit"] is False
    report.request.horizon_months += 1
    assert ai.synthesize(report)["cache_hit"] is False
    assert len(calls) == 3


def test_model_endpoint_and_credential_changes_do_not_share_cache(monkeypatch, demo_report):
    calls = provider(monkeypatch, demo_report)
    ai.synthesize(demo_report)
    monkeypatch.setenv("LLM_MODEL", "another-model")
    assert ai.synthesize(demo_report)["cache_hit"] is False
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:61392/v1")
    assert ai.synthesize(demo_report)["cache_hit"] is False
    monkeypatch.setenv("LLM_API_KEY", "another-unit-key")
    assert ai.synthesize(demo_report)["cache_hit"] is False
    assert len(calls) == 4
    assert "unit-key" not in repr(ai._AI_CACHE)


def test_expired_cache_does_not_suppress_a_fresh_call(monkeypatch, demo_report):
    calls = provider(monkeypatch, demo_report)
    clock = [1000.0]
    monkeypatch.setattr(ai.time, "monotonic", lambda: clock[0])
    ai.synthesize(demo_report)
    clock[0] += ai._CACHE_TTL_SECONDS
    assert ai.synthesize(demo_report)["cache_hit"] is False
    assert len(calls) == 2


def test_invalid_ai_result_is_not_cached(monkeypatch, demo_report):
    provider(monkeypatch, demo_report)
    calls = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            calls.append(True)
            return {"choices": [{"message": {"content": '{"claims":[{"text":"Lãi 999 phần trăm.","source_ids":["missing"]}]}'}}]}

    monkeypatch.setattr(ai.requests, "post", lambda *args, **kwargs: Response())
    assert ai.synthesize(demo_report)["status"] == "error"
    assert ai.synthesize(demo_report)["status"] == "error"
    assert len(calls) == 2 and not ai._AI_CACHE
