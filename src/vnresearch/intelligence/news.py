from datetime import date, datetime
from difflib import SequenceMatcher
import functools
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import urllib.parse

import pandas as pd

from vnresearch._vendor.dictionary import Dictionary
from vnresearch._vendor.matcher import GenericFuzzyMatcher
from vnresearch._vendor.news_scraper import MultiSourceNewsAggregator
from vnresearch._vendor.snippet_extractor import SnippetExtractor
from vnresearch.domain.models import Mode, NewsArticle, Section, Source, utcnow
from vnresearch.platform.settings import ASSETS

INJECTION_PATTERNS = [
    r"(?i)\b(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules|commands)\b",
    r"(?i)\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be)\b",
    r"(?i)\b(?:system\s*:\s*|human\s*:\s*|assistant\s*:\s*|<\|im_start\|>|<\|im_end\|>)",
    r"(?i)\b(?:bỏ\s+qua|hủy\s+bỏ)\s+(?:mọi\s+)?(?:chỉ\s+thị|lệnh|hướng\s+dẫn|quy\s+tắc)\s+(?:trước|ở\s+trên)\b",
    r"(?i)\b(?:hệ\s+thống\s*:\s*|người\s+dùng\s*:\s*)",
    r"(?i)\b(?:khuyến\s+nghị\s+mua\s+ngay\s+lập\s+tức|override\s+decision|bỏ\s+qua\s+rủi\s+ro)\b",
    r"(?i)\[(?:system|instruction|prompt)\b",
]


def sanitize_untrusted_text(text: str) -> tuple[str, list[str]]:
    """
    Mask một số mẫu chỉ thị đáng ngờ để hỗ trợ phân tích heuristic.

    Đây không phải ranh giới bảo mật. Luôn giữ nguồn ngoài là dữ liệu không tin cậy;
    bản gốc phải được bảo toàn riêng để truy vết và đối chiếu.
    """
    raw = str(text or "")
    detected: list[str] = []
    masked = list(raw)
    for pat in INJECTION_PATTERNS:
        for match in re.finditer(pat, raw):
            detected.append(match.group(0).strip())
            for index in range(match.start(), match.end()):
                if masked[index] not in "\r\n":
                    masked[index] = " "
    return "".join(masked), detected


def strict_article_date(value: str) -> date | None:
    value = str(value or "").strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
            return datetime.strptime(value, "%d/%m/%Y").date()
        if "T" in value or " " in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (ValueError, OverflowError):
        return None
    return None


@functools.lru_cache(maxsize=4)
def _load_company_names_map(path_text: str, modified_ns: int, size: int) -> dict[str, list[str]]:
    del modified_ns, size
    frame = pd.read_csv(path_text, usecols=["Mã CK", "Tên Doanh Nghiệp", "Tên thương hiệu / Viết tắt"],
                        dtype=str, keep_default_na=False)
    result: dict[str, list[str]] = {}
    for _, row in frame.iterrows():
        ticker = str(row["Mã CK"]).strip().upper()
        if not ticker:
            continue
        aliases = [ticker]
        for column in ("Tên Doanh Nghiệp", "Tên thương hiệu / Viết tắt"):
            alias = str(row[column]).strip()
            if alias and alias.casefold() not in {item.casefold() for item in aliases}:
                aliases.append(alias)
        result[ticker] = aliases
    return result


def load_company_names_map() -> dict[str, list[str]]:
    path = ASSETS / "companies.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Thiếu danh mục doanh nghiệp: {path.name}")
    stat = path.stat()
    return _load_company_names_map(str(path), stat.st_mtime_ns, stat.st_size)


def _normalize_company_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    normalized = "".join(char for char in unicodedata.normalize("NFD", normalized)
                         if unicodedata.category(char) != "Mn")
    normalized = normalized.replace("đ", "d")
    return re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()


def _has_phrase(text: str, phrase: str) -> bool:
    normalized_text = f" {_normalize_company_text(text)} "
    normalized_phrase = _normalize_company_text(phrase)
    return bool(normalized_phrase and f" {normalized_phrase} " in normalized_text)


