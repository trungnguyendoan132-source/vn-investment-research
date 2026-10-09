import hashlib
from pathlib import Path
import re
from typing import Any

import pymupdf

from vnresearch._vendor.bctn_validator import audit_bctn_file
from vnresearch._vendor.dictionary import Dictionary
from vnresearch._vendor.matcher import GenericFuzzyMatcher
from vnresearch._vendor.snippet_extractor import SnippetExtractor
from vnresearch.intelligence.news import load_company_names_map, sanitize_untrusted_text, strict_article_date
from vnresearch.platform.settings import ASSETS

KNOWN_SECURITIES_FIRMS = [
    "SSI", "VNDIRECT", "HSC", "VIETCAP", "VCSC", "MIRAE ASSET", "MBS", "VPS",
    "BVSC", "SHS", "KBSV", "ACBS", "TPS", "FPTS", "VCBS", "BSC"
]


def detect_document_metadata(document: pymupdf.Document, first_pages_text: str) -> dict[str, Any]:
    """
    Trích thông tin có căn cứ trong trang đầu; metadata PDF không được coi là ngày phát hành.
    """
    meta = document.metadata or {}
    issuer_candidates = sorted({
        firm for firm in KNOWN_SECURITIES_FIRMS
        if re.search(rf"(?<![A-Z0-9]){re.escape(firm)}(?![A-Z0-9])", first_pages_text, re.IGNORECASE)
    })
    firm_pattern = "|".join(re.escape(firm) for firm in KNOWN_SECURITIES_FIRMS)
    issuer_match = re.search(
        rf"(?i)(?:đơn vị(?:\s+phân tích|\s+phát hành)?|công ty chứng khoán|ctck|issuer|research\s+provider)"
        rf"\s*[:\-]?\s*({firm_pattern})\b",
        first_pages_text,
    )
    issuer = re.sub(r"\s+", " ", issuer_match.group(0)).strip() if issuer_match else None

    date_match = re.search(
        r"(?i)(?:ngày(?:\s+công\s+bố|\s+phát\s+hành)?|published(?:\s+on)?|date)"
        r"\s*[:\-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})",
        first_pages_text,
    )
    doc_date = strict_article_date(date_match.group(1)) if date_match else None

    target_match = re.search(
        r"(?i)(?:cổ\s+phiếu|mã\s+ck|mã\s+chứng\s+khoán|ticker|doanh\s+nghiệp)"
        r"\s*[:\-]?\s*([A-Z0-9]{3,6})\b",
        first_pages_text,
    )
    company_map = load_company_names_map()
    candidate = target_match.group(1).upper() if target_match else None
    detected_ticker = candidate if candidate in company_map else None
    ticker_candidates = sorted(
        set(re.findall(r"(?<![A-Z0-9])[A-Z0-9]{3,6}(?![A-Z0-9])", first_pages_text)) & set(company_map)
    )

    return {
        "issuer": issuer,
        "issuer_candidates": issuer_candidates,
        "issuer_confidence": "explicit_label" if issuer else "unknown",
        "issuer_evidence": issuer_match.group(0) if issuer_match else None,
        "date": doc_date.isoformat() if doc_date else None,
        "date_basis": "explicit_text_label" if doc_date else "unknown",
        "ticker": detected_ticker,
        "ticker_candidates": ticker_candidates,
        "ticker_basis": "explicit_context" if detected_ticker else "unknown",
        "pdf_author_metadata": str(meta.get("author", "")).strip() or None,
        "pdf_creation_date_metadata": str(meta.get("creationDate", "")).strip() or None,
    }


def ocr_page_fallback(page: pymupdf.Page) -> str:
    """
    Cơ chế OCR dự phòng cho các trang scan không có text layer.
    Sử dụng engine OCR tích hợp của PyMuPDF nếu có môi trường hỗ trợ.
    """
    try:
        tp = page.get_textpage_ocr(language="vie", dpi=150, full=True)
        return tp.extractText()
    except Exception:
        # Nếu máy tính chưa cài đặt Tesseract/tessdata ngôn ngữ, trả về rỗng để đánh dấu trang scan
        return ""


