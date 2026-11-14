"""Every test is offline; no API key is needed or loaded from a developer's environment."""

from pathlib import Path

import pytest

from covenants.extraction import extract
from covenants.providers import FakeProvider

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_secrets(monkeypatch):
    for key in ("GROQ_API_KEY", "HEADROOM_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def text():
    return (ROOT / "data/agreements/loan_01.txt").read_text()


@pytest.fixture
def extraction(text):
    return extract(text, FakeProvider())


@pytest.fixture
def financials():
    return dict(net_debt=250_000_000, ltm_ebitda=100_000_000, interest_expense=20_000_000,
                cash_available_for_debt_service=60_000_000, debt_service=40_000_000,
                tangible_net_worth=80_000_000, current_assets=200_000_000,
                current_liabilities=100_000_000, capex=10_000_000)

