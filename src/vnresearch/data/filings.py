"""Import reviewed filing observations without overwriting the legacy snapshot."""

from datetime import date, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit

import pandas as pd

from vnresearch.domain.models import Source, utcnow


FACT_KEYS = {
    "total_assets", "current_assets", "current_liabilities", "total_liabilities", "equity",
    "equity_parent", "noncontrolling_interest", "revenue", "net_income", "net_income_parent",
    "ebt", "interest_expense", "ebit", "ebitda", "depreciation", "cfo", "capex", "eps",
    "weighted_average_shares", "diluted_eps",
}


def valid_url(value: str) -> bool:
    parsed = urlsplit(str(value))
    return (parsed.scheme in {"https", "http"} and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None)


def _date(value, name: str) -> date:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
            raise ValueError("Date must have day precision")
        return date.fromisoformat(str(value))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} phải là YYYY-MM-DD") from exc


def validate_filing(envelope: dict, document: bytes | None = None) -> dict:
    required = {"ticker", "fiscal_year", "period_start", "period_end", "period_type",
                "consolidation", "report_url", "original_sha256", "facts"}
    if not isinstance(envelope, dict):
        raise ValueError("Filing envelope phải là JSON object")
    if not required.issubset(envelope):
        raise ValueError("Filing thiếu metadata bắt buộc: " + ", ".join(sorted(required - set(envelope))))
    item = dict(envelope)
    ticker = str(item["ticker"]).strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,10}", ticker):
        raise ValueError("Invalid filing ticker")
    item["ticker"] = ticker
    start, end = _date(item["period_start"], "period_start"), _date(item["period_end"], "period_end")
    if not item.get("published_on") and not item.get("published_at"):
        raise ValueError("Phải có published_on hoặc published_at có bằng chứng")
    published = _date(item.get("published_on") or str(item["published_at"])[:10], "published_on")
    item["published_on"] = published.isoformat()
    if item.get("published_at"):
        timestamp = datetime.fromisoformat(str(item["published_at"]).replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.date() != published:
            raise ValueError("published_at cần múi giờ và cùng ngày published_on")
        item["publication_precision"] = "timestamp"
    else:
        item["published_at"] = None
        item["publication_precision"] = "day"
    if start > end or end > published or published > utcnow().date():
        raise ValueError("Kỳ hoặc ngày công bố không hợp lệ; không tự tạo ngày công bố")
    if item["period_type"] not in {"annual", "quarterly", "half_year"}:
        raise ValueError("period_type phải là annual, quarterly hoặc half_year")
    if item["consolidation"] not in {"consolidated", "separate"}:
        raise ValueError("Phải xác định BCTC hợp nhất hoặc riêng lẻ")
    if isinstance(item["fiscal_year"], bool) or not isinstance(item["fiscal_year"], int):
        raise ValueError("fiscal_year phải là số nguyên")
    if not 2000 <= item["fiscal_year"] <= end.year + 1:
        raise ValueError("fiscal_year ngoài phạm vi hỗ trợ")
    if not valid_url(item["report_url"]):
        raise ValueError("report_url phải là HTTP(S) có host")
    digest = str(item["original_sha256"]).lower()
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("original_sha256 không hợp lệ")
    if document is not None and hashlib.sha256(document).hexdigest() != digest:
        raise ValueError("Original filing document checksum mismatch")
    status = item.get("verification_status", "unverified")
    if status not in {"unknown", "unverified", "verified", "quarantined"}:
        raise ValueError("verification_status không hợp lệ")
    if status == "verified" and (document is None or not item.get("verification_note")):
        raise ValueError("Filing verified cần bản gốc khớp hash và verification_note")
    item["verification_status"] = status
    item["schema_version"] = "1.0.0"
    if not isinstance(item["facts"], list) or not item["facts"]:
        raise ValueError("Filing không có quan sát tài chính")
    normalized, seen = [], set()
    for observation in item["facts"]:
        if not isinstance(observation, dict) or observation.get("key") not in FACT_KEYS:
            raise ValueError("Filing fact key không được hỗ trợ")
        fact = dict(observation)
        key = fact["key"]
        if key in seen:
            raise ValueError(f"Filing fact bị trùng: {key}")
        seen.add(key)
        expected_unit = "VND/share" if key in {"eps", "diluted_eps"} else "shares" if key == "weighted_average_shares" else "VND"
        if fact.get("unit") != expected_unit:
            raise ValueError(f"Sai đơn vị {key}; cần {expected_unit}")
        value = fact.get("value")
        scale = fact.get("scale", 1)
        if isinstance(value, bool) or isinstance(scale, bool):
            raise ValueError("Boolean không phải số tài chính")
        if not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
            raise ValueError("Scale phải hữu hạn và dương")
        if value is not None:
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Giá trị {key} không hữu hạn")
            value_basis = fact.get("value_basis", "canonical")
            if value_basis not in {"canonical", "reported"}:
                raise ValueError("value_basis phải là canonical hoặc reported")
            converted = float(value) * float(scale) if value_basis == "reported" else float(value)
            if not math.isfinite(converted):
                raise ValueError(f"Tràn số sau quy đổi đơn vị {key}")
            fact["raw_value"] = fact.get("raw_value", value)
            fact["value"] = converted
            fact["original_value_basis"] = fact.get("original_value_basis", value_basis)
            fact["value_basis"] = "canonical"
        if status == "verified" and (isinstance(fact.get("page"), bool)
                                     or not isinstance(fact.get("page"), int) or fact["page"] < 1):
            raise ValueError(f"Filing verified cần trang nguồn cho {key}")
        fact["scale"] = float(scale)
        fact.setdefault("sign_convention", "canonical")
        if fact["sign_convention"] not in {"canonical", "outflow_negative", "expense_negative", "signed_adjustment"}:
            raise ValueError("sign_convention không được hỗ trợ")
        normalized.append(fact)
    item["facts"] = normalized
    return item


def import_filing(metadata: Path, directory: Path, *, original_document: Path | None = None) -> Path:
    document = original_document.read_bytes() if original_document else None
    if document is not None and len(document) > 50 * 1024 * 1024:
        raise ValueError("Original filing exceeds 50 MB")
    item = validate_filing(json.loads(metadata.read_text(encoding="utf-8")), document)
    payload = json.dumps(item, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
    version = hashlib.sha256(payload).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / version
    if final.exists():
        if (final / "filing.json").read_bytes() != payload:
            raise ValueError("Filing release identity collision")
        if document is not None and (final / "original.document").read_bytes() != document:
            raise ValueError("Filing original document integrity mismatch")
        return final
    stage = Path(tempfile.mkdtemp(prefix=".filing-", dir=directory))
    try:
        (stage / "filing.json").write_bytes(payload)
        if document is not None:
            (stage / "original.document").write_bytes(document)
        try:
            os.rename(stage, final)
        except FileExistsError:
            if (final / "filing.json").read_bytes() != payload:
                raise ValueError("Filing release identity collision")
            if document is not None and (final / "original.document").read_bytes() != document:
                raise ValueError("Filing original document integrity mismatch")
        return final
    finally:
        if stage.exists() and stage.resolve().is_relative_to(directory.resolve()):
            shutil.rmtree(stage)


def source_optional(**fields):
    return {key: value for key, value in fields.items() if key in Source.model_fields}


def load_filings(directory: Path, tickers: list[str], start: int, end: int, *, as_of: date | None = None,
                 period_type: str = "annual"):
    frames, sources = [], []
    if not directory.exists():
        return frames, sources
    for path in sorted(directory.glob("*/filing.json")):
        if path.parent.name.startswith(".filing-"):
            continue
        payload = path.read_bytes()
        version = hashlib.sha256(payload).hexdigest()
        if path.parent.name != version:
            raise ValueError("Immutable filing release identity mismatch; re-import instead of editing")
        document_path = path.parent / "original.document"
        document = document_path.read_bytes() if document_path.exists() else None
        item = validate_filing(json.loads(payload), document)
        if item["ticker"] not in tickers or not start <= item["fiscal_year"] <= end:
            continue
        if as_of and _date(item["published_on"], "published_on") > as_of:
            continue
        if item["period_type"] != period_type or item["verification_status"] == "quarantined":
            continue
        sid = "filing-" + version[:20]
        source = Source(id=sid, title=f"BCTC {item['ticker']} {item['fiscal_year']} ({item['consolidation']})",
                        url=item["report_url"], kind="user_supplied", retrieved_at=utcnow(),
                        period=f"{item['period_start']}/{item['period_end']}", sha256=item["original_sha256"],
                        note=f"Original SHA-256 preserved; verification={item['verification_status']}; release={version}",
                        **source_optional(published_at=item["published_at"], published_on=item["published_on"],
                                          publication_precision=item["publication_precision"], report_basis=item["consolidation"],
                                          period_start=item["period_start"], period_end=item["period_end"],
                                          period_type=item["period_type"], dataset_version=version,
                                          currency="VND", verification_status=item["verification_status"],
                                          mapping_version="2.0.0"))
        observations = []
        for fact in item["facts"]:
            key = fact["key"]
            statement = "balance_sheet" if key in {"total_assets", "current_assets", "current_liabilities", "total_liabilities", "equity", "equity_parent", "noncontrolling_interest"} else "cash_flow" if key in {"cfo", "capex", "depreciation"} else "income_statement"
            observations.append({"ticker": item["ticker"], "year": item["fiscal_year"], "statement": statement,
                                 "exchange": item.get("exchange", "unknown"), "item_code": fact.get("item_code", "filing_" + key),
                                 "item_name": fact.get("label", key), "metric_key": key, "value": fact["value"],
                                 "raw_value": fact.get("raw_value"), "unit": fact["unit"], "scale": fact["scale"],
                                 "sign_convention": fact["sign_convention"], "source_id": sid,
                                 "source_file": item["report_url"], "source_sheet": str(fact.get("page", "unknown")),
                                 "source_page": fact.get("page"), "original_sha256": item["original_sha256"],
                                 "dataset_version": version, "file_sha256": version, "period_start": item["period_start"],
                                 "period_end": item["period_end"], "period_type": item["period_type"],
                                 "published_at": item["published_at"], "published_on": item["published_on"],
                                 "publication_precision": item["publication_precision"], "report_basis": item["consolidation"],
                                 "verification_status": item["verification_status"], "filing_id": version})
        frames.append(pd.DataFrame(observations))
        sources.append(source)
    return frames, sources


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Import original-source financial filing observations")
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--original-document", type=Path)
    args = parser.parse_args()
    print(import_filing(args.metadata, args.directory, original_document=args.original_document))


if __name__ == "__main__":
    main()
