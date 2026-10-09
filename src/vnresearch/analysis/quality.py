"""Keep unverified observations visible as evidence, but exclude them from production calculations."""
from copy import deepcopy


def verified_financial_rows(rows: list[dict], require_verified: bool = True) -> list[dict]:
    result = deepcopy(rows)
    if not require_verified:
        return result
    for row in result:
        blocked = []
        metadata = row.setdefault("fact_metadata", {})
        for key, value in row["facts"].items():
            if value is None:
                continue
            fact = metadata.setdefault(key, {})
            if fact.get("verification_status") != "verified" or fact.get("status") == "quarantined":
                fact["observed_value"] = value
                fact["calculation_status"] = "blocked_unverified"
                row["facts"][key] = None
                blocked.append(key)
        if blocked:
            row.setdefault("quality_issues", []).append({
                "code": "UNVERIFIED_FACTS_EXCLUDED", "component": "financial", "severity": "warning",
                "message": f"Năm {row['year']}: {', '.join(blocked)} chưa được đối chiếu nguồn gốc; chỉ giữ trong bằng chứng, không dùng tính tỷ số/định giá.",
            })
    return result


def comparable_facts(current: dict, previous: dict, key: str) -> bool:
    current_meta = current.get("fact_metadata", {}).get(key, {})
    previous_meta = previous.get("fact_metadata", {}).get(key, {})
    for field in ["report_basis", "period_type", "unit"]:
        a, b = current_meta.get(field), previous_meta.get(field)
        if a and b and a != b:
            return False
    return True