def inspect_document(path: Path, annual_report: bool = False) -> dict[str, Any]:
    """
    Phân tích và trích xuất bằng chứng từ tài liệu PDF (BCTN, BCTC hoặc Báo cáo CTCK).
    Đảm bảo:
    - Lưu tổ chức phát hành, ngày, ticker, số trang và SHA-256
    - Đánh dấu và xử lý trang scan bằng OCR
    - Trích xuất bằng chứng theo chủ đề (catalyst, rủi ro, chiến lược, sự kiện vốn)
    - Gắn cờ mẫu giống chỉ thị; bảo toàn nguyên văn bằng chứng
    """
    if path.suffix.lower() != ".pdf":
        raise ValueError("Chỉ nhận tài liệu PDF")
    if not path.is_file() or path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Tệp không tồn tại hoặc lớn hơn giới hạn 50 MB")

    file_bytes = path.read_bytes()
    if len(file_bytes) > 50 * 1024 * 1024:
        raise ValueError("Tệp vượt giới hạn 50 MB")
    annual_validation = audit_bctn_file(file_bytes) if annual_report else None
    matcher = GenericFuzzyMatcher(Dictionary.from_yaml(ASSETS / "investment_dictionary.yaml"), threshold=95)
    extractor = SnippetExtractor()

    snippets: list[dict[str, Any]] = []
    scanned: list[int] = []
    ocr_recovered: list[int] = []
    first_pages_buffer: list[str] = []

    evidence_by_theme: dict[str, list[dict[str, Any]]] = {
        "catalyst": [],
        "risks": [],
        "strategy": [],
        "capital_events": [],
        "growth": [],
        "other": []
    }

    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    with pymupdf.open(stream=file_bytes, filetype="pdf") as document:
        if len(document) > 1000:
            raise ValueError("Tài liệu vượt giới hạn 1.000 trang")

        pages = len(document)

        for index, page in enumerate(document):
            page_num = index + 1
            text = page.get_text()

            if len(text.strip()) < 40:
                # Trang có khả năng là bản scan ảnh
                recovered_text = ocr_page_fallback(page)
                if len(recovered_text.strip()) >= 40:
                    text = recovered_text
                    ocr_recovered.append(page_num)
                else:
                    scanned.append(page_num)
                    continue

            if index < 3:
                first_pages_buffer.append(text)

            # Dùng bản mask cùng độ dài để vị trí trích đoạn khớp với văn bản gốc.
            masked_text, detected_instructions = sanitize_untrusted_text(text)

            matches = matcher.search(masked_text, use_fuzzy=False)
            for match in matches[:20]:
                category = match.get("category", "other")
                keyword = match.get("keyword_found", "")
                context = extractor.extract_sentence_context(text, match["position"], len(keyword))

                item = {
                    "page": page_num,
                    "category": category,
                    "keyword": keyword,
                    "context": context,
                    "untrusted_instruction_pattern_detected": bool(detected_instructions),
                }
                snippets.append(item)
                if category in evidence_by_theme:
                    evidence_by_theme[category].append(item)
                else:
                    evidence_by_theme["other"].append(item)

        metadata = detect_document_metadata(document, "\n".join(first_pages_buffer))

    return {
        "filename": path.name,
        "sha256": sha256_hash,
        "pages": pages,
        "metadata": metadata,
        "annual_validation": annual_validation,
        "snippets": snippets,
        "evidence_by_theme": evidence_by_theme,
        "requires_ocr_pages": scanned,
        "ocr_recovered_pages": ocr_recovered,
        "status": "partial" if scanned or ocr_recovered else "complete",
        "note": (
            "Trang scan chưa đọc được được liệt kê trong requires_ocr_pages; không coi text trống là không có thông tin. "
            "Trang OCR đã trích vẫn cần đối chiếu thủ công. Mẫu chỉ thị được gắn cờ heuristic, không phải bảo đảm an toàn."
        )
    }
