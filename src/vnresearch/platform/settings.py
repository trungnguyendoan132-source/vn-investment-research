from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
from pathlib import Path


ASSETS = Path(__file__).resolve().parents[1] / "assets"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    workers: int = 2
    api_key: str | None = field(default=None, repr=False)
    user_api_tokens: dict[str, str] = field(default_factory=dict, repr=False)
    max_pending: int = 32
    upload_max_bytes: int = 2 * 1024 * 1024
    upload_ttl_hours: int = 168
    retention_days: int = 30
    filing_dir: Path | None = None
    dataset_dir: Path | None = None

    def __post_init__(self):
        if not 1 <= self.workers <= 4 or not 1 <= self.max_pending <= 10000:
            raise ValueError("Cấu hình worker/hàng đợi không hợp lệ")
        if not 1 <= self.upload_max_bytes <= 2 * 1024 * 1024 or self.upload_ttl_hours < 1 or self.retention_days < 1:
            raise ValueError("Cấu hình dung lượng/lưu trữ không hợp lệ")
        if not isinstance(self.user_api_tokens, dict):
            raise ValueError("Token người dùng phải là object owner:token")
        if self.api_key and (not isinstance(self.api_key, str) or not self.api_key.isascii() or len(self.api_key) > 4096):
            raise ValueError("API key phải là chuỗi ASCII hợp lệ")
        for owner, token in self.user_api_tokens.items():
            if (not isinstance(owner, str) or not owner or len(owner) > 80 or not owner.isascii() or
                    not all(c.isalnum() or c in "-_." for c in owner) or not isinstance(token, str) or
                    not token or not token.isascii() or len(token) > 4096):
                raise ValueError("Cấu hình token người dùng không hợp lệ")
        tokens = list(self.user_api_tokens.values()) + ([self.api_key] if self.api_key else [])
        if len(tokens) != len(set(tokens)):
            raise ValueError("Mỗi người dùng phải có token riêng")

    @property
    def authentication_enabled(self) -> bool:
        return bool(self.api_key or self.user_api_tokens)

    def principal(self, token: str | None) -> str:
        if not self.authentication_enabled:
            return "local"
        if not token or len(token) > 4096 or not token.isascii():
            raise ValueError("API key không đúng")
        supplied = hashlib.sha256(token.encode()).digest()
        for owner, expected in self.user_api_tokens.items():
            if hmac.compare_digest(supplied, hashlib.sha256(expected.encode()).digest()):
                return "user:" + owner
        if self.api_key and hmac.compare_digest(supplied, hashlib.sha256(self.api_key.encode()).digest()):
            return "local"
        raise ValueError("API key không đúng")

    @classmethod
    def from_env(cls):
        from vnresearch.platform.environment import load_environment
        load_environment()
        return cls(
            Path(os.getenv("VNRESEARCH_DATA_DIR", "var")).resolve(),
            max(1, min(4, int(os.getenv("VNRESEARCH_WORKERS", "2")))),
            os.getenv("VNRESEARCH_API_KEY") or None,
            user_api_tokens=json.loads(os.getenv("VNRESEARCH_USER_TOKENS_JSON") or "{}"),
            max_pending=int(os.getenv("VNRESEARCH_MAX_PENDING", "32")),
            upload_ttl_hours=int(os.getenv("VNRESEARCH_UPLOAD_TTL_HOURS", "168")),
            retention_days=int(os.getenv("VNRESEARCH_RETENTION_DAYS", "30")),
            filing_dir=Path(os.getenv("VNRESEARCH_FILING_DIR") or Path(os.getenv("VNRESEARCH_DATA_DIR", "var")) / "financial-filings").resolve(),
            dataset_dir=Path(os.getenv("VNRESEARCH_DATASET_DIR") or Path(os.getenv("VNRESEARCH_DATA_DIR", "var")) / "financial-snapshots").resolve(),
        )

    def prepare(self):
        for child in ["jobs", "uploads", "cache"]:
            (self.data_dir / child).mkdir(parents=True, exist_ok=True)


def require_local_bind(host: str, settings: Settings):
    if host not in {"127.0.0.1", "localhost", "::1"} and not settings.authentication_enabled:
        raise ValueError("Cấu hình VNRESEARCH_API_KEY trước khi mở API ra mạng")
