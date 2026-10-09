import pytest

from vnresearch.platform.providers import effective_provider_config, endpoint_url


@pytest.mark.parametrize("base,kind,expected", [
    ("http://localhost:61392/v1", "llm", "http://localhost:61392/v1"),
    ("http://127.0.0.1:8795/v1/systemone", "jev", "http://127.0.0.1:8795/v1/systemone"),
    ("http://[::1]:8795/v1/", "jev", "http://[::1]:8795/v1/systemone"),
    ("https://api.typesafe.ai", "jev", "https://api.typesafe.ai/v1/systemone"),
    ("https://example.test/v1/chat/completions", "llm", "https://example.test/v1"),
])
def test_provider_loopback_and_endpoint_normalization(base, kind, expected):
    assert endpoint_url(base, kind) == expected


@pytest.mark.parametrize("base", [
    "http://example.test/v1", "http://localhost.evil/v1", "http://127.0.0.1.evil/v1",
    "http://user:key@127.0.0.1/v1", "https://user:key@example.test/v1",
    "http://127.0.0.1/v1?key=secret", "http://127.0.0.1/v1#part", "file:///tmp/api",
    "http://2130706433/v1", "http://127.0.0.1:99999/v1",
])
def test_unsafe_provider_endpoints_are_rejected(base):
    with pytest.raises(ValueError):
        endpoint_url(base)


def test_localhost_resolution_must_be_loopback(monkeypatch):
    monkeypatch.setattr("vnresearch.platform.providers.socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("192.0.2.1", 80))])
    with pytest.raises(ValueError):
        endpoint_url("http://localhost/v1")


def test_explicit_model_and_secrets_are_preserved_safely(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:61392/v1")
    monkeypatch.setenv("LLM_MODEL", "exact-luna-server-id")
    monkeypatch.setenv("LLM_API_KEY", "mock-private-key")
    config = effective_provider_config("llm")
    assert config.model == "exact-luna-server-id" and config.configured
    assert "mock-private-key" not in repr(config)
