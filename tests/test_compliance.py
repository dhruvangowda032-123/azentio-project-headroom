import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from covenants.compliance import check
from covenants.extraction import extract
from covenants.providers import FakeProvider
from covenants.schemas import CheckInput
from covenants.storage import Store

ROOT = Path(__file__).resolve().parents[1]


def run_check(extraction, financials, tmp_path, period="2026-03-31", **kwargs):
    return check(extraction, CheckInput(period_end=period, financials=financials), Store(tmp_path), **kwargs)


def leverage(result):
    return next(r for r in result["results"] if r["type"] == "LEVERAGE")


@pytest.mark.parametrize("actual,status", [(3.0, "PASS"), (3.6, "PASS"), (3.8, "NEAR_BREACH"),
                                          (4.0, "NEAR_BREACH"), (4.01, "BREACH")])
def test_lte_boundaries(extraction, financials, tmp_path, actual, status):
    financials["net_debt"] = Decimal(str(actual)) * financials["ltm_ebitda"]
    result = leverage(run_check(extraction, financials, tmp_path))
    assert result["status"] == status
    assert result["computed_value"] == actual


@pytest.mark.parametrize("actual,status", [(2.99, "BREACH"), (3.0, "NEAR_BREACH"),
                                          (3.1, "NEAR_BREACH"), (3.3, "PASS"), (4.0, "PASS")])
def test_gte_boundaries(extraction, financials, tmp_path, actual, status):
    financials["ltm_ebitda"] = Decimal(str(actual)) * financials["interest_expense"]
    result = run_check(extraction, financials, tmp_path)
    interest = next(r for r in result["results"] if r["type"] == "INTEREST_COVER")
    assert interest["status"] == status


@pytest.mark.parametrize("period,limit", [("2026-06-30", 4.0), ("2026-07-01", 3.5), ("2026-12-31", 3.5)])
def test_step_down_date_selection(extraction, financials, tmp_path, period, limit):
    result = run_check(extraction, financials, tmp_path, period)
    assert leverage(result)["applicable_threshold"] == limit
    assert sum(r["type"] == "LEVERAGE" for r in result["results"]) == 1


@pytest.mark.parametrize("period,limit,clause", [("2026-06-30", 4.0, "22.1"), ("2026-07-01", 3.0, "23.1")])
def test_amendment_overrides_prior_threshold(financials, tmp_path, period, limit, clause):
    result = extract((ROOT / "data/agreements/loan_03.txt").read_text(), FakeProvider())
    row = leverage(run_check(result, financials, tmp_path, period))
    assert row["applicable_threshold"] == limit
    assert row["clause_id"] == clause


@pytest.mark.parametrize("denominator", [0, -1])
def test_zero_or_negative_ebitda_needs_review(extraction, financials, tmp_path, denominator):
    financials["ltm_ebitda"] = denominator
    result = leverage(run_check(extraction, financials, tmp_path))
    assert result["status"] == "NEEDS_REVIEW"
    assert "denominator" in result["reason"]


@pytest.mark.parametrize("field", ["net_debt", "ltm_ebitda"])
def test_missing_input_needs_review(extraction, financials, tmp_path, field):
    del financials[field]
    row = leverage(run_check(extraction, financials, tmp_path))
    assert row["status"] == "NEEDS_REVIEW"
    assert field in row["reason"]


@pytest.mark.parametrize("change", ["unverified", "low_confidence", "overlap", "unit", "other"])
def test_uncertainty_never_passes(extraction, financials, tmp_path, change):
    c = extraction.covenants[0]
    if change == "unverified":
        c.status = "unverified"
    elif change == "low_confidence":
        c.confidence = 0.4
    elif change == "overlap":
        extraction.covenants.append(c.model_copy(deep=True))
    elif change == "unit":
        c.unit = "percent"
    else:
        c.type = "OTHER"
    result = run_check(extraction, financials, tmp_path)
    assert result["overall_status"] == "NEEDS_REVIEW"
    assert any(r["status"] == "NEEDS_REVIEW" for r in result["results"])


def test_no_applicable_threshold_needs_review(extraction, financials, tmp_path):
    result = run_check(extraction, financials, tmp_path, "2027-03-31")
    assert result["overall_status"] == "NEEDS_REVIEW"
    assert all(r["applicable_threshold"] is None for r in result["results"])


def test_empty_extraction_never_all_clear(extraction, financials, tmp_path):
    extraction.covenants = []
    assert run_check(extraction, financials, tmp_path)["overall_status"] == "NEEDS_REVIEW"


def test_configurable_cutoffs(extraction, financials, tmp_path):
    financials["net_debt"] = 380_000_000
    result = run_check(extraction, financials, tmp_path, near_breach_percent=2)
    assert leverage(result)["status"] == "PASS"
    result = run_check(extraction, financials, tmp_path, confidence_cutoff=0.99)
    assert leverage(result)["status"] == "NEEDS_REVIEW"


def test_two_checks_append_immutable_audit(extraction, financials, tmp_path):
    first = run_check(extraction, financials, tmp_path)
    second = run_check(extraction, financials, tmp_path)
    assert first["input_hash"] == second["input_hash"]
    with sqlite3.connect(tmp_path / "headroom.sqlite3") as db:
        rows = db.execute("SELECT agreement_id,period,input_hash,results,extraction_meta,timestamp FROM audit").fetchall()
        assert len(rows) == 2
        assert rows[0][0] == extraction.agreement_id
        assert len(rows[0][2]) == 64
        assert json.loads(rows[0][3])[0]["quote"]
        assert json.loads(rows[0][4])["prompt_version"]
        assert rows[0][5].endswith("+00:00")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM audit")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("UPDATE audit SET period='2020-01-01'")


def test_seeded_borrower_four_quarters(extraction, tmp_path):
    data = json.loads((ROOT / "data/financials/loan_01.json").read_text())
    results = [leverage(check(extraction, CheckInput.model_validate(row), Store(tmp_path))) for row in data]
    assert [row["status"] for row in results] == ["PASS", "PASS", "BREACH", "PASS"]
    assert results[2]["computed_value"] == 4.5
    assert results[2]["applicable_threshold"] == 3.5
    assert results[2]["headroom_percent"] == pytest.approx(-28.5714285714)


def test_compliance_never_calls_provider(extraction, financials, tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("LLM called in compliance path")
    monkeypatch.setattr(FakeProvider, "generate", forbidden)
    assert run_check(extraction, financials, tmp_path)["overall_status"] == "PASS"


@pytest.mark.parametrize("field,kind", [("interest_expense", "INTEREST_COVER"),
                                       ("debt_service", "DSCR"), ("current_liabilities", "CURRENT_RATIO")])
@pytest.mark.parametrize("value", [0, -100])
def test_all_ratio_denominators_guarded(extraction, financials, tmp_path, field, kind, value):
    financials[field] = value
    result = run_check(extraction, financials, tmp_path)
    assert next(r for r in result["results"] if r["type"] == kind)["status"] == "NEEDS_REVIEW"


def test_unverified_amendment_cannot_leave_original_passing(financials, tmp_path):
    extraction = extract((ROOT / "data/agreements/loan_03.txt").read_text(), FakeProvider())
    amendment = next(c for c in extraction.covenants if c.clause_id == "23.1")
    amendment.status = "unverified"
    amendment.status_reason = "citation could not be checked"
    assert run_check(extraction, financials, tmp_path, "2026-09-30")["overall_status"] == "NEEDS_REVIEW"