def verify_article_ticker(ticker: str, title: str, text: str) -> bool:
    """
    Xác nhận bài viết có thực sự đề cập đến mã cổ phiếu (hoặc tên doanh nghiệp) hay không,
    ngăn ngừa tình trạng tài liệu sai ticker / gán sai doanh nghiệp.
    """
    ticker_clean = str(ticker or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{3,6}", ticker_clean):
        return False
    pattern = rf"\b{re.escape(ticker_clean)}\b"
    if re.search(pattern, title.upper()) or re.search(pattern, text.upper()):
        return True

    names_map = load_company_names_map()
    aliases = names_map.get(ticker_clean, [])[1:]
    source_text = f"{title}\n{text}"
    for alias in aliases:
        if len(_normalize_company_text(alias).replace(" ", "")) >= 4 and _has_phrase(source_text, alias):
            return True
    return False


def normalize_url(url: str) -> str:
    value = str(url or "").strip()
    parsed = urllib.parse.urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme == "urn" and value.lower().startswith("urn:demo:"):
        return value.rstrip("/")
    if scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL phải là HTTP(S) có host, không chứa thông tin xác thực")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL có cổng không hợp lệ") from exc
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = f"[{host}]"
    if parsed.netloc.endswith(":"):
        raise ValueError("URL có cổng không hợp lệ")
    netloc = f"{host}:{port}" if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)) else host
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [(key, val) for key, val in pairs if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
    query = urllib.parse.urlencode(sorted(filtered))
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))


