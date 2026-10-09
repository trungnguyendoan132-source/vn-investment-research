"""Bounded, explicit market-source contract. No account rotation or automatic retry."""

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
from threading import Lock
import time

import pandas as pd
import requests


KBS_BASE = "https://kbbuddywts.kbsec.com.vn/iis-server/investment"
CONTRACT_SOURCE = "https://github.com/thinh-vu/vnstock/blob/88825be3f9aab729362e6fca178eb6e9ae4d3f88/vnstock/explorer/kbs/quote.py"
CONTRACT_VERSION = "kbs-data-day-2026-10-09"
_LOCK = Lock()
_LAST_REQUEST = 0.0


@dataclass(frozen=True)
class MarketConfig:
    provider: str = "kbs"
    timeout_seconds: float = 15.0
    maximum_days: int = 366
    maximum_bytes: int = 2 * 1024 * 1024
    minimum_interval_seconds: float = 2.0
    archive_dir: Path | None = None

    def __post_init__(self):
        if self.provider != "kbs":
            raise ValueError("Provider hỗ trợ là kbs; không tự đổi nguồn khi gặp lỗi")
        if not 1 <= self.timeout_seconds <= 30 or not 1 <= self.maximum_days <= 366:
            raise ValueError("Market timeout/window ngoài giới hạn")
        if not 1024 <= self.maximum_bytes <= 5 * 1024 * 1024 or self.minimum_interval_seconds < 2:
            raise ValueError("Market response/rate bound ngoài giới hạn")

    @classmethod
    def from_env(cls):
        return cls(provider=os.environ.get("VNRESEARCH_MARKET_PROVIDER", "kbs").strip().lower(),
                   timeout_seconds=float(os.environ.get("VNRESEARCH_MARKET_TIMEOUT", "15")),
                   archive_dir=Path(os.environ.get("VNRESEARCH_MARKET_ARCHIVE_DIR", "var/data/market")))


def capabilities() -> dict:
    return {"provider": "kbs", "contract_version": CONTRACT_VERSION, "contract_source": CONTRACT_SOURCE,
            "endpoint": KBS_BASE + "/stocks/{ticker}/data_day", "frequency": "daily", "price_unit": "VND",
            "volume_unit": "shares", "adjustment_basis": "unknown", "max_days_per_request": 366,
            "max_response_bytes": 2 * 1024 * 1024, "automatic_retries": 0,
            "corporate_actions": False, "financial_filings": False,
            "note": "Public endpoint can change or fail; adjustment and publication latency are not certified."}


def fetch_prices(ticker: str, start: date, end: date, *, config: MarketConfig | None = None,
                 session=None) -> tuple[pd.DataFrame, dict]:
    global _LAST_REQUEST
    config = config or MarketConfig.from_env()
    if not re.fullmatch(r"[A-Z0-9]{2,10}", ticker) or start > end or (end - start).days > config.maximum_days:
        raise ValueError("Ticker hoặc cửa sổ truy vấn không hợp lệ")
    endpoint = f"{KBS_BASE}/stocks/{ticker}/data_day"
    params = {"sdate": start.strftime("%d-%m-%Y"), "edate": end.strftime("%d-%m-%Y")}
    client = session or requests.Session()
    try:
        with _LOCK:
            pause = config.minimum_interval_seconds - (time.monotonic() - _LAST_REQUEST)
            if pause > 0:
                time.sleep(pause)
            _LAST_REQUEST = time.monotonic()
            response = client.get(endpoint, params=params, headers={"Accept": "application/json", "User-Agent": "VNResearch/0.2"},
                                  timeout=(5, config.timeout_seconds), stream=True, allow_redirects=False)
            try:
                if response.status_code != 200:
                    raise ValueError(f"KBS HTTP {response.status_code}; không retry hoặc chuyển tài khoản")
                chunks, size = [], 0
                for chunk in response.iter_content(chunk_size=65536):
                    size += len(chunk)
                    if size > config.maximum_bytes:
                        raise ValueError("KBS response vượt giới hạn kích thước")
                    chunks.append(chunk)
                payload = b"".join(chunks)
            finally:
                response.close()
    except requests.RequestException as exc:
        raise ValueError(f"KBS network error: {type(exc).__name__}; không tự retry") from exc
    finally:
        if session is None:
            client.close()
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("KBS response không phải JSON hợp lệ") from exc
    if not isinstance(document, dict) or document.get("symbol") != ticker or not isinstance(document.get("data_day"), list):
        raise ValueError("KBS schema/symbol mismatch")
    observations = document["data_day"]
    if len(observations) > 370:
        raise ValueError("KBS trả quá nhiều phiên cho cửa sổ ngày giới hạn")
    frame = pd.DataFrame(observations)
    if frame.empty:
        frame = pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
    required = {"t", "o", "h", "l", "c", "v"}
    if not required.issubset(frame):
        raise ValueError("KBS schema thiếu OHLCV")
    frame = frame.rename(columns={"t": "date", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    if len(frame):
        timestamps = pd.to_datetime(frame.date, format="%Y-%m-%d %H:%M", errors="raise")
        frame["date"] = timestamps.dt.strftime("%Y-%m-%d")
        if (timestamps.dt.date < start).any() or (timestamps.dt.date > end).any():
            raise ValueError("KBS observations ngoài cửa sổ yêu cầu")
    source_url = requests.Request("GET", endpoint, params=params).prepare().url
    frame["ticker"], frame["price_unit"], frame["volume_unit"] = ticker, "VND", "shares"
    frame["source_url"], frame["price_basis"] = source_url, "unknown"
    digest = hashlib.sha256(payload).hexdigest()
    archived = None
    if config.archive_dir:
        config.archive_dir.mkdir(parents=True, exist_ok=True)
        target = config.archive_dir / f"{digest}.json"
        if target.exists() and target.read_bytes() != payload:
            raise ValueError("Market archive checksum collision")
        if not target.exists():
            target.write_bytes(payload)
        archived = str(target.resolve())
    metadata = {**capabilities(), "request_url": source_url, "response_sha256": digest,
                "response_bytes": len(payload), "archived_response": archived,
                "start": start.isoformat(), "end": end.isoformat(), "observations": len(frame)}
    frame.attrs["provider"] = metadata
    return frame, metadata
