"""Exercise a running local API with every synthetic agreement and all eight financial periods.

Run after starting Uvicorn or Compose. This is intentionally separate from offline pytest.
"""

import argparse
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def run(base_url: str, output: Path) -> dict:
    headers = {"x-api-key": os.getenv("HEADROOM_API_KEY", "")}
    identities = {}
    covenant_count = 0
    sample = None
    statuses = []
    with httpx.Client(base_url=base_url, headers=headers, timeout=60) as client:
        client.get("/health").raise_for_status()
        for path in sorted((ROOT / "data/agreements").glob("*.txt")):
            uploaded = client.post("/agreements", json={"text": path.read_text()})
            uploaded.raise_for_status()
            identity = uploaded.json()["agreement_id"]
            identities[path.stem] = identity
            response = client.get(f"/agreements/{identity}/covenants")
            response.raise_for_status()
            extracted = response.json()
            clauses = {c["clause_id"]: c["text"] for c in extracted["clauses"]}
            covenant_count += len(extracted["covenants"])
            for covenant in extracted["covenants"]:
                if covenant["status"] == "verified":
                    assert " ".join(covenant["quote"].split()) in " ".join(clauses[covenant["clause_id"]].split())
        for path in sorted((ROOT / "data/financials").glob("*.json")):
            for request in json.loads(path.read_text()):
                response = client.post(f"/agreements/{identities[path.stem]}/compliance-check", json=request)
                response.raise_for_status()
                result = response.json()
                expected = "BREACH" if path.stem == "loan_01" and request["period_end"] == "2026-09-30" else "PASS"
                assert result["overall_status"] == expected, result
                statuses.append({"borrower": path.stem, "period": request["period_end"], "status": expected})
                if expected == "BREACH":
                    sample = {"request": request, "response": result}
        missing = client.post(f"/agreements/{identities['loan_01']}/compliance-check",
                              json={"period_end": "2026-09-30", "financials": {}})
        missing.raise_for_status()
        assert missing.json()["overall_status"] == "NEEDS_REVIEW"
        assert client.get("/agreements/missing/covenants").status_code == 404
        assert client.post("/agreements", json={"text": ""}).status_code == 422
    report = {"agreements": len(identities), "covenants": covenant_count, "quarterly_checks": statuses,
              "missing_inputs": "NEEDS_REVIEW", "not_found": 404, "invalid_input": 422, "breach_example": sample}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"HTTP smoke passed: {len(identities)} agreements, {covenant_count} covenants, {len(statuses)} quarterly checks; report: {output}")
    return report


if __name__ == "__main__":
    load_dotenv(override=False)
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", type=Path, default=ROOT / "reports/http_smoke.json")
    args = parser.parse_args()
    run(args.url, args.out)

