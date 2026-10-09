from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from vnresearch.domain.models import AnalysisRequest, ValuationAssumptions
from vnresearch.intelligence.news import strict_article_date


def test_symbol_normalization():
    assert AnalysisRequest(ticker=" fpt ").ticker == "FPT"


@pytest.mark.parametrize("arguments", [
    {"ticker": "../secret"}, {"ticker": "FPT", "start_year": 2025, "end_year": 2024},
    {"ticker": "FPT", "sections": []}, {"ticker": "FPT", "sections": ["macro", "macro"]},
    {"ticker": "FPT", "as_of": date.today() + timedelta(days=1)},
    {"ticker": "FPT", "datasets": {"prices": "../../private"}},
])
def test_invalid_requests_rejected(arguments):
    with pytest.raises(ValidationError):
        AnalysisRequest(**arguments)


def test_share_count_requires_source():
    with pytest.raises(ValidationError):
        ValuationAssumptions(shares_outstanding=100)


def test_news_year_is_not_publication_date():
    assert strict_article_date("2024") is None
    assert strict_article_date("2024-02-30") is None
    assert strict_article_date("2024-03-01T12:00:00Z") == date(2024, 3, 1)
