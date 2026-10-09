"""Ephemeral browser-entered LLM/Jev configuration; provider secrets never reach storage."""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import ipaddress
import secrets
import threading
import time
from typing import Mapping
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from vnresearch.platform.providers import ProviderConfig, ProviderKind, effective_provider_config, endpoint_url


SESSION_TTL_SECONDS = 8 * 60 * 60
JOB_CONFIG_TTL_SECONDS = SESSION_TTL_SECONDS
MAX_SESSIONS = 256
MAX_JOB_CONFIGS = 512


class ProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    base_url: str = Field(min_length=1, max_length=2048)
    api_key: SecretStr = Field(min_length=1, max_length=4096)
    model: str = Field(default="auto", min_length=1, max_length=200)


class JevInput(ProviderInput):
    model: str = Field(default="jev-latest", min_length=1, max_length=200)


class ProviderInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: ProviderInput | None = None
    jev: JevInput | None = None


class ProviderSessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: ProviderInputs


def _valid_model(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 200 or any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise ValueError("Invalid provider model")
    return normalized


def _valid_key(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    if (len(normalized) > 4096 or not normalized.isascii() or
            any(ord(char) < 33 or ord(char) > 126 for char in normalized)):
        raise ValueError("Invalid provider key")
    return normalized


def provider_configs(value: ProviderSessionInput) -> dict[ProviderKind, ProviderConfig]:
    result = {}
    for kind in ("llm", "jev"):
        item = getattr(value.providers, kind)
        if item is None:
            continue
        key = _valid_key(item.api_key.get_secret_value())
        if key is None:
            raise ValueError("Provider API key is required when a provider is submitted")
        result[kind] = ProviderConfig(
            base_url=endpoint_url(item.base_url, kind),
            model=_valid_model(item.model),
            api_key=key,
        )
    if not result:
        raise ValueError("At least one provider key is required")
    return result


def provider_status(configs: Mapping[ProviderKind, ProviderConfig]) -> dict:
    result = {}
    for kind in ("llm", "jev"):
        try:
            config = configs.get(kind) or effective_provider_config(kind)
            result[kind + "_configured"] = config.configured
            result[kind + "_model"] = config.model
            result[kind + "_configuration_status"] = "configured_unverified" if config.configured else "missing_key"
        except ValueError:
            result[kind + "_configured"] = False
            result[kind + "_configuration_status"] = "invalid_configuration"
    return result


@dataclass(frozen=True)
class _Session:
    owner: str
    configs: Mapping[ProviderKind, ProviderConfig]
    expires_at: float


@dataclass(frozen=True)
class _JobConfigs:
    owner: str
    configs: Mapping[ProviderKind, ProviderConfig]
    expires_at: float


class ProviderSessionStore:
    """Bounded, process-local credential sessions and per-job snapshots."""

    def __init__(self, *, session_ttl: int = SESSION_TTL_SECONDS,
                 job_ttl: int = JOB_CONFIG_TTL_SECONDS,
                 max_sessions: int = MAX_SESSIONS, max_jobs: int = MAX_JOB_CONFIGS):
        if min(session_ttl, job_ttl, max_sessions, max_jobs) <= 0:
            raise ValueError("Provider session limits must be positive")
        self.session_ttl, self.job_ttl = session_ttl, job_ttl
        self.max_sessions, self.max_jobs = max_sessions, max_jobs
        self._sessions: OrderedDict[str, _Session] = OrderedDict()
        self._jobs: OrderedDict[str, _JobConfigs] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def _session_digest(session_id: str) -> str:
        if not isinstance(session_id, str) or not 32 <= len(session_id) <= 128:
            raise KeyError("Provider session not found")
        return hashlib.sha256(session_id.encode("ascii", errors="ignore")).hexdigest()

    def _prune(self, now: float):
        for key in [key for key, value in self._sessions.items() if value.expires_at <= now]:
            self._sessions.pop(key, None)
        for key in [key for key, value in self._jobs.items() if value.expires_at <= now]:
            self._jobs.pop(key, None)

    def create(self, owner: str, configs: Mapping[ProviderKind, ProviderConfig]) -> tuple[str, float]:
        if not configs or not set(configs).issubset({"llm", "jev"}):
            raise ValueError("At least one valid provider configuration is required")
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            session_id = secrets.token_urlsafe(32)
            digest = self._session_digest(session_id)
            while digest in self._sessions:
                session_id = secrets.token_urlsafe(32)
                digest = self._session_digest(session_id)
            self._sessions[digest] = _Session(owner, dict(configs), now + self.session_ttl)
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
        return session_id, float(self.session_ttl)

    def get(self, owner: str, session_id: str) -> dict[ProviderKind, ProviderConfig]:
        configs, _ = self.get_with_ttl(owner, session_id)
        return configs

    def get_with_ttl(self, owner: str, session_id: str) -> tuple[dict[ProviderKind, ProviderConfig], int]:
        digest = self._session_digest(session_id)
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            session = self._sessions.get(digest)
            if session is None or session.owner != owner:
                raise KeyError("Provider session not found")
            self._sessions.move_to_end(digest)
            remaining = max(0, int(session.expires_at - now))
            return dict(session.configs), remaining

    def delete(self, owner: str, session_id: str):
        digest = self._session_digest(session_id)
        with self._lock:
            session = self._sessions.get(digest)
            if session is None or session.owner != owner or session.expires_at <= time.monotonic():
                self._sessions.pop(digest, None)
                raise KeyError("Provider session not found")
            self._sessions.pop(digest, None)

    def bind_job(self, job_id: str, owner: str, configs: Mapping[ProviderKind, ProviderConfig]):
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            self._jobs[job_id] = _JobConfigs(owner, dict(configs), now + self.job_ttl)
            self._jobs.move_to_end(job_id)
            while len(self._jobs) > self.max_jobs:
                self._jobs.popitem(last=False)

    def for_job(self, job_id: str) -> dict[ProviderKind, ProviderConfig] | None:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            job = self._jobs.get(job_id)
            if job is None:
                return None
            self._jobs.move_to_end(job_id)
            return dict(job.configs)

    def retry_configs(self, job_id: str, owner: str) -> dict[ProviderKind, ProviderConfig] | None:
        configs = self.for_job(job_id)
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None or record.owner != owner:
                return None
        return configs

    def finish_job(self, job_id: str, *, retryable: bool):
        if not retryable:
            with self._lock:
                self._jobs.pop(job_id, None)


def require_loopback_same_origin(request):
    """Reject remote callers and browser origins other than this exact origin."""
    peer = request.client.host if request.client else ""
    try:
        loopback = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        loopback = peer == "testclient"
    if not loopback:
        raise PermissionError("Provider sessions are available only from loopback")
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        request_origin = request.url
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or
                parsed.scheme.lower() != request_origin.scheme.lower() or
                parsed.netloc.lower() != request_origin.netloc.lower()):
            raise PermissionError("Provider sessions require the same browser origin")
