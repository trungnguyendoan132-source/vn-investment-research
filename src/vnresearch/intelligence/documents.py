import hashlib
from pathlib import Path

import pymupdf

from vnresearch._vendor.bctn_validator import audit_bctn_file
from vnresearch._vendor.dictionary import Dictionary
from vnresearch._vendor.matcher import GenericFuzzyMatcher
from vnresearch._vendor.snippet_extractor import SnippetExtractor
from vnresearch.platform.settings import ASSETS


def inspect_document(path: Path, annual_report: bool = False) -> dict:
    if path.suffix.lower() != ".pdf":
        raise ValueError("Chỉ nhận tài liệu PDF")
    if not path.is_file() or path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Tệp không tồn tại hoặc lớn hơn giới hạn 50 MB")
    annual_validation = audit_bctn_file(path) if annual_report else None
    matcher = GenericFuzzyMatcher(Dictionary.from_yaml(ASSETS / "investment_dictionary.yaml"), threshold=95)
    snippets, scanned = [], []
    with pymupdf.open(path) as document:
        if len(document) > 1000:
            raise ValueError("Tài liệu vượt giới hạn 1.000 trang")
        for index, page in enumerate(document):
            text = page.get_text()
            if len(text.strip()) < 40:
                scanned.append(index + 1)
                continue
            for match in matcher.search(text, use_fuzzy=False)[:20]:
                snippets.append({"page": index + 1, "keyword": match.get("keyword_found", ""),
                                 "context": SnippetExtractor().extract_sentence_context(text, match["position"], len(match.get("keyword_found", "")))})
        pages = len(document)
    return {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pages": pages, "annual_validation": annual_validation, "snippets": snippets,
            "requires_ocr_pages": scanned, "status": "partial" if scanned else "complete",
            "note": "Trang scan được đánh dấu cần OCR; không coi text trống là tài liệu không có thông tin."}
