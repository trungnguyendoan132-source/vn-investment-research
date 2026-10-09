from dataclasses import dataclass
import os
from pathlib import Path


ASSETS = Path(__file__).resolve().parents[1] / "assets"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    workers: int = 2
    api_key: str | None = None

    @classmethod
    def from_env(cls):
        from vnresearch.platform.environment import load_environment
        load_environment()
        return cls(
            Path(os.getenv("VNRESEARCH_DATA_DIR", "var")).resolve(),
            max(1, min(4, int(os.getenv("VNRESEARCH_WORKERS", "2")))),
            os.getenv("VNRESEARCH_API_KEY") or None,
        )

    def prepare(self):
        for child in ["jobs", "uploads", "cache"]:
            (self.data_dir / child).mkdir(parents=True, exist_ok=True)


def require_local_bind(host: str, settings: Settings):
    if host not in {"127.0.0.1", "localhost", "::1"} and not settings.api_key:
        raise ValueError("Cấu hình VNRESEARCH_API_KEY trước khi mở API ra mạng")
