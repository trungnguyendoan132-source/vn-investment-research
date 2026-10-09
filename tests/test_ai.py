import json

from vnresearch.analysis.ai import synthesize


def fake_response(claims):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"claims": claims})}}]}
    return Response()


def configure(monkeypatch):
    monkeypatch.setenv("VNRESEARCH_AI_API_KEY", "unit-test-key")
    monkeypatch.setenv("VNRESEARCH_AI_MODEL", "unit-test-model")


def test_missing_key_is_explicit(monkeypatch, demo_report):
    monkeypatch.delenv("VNRESEARCH_AI_API_KEY", raising=False)
    assert synthesize(demo_report)["status"] == "unavailable"


def test_ai_claims_must_reference_existing_evidence(monkeypatch, demo_report):
    configure(monkeypatch)
    monkeypatch.setattr("vnresearch.analysis.ai.requests.post", lambda *a, **k: fake_response([{"text": "Nhận xét có dẫn nguồn.", "source_ids": ["fake-source"]}]))
    assert synthesize(demo_report)["status"] == "error"


def test_ai_may_not_invent_numbers(monkeypatch, demo_report):
    configure(monkeypatch)
    monkeypatch.setattr("vnresearch.analysis.ai.requests.post", lambda *a, **k: fake_response([{"text": "Lợi nhuận tăng 999 phần trăm.", "source_ids": [demo_report.sources[0].id]}]))
    assert synthesize(demo_report)["status"] == "error"


def test_valid_structured_ai_result(monkeypatch, demo_report):
    configure(monkeypatch)
    monkeypatch.setattr("vnresearch.analysis.ai.requests.post", lambda *a, **k: fake_response([{"text": "Cần xác minh dữ liệu snapshot trước khi ra quyết định.", "source_ids": [demo_report.sources[0].id]}]))
    result = synthesize(demo_report)
    assert result["status"] == "ok"
    assert len(result["claims"]) == 1
    assert "unit-test-key" not in json.dumps(result)
