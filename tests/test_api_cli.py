import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from covenants.api import create_app
from covenants.cli import app
from covenants.core.config import Settings
from covenants.providers import FakeProvider, ProviderError
from covenants.schemas import ExtractionResult
from covenants.services.verification import normalize

ROOT = Path(__file__).resolve().parents[1]


def test_api_full_flow_and_verified_substrings(text, financials, tmp_path, monkeypatch):
    application = create_app(Settings(data_dir=tmp_path), FakeProvider())
    with TestClient(application) as client:
        assert client.get("/health").json() == {"status": "ok"}
        uploaded = client.post("/agreements", json={"text": text})
        assert uploaded.status_code == 201
        identity = uploaded.json()["agreement_id"]
        response = client.get(f"/agreements/{identity}/covenants")
        assert response.status_code == 200
        extraction = ExtractionResult.model_validate(response.json())
        clauses = {c.clause_id: c for c in extraction.clauses}
        for c in extraction.covenants:
            if c.status == "verified":
                assert normalize(c.quote) in normalize(clauses[c.clause_id].text)
        financials["net_debt"] = 450_000_000
        # Once extracted, compliance must succeed even if the provider becomes unavailable.
        def forbidden(*args, **kwargs):
            raise AssertionError("compliance must not call AI")
        monkeypatch.setattr(FakeProvider, "generate", forbidden)
        for _ in range(2):
            response = client.post(f"/agreements/{identity}/compliance-check",
                                   json={"period_end": "2026-09-30", "financials": financials})
            assert response.status_code == 200
            assert response.json()["overall_status"] == "BREACH"
            leverage = next(r for r in response.json()["results"] if r["type"] == "LEVERAGE")
            assert leverage["computed_value"] == 4.5
            assert leverage["applicable_threshold"] == 3.5
            assert leverage["clause_id"] == "22.1"
        assert client.post("/agreements", json={"text": text}).json()["cached"] is True


@pytest.mark.parametrize("body", [{"text": ""}, {"text": "  "}, {"text": "no clauses"},
                                   {"text": "x" * 200_001}, {"text": "22.1 A\nx", "unexpected": True}])
def test_api_invalid_agreements(body, tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path), FakeProvider())) as client:
        assert client.post("/agreements", json=body).status_code == 422


def test_api_unknown_id_and_auth(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, api_key="test-only-key"), FakeProvider())) as client:
        assert client.get("/health").status_code == 401
        response = client.get("/agreements/unknown/covenants", headers={"x-api-key": "test-only-key"})
        assert response.status_code == 404


@pytest.mark.parametrize("body", [{"period_end": "invalid", "financials": {}},
                                   {"period_end": "2026-03-31", "financials": {"net_debt": "NaN"}}])
def test_api_invalid_financials(text, body, tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path), FakeProvider())) as client:
        identity = client.post("/agreements", json={"text": text}).json()["agreement_id"]
        assert client.post(f"/agreements/{identity}/compliance-check", json=body).status_code == 422


def test_api_provider_failure_is_not_empty_success(text, tmp_path):
    class Unavailable(FakeProvider):
        def generate(self, *_args):
            raise ProviderError("provider unavailable")
    with TestClient(create_app(Settings(data_dir=tmp_path), Unavailable())) as client:
        assert client.post("/agreements", json={"text": text}).status_code == 502


def test_body_size_limit_with_and_without_content_length(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path), FakeProvider())) as client:
        assert client.post("/agreements", content=b"x" * 1_500_001).status_code == 413
        chunks = (b"x" * 500_001 for _ in range(3))
        assert client.post("/agreements", content=chunks).status_code == 413


def test_invalid_content_length_is_rejected(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path), FakeProvider())) as client:
        assert client.post("/agreements", content=b"{}", headers={"content-length": "bad"}).status_code == 400


def test_cli_extract_and_schema(tmp_path):
    path = tmp_path / "answer.json"
    result = CliRunner().invoke(app, ["extract", str(ROOT / "data/agreements/loan_01.txt"),
                                      "--provider", "fake", "--out", str(path)])
    assert result.exit_code == 0, result.output
    extraction = ExtractionResult.model_validate_json(path.read_text())
    assert len(extraction.covenants) == 7


def test_cli_eval_outputs_required_metrics(tmp_path, monkeypatch):
    import shutil
    shutil.copytree(ROOT / "data", tmp_path / "data")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["eval", "--provider", "fake"])
    assert result.exit_code == 0, result.output
    report = json.loads((tmp_path / "reports/eval_fake.json").read_text())
    assert {"precision", "recall", "f1", "per_field_accuracy", "citation_accuracy", "unverified_rate"} <= report["metrics"].keys()


def test_cli_compare_required_option_and_replay(tmp_path, monkeypatch):
    import shutil
    for folder in ("data", "config"):
        shutil.copytree(ROOT / folder, tmp_path / folder)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["compare", "--providers", "rules,fake", "--record"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "reports/comparison.md").exists()
    result = runner.invoke(app, ["compare", "--providers", "replay:rules,replay:fake"])
    assert result.exit_code == 0, result.output

