import json
import shutil
from pathlib import Path

import pytest

from covenants.evaluation import compare, cost_estimate, evaluate, score
from covenants.providers import FakeProvider, ReplayProvider, RulesProvider

ROOT = Path(__file__).resolve().parents[1]


def test_exact_metrics_known_answer():
    base = dict(agreement="a", type="LEVERAGE", operator="LTE", threshold=4, unit="ratio",
                effective_from="2026-01-01", effective_to="2026-12-31", status="verified")
    gold = [{**base, "clause_id": str(i)} for i in range(3)]
    predicted = [gold[0], {**gold[1], "threshold": 9}]
    result = score(predicted, gold)
    assert result["precision"] == 0.5
    assert result["recall"] == 1 / 3
    assert result["f1"] == 0.4
    assert result["per_field_accuracy"]["threshold"] == 0.5
    assert result["per_field_accuracy"]["operator"] == 1.0


def test_duplicate_predictions_cannot_inflate_score():
    base = dict(agreement="a", type="LEVERAGE", clause_id="22.1", operator="LTE", threshold=4,
                unit="ratio", effective_from="2026-01-01", effective_to="2026-12-31", status="verified")
    result = score([base, base], [base])
    assert result["precision"] == 0.5
    assert result["recall"] == 1


def test_empty_metrics_are_defined():
    result = score([], [])
    assert result["f1"] == 0
    assert result["unverified_rate"] == 0


def test_numeric_distractors_and_date_accuracy(extraction):
    c = extraction.covenants[0].model_dump(mode="json")
    prediction = {**c, "agreement": "a"}
    gold = [{**prediction, "effective_to": "2026-06-29"},
            {"agreement": "a", "clause_id": "30.1", "kind": "negative"}]
    result = score([prediction, {**prediction, "clause_id": "30.1"}], gold)
    assert result["distractor_false_positives"] == 1
    assert result["per_field_accuracy"]["effective_to"] == 0


def test_corpus_counts_hard_cases_and_label_quotes():
    agreements = sorted((ROOT / "data/agreements").glob("*.txt"))
    assert len(agreements) >= 6
    labels = [json.loads(row) for row in (ROOT / "data/golden/covenants.jsonl").read_text().splitlines()]
    positives = [row for row in labels if row["kind"] == "positive"]
    assert len(positives) >= 30
    tags = {tag for row in labels for tag in row["tags"]}
    assert {"step_down", "amendment_override", "minimum_wording", "maximum_wording", "cross_reference", "numeric_distractor"} <= tags
    for path in agreements:
        records = [row for row in labels if row["agreement"] == path.stem]
        assert sum(row["kind"] == "positive" for row in records) >= 3
        assert sum(row["kind"] == "negative" for row in records) >= 2
        for row in records:
            if row["kind"] == "positive":
                assert row["quote"] in path.read_text()


def test_fake_and_rules_metrics_are_distinct():
    fake = evaluate(FakeProvider(), ROOT)
    baseline = evaluate(RulesProvider(), ROOT)
    assert fake["metrics"]["recall"] == 1
    assert 0 < baseline["metrics"]["recall"] < fake["metrics"]["recall"]
    assert fake["metrics"]["distractor_false_positives"] == 0


def test_record_and_replay_reproduce_quality_and_usage(tmp_path):
    path = tmp_path / "fake"
    original = evaluate(ReplayProvider(path, FakeProvider()), ROOT)
    replayed = evaluate(ReplayProvider(path), ROOT)
    assert original["metrics"] == replayed["metrics"]
    for key in ("input_tokens", "output_tokens", "mean_latency_ms", "max_latency_ms"):
        assert original[key] == replayed[key]
    assert json.loads((path / "manifest.json").read_text())["kind"] == "deterministic-baseline"


def test_compare_report_and_offline_replay(tmp_path, monkeypatch):
    for folder in ("data", "config"):
        shutil.copytree(ROOT / folder, tmp_path / folder)
    monkeypatch.chdir(tmp_path)
    original = compare(["rules", "fake"], tmp_path, record=True)
    replayed = compare(["replay:rules", "replay:fake"], tmp_path)
    assert [r["metrics"] for r in original] == [r["metrics"] for r in replayed]
    report = (tmp_path / "reports/comparison.md").read_text()
    assert "deterministic baselines" in report
    assert "effective_from" in report
    assert all(r["usd_per_100_agreements"] == 0 for r in original)


def test_unknown_cost_is_not_assumed_free():
    report = dict(model="unknown", input_tokens=100, output_tokens=100, agreements=6)
    assert cost_estimate(report, {})["usd_per_100_agreements"] is None

