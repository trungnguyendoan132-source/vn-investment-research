from datetime import date, datetime
from difflib import SequenceMatcher
import hashlib
from pathlib import Path
import re

import pandas as pd

from vnresearch._vendor.dictionary import Dictionary
from vnresearch._vendor.matcher import GenericFuzzyMatcher
from vnresearch._vendor.news_scraper import MultiSourceNewsAggregator
from vnresearch._vendor.snippet_extractor import SnippetExtractor
from vnresearch.domain.models import Mode, NewsArticle, Section, Source, utcnow
from vnresearch.platform.settings import ASSETS


def strict_article_date(value: str) -> date | None:
    value = str(value or "").strip()
    match = re.search(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", value)
    try:
        if match:
            return date.fromisoformat(match.group(1))
        match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", value)
        return datetime.strptime(match.group(1), "%d/%m/%Y").date() if match else None
    except ValueError:
        return None


def load_news(ticker: str, as_of: date, mode: Mode, limit: int, input_path: Path | None = None):
    if input_path:
        frame = pd.read_csv(input_path).fillna("")
        required = {"ticker", "title", "text", "url", "published_at"}
        if not required.issubset(frame.columns):
            raise ValueError("CSV tin tức thiếu cột bắt buộc")
        raw = frame.loc[frame.ticker.str.upper() == ticker].to_dict("records")
        kind = "user_supplied"
    elif mode == Mode.LIVE:
        raw = MultiSourceNewsAggregator().crawl_ticker(ticker, ["cafef", "vnexpress"],
                                                       target_articles=limit, year_from=as_of.year - 1,
                                                       year_to=as_of.year)
        kind = "live"
    elif mode == Mode.DEMO:
        raw = [{"ticker": ticker, "title": f"Minh họa: {ticker} và kế hoạch công nghệ",
                "text": f"Đây là văn bản giả lập về {ticker}. Chuyển đổi số và quản trị rủi ro là các chủ đề dùng để kiểm tra khai phá văn bản. Nội dung này không mô tả sự kiện thật của doanh nghiệp.",
                "url": "urn:demo:news", "published_at": str(as_of)}]
        kind = "synthetic"
    else:
        raw, kind = [], "snapshot"
    matcher = GenericFuzzyMatcher(Dictionary.from_yaml(ASSETS / "investment_dictionary.yaml"), threshold=95)
    extractor = SnippetExtractor()
    articles, sources, seen = [], [], []
    rejected = 0
    for item in raw:
        published = strict_article_date(item.get("published_at", item.get("published_date", "")))
        title, text, url = str(item.get("title", "")), str(item.get("text", "")), str(item.get("url", ""))
        if not published or published > as_of or (as_of - published).days > 365 or not title or not text:
            rejected += 1
            continue
        if not url.startswith(("https://", "http://", "urn:demo:")):
            raise ValueError("Tin tức phải có URL nguồn hợp lệ")
        cleaned = re.sub(r"\W+", " ", title.lower()).strip()
        if any(SequenceMatcher(None, cleaned, old).ratio() > 0.85 for old in seen):
            continue
        seen.append(cleaned)
        sid = "news-" + hashlib.sha256((url + title).encode()).hexdigest()[:16]
        matches = matcher.search(text, use_fuzzy=False)
        snippets = [extractor.extract_sentence_context(text, m["position"], len(m.get("keyword_found", ""))) for m in matches[:3]]
        sources.append(Source(id=sid, title=title, kind=kind, url=url, period=str(published), retrieved_at=utcnow(),
                              note="Nhận diện chủ đề bằng từ khóa; không suy ra tâm lý tích cực/tiêu cực hay khuyến nghị từ tần suất từ."))
        articles.append(NewsArticle(title=title, text=text, url=url, published_at=published, ticker=ticker,
                                    source_id=sid, themes=sorted({m.get("category", "default") for m in matches}), snippets=snippets))
        if len(articles) >= limit:
            break
    articles.sort(key=lambda a: a.published_at, reverse=True)
    return articles, sources, Section(title="Tin tức và bằng chứng", status="ok" if articles else "unavailable",
                                      summary=f"{len(articles)} bài có ngày hợp lệ trong 365 ngày; {rejected} bài thiếu ngày, quá cũ hoặc sau ngày chốt bị loại.",
                                      rows=[{"Ngày": str(a.published_at), "Tiêu đề": a.title, "Chủ đề": ", ".join(a.themes)} for a in articles],
                                      source_ids=[s.id for s in sources])
