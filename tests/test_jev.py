from copy import deepcopy

from vnresearch.analysis.jev import endpoint, evaluate


def response_payload():
    return {"model": "jev-1.13.0", "usage": {"input_tokens": 100, "output_tokens": 10}, "answers": {
        "research_action": {"type": "choice", "choice": "watchlist", "confidence": 0.96,
                            "probabilities": {"insufficient_data": 0.05, "needs_review": 0.05, "watchlist": 0.85, "risk_caution": 0.05}},
        "requires_review": {"type": "noul", "noul": 0.1},
    }}


def install_response(monkeypatch, payload):
    monkeypatch.setenv("JEV_API_KEY", "jev-unit-test-key")
    monkeypatch.setenv("JEV_BASE_URL", "https://api.typesafe.ai")
    class Response:
        status_code = 200
        def raise_for_status(self):
            return None

        def json(self):
            return payload
    monkeypatch.setattr("vnresearch.analysis.jev.requests.post", lambda *a, **kw: Response())


def test_jev_endpoint_normalization():
    expected = "https://api.typesafe.ai/v1/systemone"
    assert endpoint("https://api.typesafe.ai") == expected
    assert endpoint("https://api.typesafe.ai/v1/") == expected
    assert endpoint(expected) == expected


def test_jev_missing_key(monkeypatch, demo_report):
    monkeypatch.setattr("vnresearch.analysis.jev.load_environment", lambda: None)
    monkeypatch.setattr("vnresearch.platform.providers.load_environment", lambda: None)
    monkeypatch.setenv("JEV_BASE_URL", "https://api.typesafe.ai")
    monkeypatch.setenv("JEV_MODEL", "jev-latest")
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert evaluate(demo_report)["status"] == "unavailable"


def test_jev_cannot_bypass_demo_or_missing_evidence(monkeypatch, demo_report):
    install_response(monkeypatch, response_payload())
    result = evaluate(demo_report)
    assert result["status"] == "ok"
    assert result["proposed_decision"] == "watchlist"
    assert result["applied_decision"] == "needs_review"
    assert result["deterministic_guard"] is True


def test_jev_rejects_undeclared_option(monkeypatch, demo_report):
    data = response_payload()
    data["answers"]["research_action"]["choice"] = "guaranteed_profit"
    install_response(monkeypatch, data)
    assert evaluate(demo_report)["status"] == "error"


def test_jev_rejects_invalid_probability(monkeypatch, demo_report):
    data = deepcopy(response_payload())
    data["answers"]["requires_review"]["noul"] = 1.5
    install_response(monkeypatch, data)
    assert evaluate(demo_report)["status"] == "error"