def _article_fingerprint(item: dict, published: date) -> str:
    payload = {
        "ticker": str(item.get("ticker", "")).strip().upper(),
        "title": str(item.get("title", "")).strip(),
        "text": str(item.get("text", "")).strip(),
        "url": str(item.get("url", "")).strip(),
        "published_at": published.isoformat(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_news(ticker: str, as_of: date, mode: Mode, limit: int, input_path: Path | None = None):
    ticker = ticker.strip().upper()
    limit = min(max(1, limit), 20)

    if input_path:
        frame = pd.read_csv(input_path).fillna("")
        required = {"ticker", "title", "text", "url", "published_at"}
        if not required.issubset(frame.columns):
            raise ValueError("CSV tin tức thiếu cột bắt buộc: ticker, title, text, url, published_at")
        raw = frame.loc[frame.ticker.astype(str).str.strip().str.upper() == ticker].to_dict("records")
        kind = "user_supplied"
    elif mode == Mode.LIVE:
        raw = MultiSourceNewsAggregator().crawl_ticker(ticker, ["cafef", "vnexpress"],
                                                       target_articles=limit, year_from=as_of.year - 1,
                                                       year_to=as_of.year)
        kind = "live"
    elif mode == Mode.DEMO:
        raw = [{
            "ticker": ticker,
            "title": f"Minh họa: {ticker} và kế hoạch công nghệ",
            "text": f"Đây là văn bản giả lập về {ticker}. Chuyển đổi số và quản trị rủi ro là các chủ đề dùng để kiểm tra khai phá văn bản. Nội dung này không mô tả sự kiện thật của doanh nghiệp.",
            "url": "urn:demo:news",
            "published_at": str(as_of)
        }]
        kind = "synthetic"
    else:
        raw, kind = [], "snapshot"

    matcher = GenericFuzzyMatcher(Dictionary.from_yaml(ASSETS / "investment_dictionary.yaml"), threshold=95)
    extractor = SnippetExtractor()

    article_sources: list[tuple[NewsArticle, Source]] = []
    seen_titles: list[str] = []
    seen_urls: set[str] = set()

    rejected_date = 0
    rejected_ticker = 0
    rejected_duplicate = 0
    rejected_invalid = 0
    sanitized_count = 0

    raw = list(raw or [])
    raw.sort(
        key=lambda item: strict_article_date(item.get("published_at", item.get("published_date", ""))) or date.min,
        reverse=True,
    )

    for item in raw:
        published = strict_article_date(item.get("published_at", item.get("published_date", "")))
        title = str(item.get("title", ""))
        text = str(item.get("text", ""))
        url = str(item.get("url", "")).strip()

        # 1. Kiểm tra ngày công bố chặt chẽ (trong 365 ngày tính đến as_of)
        if not published or published > as_of or (as_of - published).days > 365 or not title.strip() or not text.strip():
            rejected_date += 1
            continue
        if len(title) > 300 or len(text) > 100000 or len(url) > 2000:
            rejected_invalid += 1
            continue

        # 2. Kiểm tra định dạng URL
        try:
            norm_url = normalize_url(url)
        except ValueError:
            rejected_invalid += 1
            continue

        # 3. Xác thực đúng doanh nghiệp (tránh tài liệu sai ticker)
        if not verify_article_ticker(ticker, title, text):
            rejected_ticker += 1
            continue

        # 4. Chống trùng lặp URL và Tiêu đề
        if norm_url in seen_urls:
            rejected_duplicate += 1
            continue

        cleaned_title = re.sub(r"\W+", " ", title.lower()).strip()
        if any(SequenceMatcher(None, cleaned_title, old).ratio() > 0.85 for old in seen_titles):
            rejected_duplicate += 1
            continue

        # 5. Vệ sinh Prompt Injection trước khi chuyển văn bản cho AI (TV5)
        _, inj_title = sanitize_untrusted_text(title)
        masked_text, inj_text = sanitize_untrusted_text(text)
        if inj_title or inj_text:
            sanitized_count += 1

        seen_urls.add(norm_url)
        seen_titles.append(cleaned_title)

        fingerprint = _article_fingerprint(item, published)
        sid = "news-" + fingerprint[:16]
        matches = matcher.search(masked_text, use_fuzzy=False)
        snippets = [
            extractor.extract_sentence_context(text, m["position"], len(m.get("keyword_found", "")))
            for m in matches[:3]
        ]

        source_note = (
            "sha256 băm các trường bài viết đã trích; không phải byte HTML gốc. "
            "Chủ đề chỉ dựa trên từ khóa, không xác nhận sentiment hoặc khuyến nghị."
        )
        if inj_title or inj_text:
            source_note += " Có mẫu giống chỉ thị; nội dung gốc được giữ nguyên và phải xem là dữ liệu không tin cậy."
        source = Source(
            id=sid,
            title=title,
            kind=kind,
            url=url,
            period=str(published),
            retrieved_at=utcnow(),
            sha256=fingerprint,
            published_on=published,
            publication_precision="day",
            note=source_note,
        )
        article = NewsArticle(
            title=title,
            text=text,
            url=url,
            published_at=published,
            ticker=ticker,
            source_id=sid,
            themes=sorted({m.get("category", "default") for m in matches}),
            snippets=snippets,
        )
        article_sources.append((article, source))

    article_sources.sort(key=lambda pair: (pair[0].published_at, pair[1].id), reverse=True)
    article_sources = article_sources[:limit]
    articles = [article for article, _ in article_sources]
    sources = [source for _, source in article_sources]

    summary_parts = [f"{len(articles)} bài có ngày hợp lệ trong 365 ngày."]
    rejected_reasons = []
    if rejected_date > 0:
        rejected_reasons.append(f"{rejected_date} bài sai/quá hạn ngày")
    if rejected_ticker > 0:
        rejected_reasons.append(f"{rejected_ticker} bài sai doanh nghiệp")
    if rejected_duplicate > 0:
        rejected_reasons.append(f"{rejected_duplicate} bài trùng lặp")
    if rejected_invalid > 0:
        rejected_reasons.append(f"{rejected_invalid} bài sai URL hoặc vượt giới hạn")
    if rejected_reasons:
        summary_parts.append(f"Đã loại bỏ: {', '.join(rejected_reasons)}.")
    if sanitized_count > 0:
        summary_parts.append(
            f"Có mẫu giống chỉ thị trong {sanitized_count} bài; bản gốc được giữ nguyên và nguồn vẫn không đáng tin cậy."
        )

    return articles, sources, Section(
        title="Tin tức và bằng chứng",
        status="ok" if articles else "unavailable",
        summary=" ".join(summary_parts),
        rows=[{"Ngày": str(a.published_at), "Tiêu đề": a.title, "Chủ đề": ", ".join(a.themes)} for a in articles],
        source_ids=[s.id for s in sources]
    )
