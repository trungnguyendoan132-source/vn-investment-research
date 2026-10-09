"""Provider configuration and transport policy. Callers must disable redirects."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import ipaddress
import os
import socket
from collections.abc import Iterator, Mapping
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from vnresearch.platform.environment import load_environment


ProviderKind = Literal["llm", "jev"]
ProviderConfigs = Mapping[ProviderKind, "ProviderConfig"]
_JOB_PROVIDER_CONFIGS: ContextVar[ProviderConfigs | None] = ContextVar("job_provider_configs", default=None)


@contextmanager
def provider_config_context(configs: ProviderConfigs | None) -> Iterator[None]:
    """Bind one job's provider credentials to the current worker context."""
    token = _JOB_PROVIDER_CONFIGS.set(dict(configs) if configs is not None else None)
    try:
        yield
    finally:
        _JOB_PROVIDER_CONFIGS.reset(token)


def endpoint_url(base: str, kind: ProviderKind = "llm") -> str:
    """Return the LLM base or Jev endpoint; permit HTTP only to loopback."""
    if kind not in {"llm", "jev"} or not isinstance(base, str) or not base.strip():
        raise ValueError("Invalid provider endpoint")
    base = base.strip()
    if any(c.isspace() for c in base) or "\\" in base:
        raise ValueError("Invalid provider URL")
    parsed = urlsplit(base)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Provider URL must use HTTPS or loopback HTTP")
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValueError("Provider URL cannot contain credentials, query or fragment")
    try:
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("Invalid provider port")
    except ValueError as exc:
        raise ValueError("Invalid provider port") from exc
    if parsed.scheme == "http":
        host = parsed.hostname.lower()
        if host == "localhost":
            try:
                addresses = socket.getaddrinfo(host, parsed.port or 80, type=socket.SOCK_STREAM)
            except OSError as exc:
                raise ValueError("Cannot validate localhost resolution") from exc
            if not addresses or not all(ipaddress.ip_address(item[4][0]).is_loopback for item in addresses):
                raise ValueError("localhost must resolve exclusively to loopback")
        else:
            try:
                if not ipaddress.ip_address(host).is_loopback:
                    raise ValueError("HTTP providers must use loopback")
            except ValueError as exc:
                raise ValueError("HTTP providers must use literal loopback or localhost") from exc
    path = parsed.path.rstrip("/")
    if kind == "jev":
        if not path.endswith("/systemone"):
            path += "/systemone" if path.endswith("/v1") else "/v1/systemone"
    else:
        for suffix in ("/chat/completions", "/models"):
            if path.endswith(suffix):
                path = path[:-len(suffix)]
        if not path:
            path = "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    model: str
    api_key: str | None = field(repr=False)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def effective_provider_config(kind: ProviderKind = "llm") -> ProviderConfig:
    if kind not in {"llm", "jev"}:
        raise ValueError("Unknown provider kind")
    job_configs = _JOB_PROVIDER_CONFIGS.get()
    if job_configs is not None and kind in job_configs:
        return job_configs[kind]
    load_environment()
    if kind == "llm":
        base = os.getenv("LLM_BASE_URL") or os.getenv("VNRESEARCH_AI_BASE_URL") or "https://api.openai.com/v1"
        model = os.getenv("LLM_MODEL") or os.getenv("VNRESEARCH_AI_MODEL") or "auto"
        key = os.getenv("LLM_API_KEY") or os.getenv("VNRESEARCH_AI_API_KEY")
    elif kind == "jev":
        base = os.getenv("JEV_BASE_URL") or "https://api.typesafe.ai"
        model = os.getenv("JEV_MODEL") or "jev-latest"
        key = os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY")
    else:
        raise ValueError("Unknown provider kind")
    model = model.strip()
    if not model or len(model) > 200 or any(ord(c) < 32 for c in model):
        raise ValueError("Invalid provider model")
    if key and (len(key) > 4096 or any(ord(c) < 32 for c in key)):
        raise ValueError("Invalid provider key encoding")
    return ProviderConfig(endpoint_url(base, kind), model, key)
