from datetime import date

import pytest
import requests

from vnresearch.analysis.pipeline import analyze
from vnresearch.domain.models import AnalysisRequest


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("External HTTP disabled in tests")
    monkeypatch.setattr(requests.sessions.Session, "request", fail)


@pytest.fixture(scope="session")
def demo_report():
    return analyze(AnalysisRequest(ticker="FPT", mode="demo", as_of=date(2026, 10, 9), start_year=2022, end_year=2025))
