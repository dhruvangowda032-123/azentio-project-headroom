"""Provider components; behavior preserved from the tested implementation."""

import json
import re
import time
from pydantic import BaseModel
from covenants.schemas import Usage


class FakeProvider:
    """Deterministic rule-derived responses for the synthetic grammar, not general AI."""

    name = "fake"
    model = "synthetic-rules-v1"

    def generate(self, prompt: str, target_schema: type[BaseModel]) -> tuple[BaseModel, Usage]:
        started = time.perf_counter()
        request = json.loads(prompt)
        records = []
        for clause in request["clauses"]:
            for line in clause["text"].splitlines():
                # Explicit contractual grammar; a deliberate, honest limitation of this fake.
                match = re.search(
                    r"From (\d{4}-\d{2}-\d{2}) through (\d{4}-\d{2}-\d{2}), "
                    r"the Borrower shall ensure (.+?) (shall not exceed|shall not be less than) "
                    r"([\d,.]+) (ratio|currency|percent)\.", line,
                )
                if not match:
                    continue
                start, end, metric, wording, value, unit = match.groups()
                kind = next((k for phrase, k in [
                    ("Net Debt / LTM EBITDA", "LEVERAGE"), ("LTM EBITDA / interest expense", "INTEREST_COVER"),
                    ("cash available for debt service / debt service", "DSCR"), ("tangible net worth", "MIN_NET_WORTH"),
                    ("current assets / current liabilities", "CURRENT_RATIO"), ("quarterly capex", "MAX_CAPEX"),
                ] if phrase == metric), "OTHER")
                override = re.search(r"replaces clause (\d+(?:\.\d+)+)", clause["text"])
                records.append(dict(type=kind, operator="LTE" if wording == "shall not exceed" else "GTE",
                                    threshold=value.replace(",", ""), unit=unit, test_frequency="quarterly",
                                    effective_from=start, effective_to=end, clause_id=clause["clause_id"],
                                    quote=match.group(), confidence=0.97,
                                    supersedes_clause_id=override.group(1) if override else None))
            # Cross-reference: covenant and its expressly scoped definition share one clause.
            if "shall not exceed the Defined Leverage Limit" in clause["text"]:
                value = re.search(r"Defined Leverage Limit means ([\d.]+)", clause["text"])
                dates = re.search(r"From (\d{4}-\d{2}-\d{2}) through (\d{4}-\d{2}-\d{2})", clause["text"])
                if value and dates:
                    records.append(dict(type="LEVERAGE", operator="LTE", threshold=value.group(1), unit="ratio",
                                        test_frequency="quarterly", effective_from=dates.group(1), effective_to=dates.group(2),
                                        clause_id=clause["clause_id"], quote=clause["text"].strip(), confidence=0.92,
                                        supersedes_clause_id=None))
        response = target_schema.model_validate({"covenants": records})
        return response, Usage(calls=1, latency_ms=(time.perf_counter() - started) * 1000)


class RulesProvider(FakeProvider):
    """Intentionally simpler baseline: no schedules, overrides, or cross-reference support."""

    name = "rules"
    model = "simple-regex-v1"

    def generate(self, prompt: str, target_schema: type[BaseModel]) -> tuple[BaseModel, Usage]:
        response, usage = super().generate(prompt, target_schema)
        records = response.model_dump()["covenants"]
        counts: dict[str, int] = {}
        for record in records:
            counts[record["clause_id"]] = counts.get(record["clause_id"], 0) + 1
        records = [r for r in records if counts[r["clause_id"]] == 1 and not r["supersedes_clause_id"]
                   and "Defined Leverage Limit" not in r["quote"]]
        return target_schema.model_validate({"covenants": records}), usage
