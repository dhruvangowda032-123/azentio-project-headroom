"""One-to-one matching and exact, inspectable metrics; never imported by extraction/providers."""

import json
from decimal import Decimal
from pathlib import Path
from statistics import mean

import yaml

from covenants.services.extraction import extract
from covenants.providers import LLMProvider, ReplayProvider, get_provider

FIELDS = ("operator", "threshold", "unit", "effective_from", "effective_to")
TOLERANCE = Decimal("0.000001")


def _overlap(a: dict, b: dict) -> bool:
    return max(a["effective_from"], b["effective_from"]) <= min(a.get("effective_to") or "9999-12-31",
                                                              b.get("effective_to") or "9999-12-31")


def _field_equal(field: str, a: dict, b: dict) -> bool:
    if field == "threshold":
        return abs(Decimal(str(a[field])) - Decimal(str(b[field]))) <= TOLERANCE
    return a.get(field) == b.get(field)


def score(predictions: list[dict], gold: list[dict]) -> dict:
    expected = [g for g in gold if g.get("kind", "positive") == "positive"]
    # Match identity independently of correctness. Exact boundaries are preferred;
    # each gold record may be used once, and all unmatched predictions are false positives.
    unused = set(range(len(expected)))
    matches = []
    for predicted in predictions:
        options = [i for i in sorted(unused) if predicted["agreement"] == expected[i]["agreement"]
                   and predicted["type"] == expected[i]["type"] and predicted["clause_id"] == expected[i]["clause_id"]
                   and _overlap(predicted, expected[i])]
        if options:
            index = max(options, key=lambda i: sum(_field_equal(f, predicted, expected[i]) for f in FIELDS))
            unused.remove(index)
            matches.append((predicted, expected[index]))
    correct = sum(all(_field_equal(f, p, g) for f in FIELDS) for p, g in matches)
    precision = correct / len(predictions) if predictions else 0.0
    recall = correct / len(expected) if expected else 0.0
    negative_clauses = {(g["agreement"], g["clause_id"]) for g in gold if g.get("kind") == "negative"}
    errors = []
    for field in FIELDS:
        errors.append((field, sum(not _field_equal(field, p, g) for p, g in matches)))
    errors.extend([("missed_or_unmatched_gold", len(expected) - len(matches)),
                   ("unmatched_predictions", len(predictions) - len(matches)),
                   ("unverified_citation", sum(p.get("status") != "verified" for p in predictions))])
    # Expose actionable missed-case categories rather than only an aggregate count.
    missed = [expected[i] for i in unused]
    case_errors = [(f"missed_{tag}", sum(tag in g.get("tags", []) for g in missed))
                   for tag in ("step_down", "amendment_override", "cross_reference")]
    detailed_errors = [(name, count) for name, count in errors if name != "missed_or_unmatched_gold"] + case_errors
    categorized = sum(count for _, count in case_errors)
    if len(missed) > categorized:
        detailed_errors.append(("missed_other_covenants", len(missed) - categorized))
    return dict(precision=precision, recall=recall,
                f1=2 * precision * recall / (precision + recall) if precision + recall else 0.0,
                true_positives=correct, predicted=len(predictions), gold=len(expected), matched=len(matches),
                per_field_accuracy={f: sum(_field_equal(f, p, g) for p, g in matches) / len(matches) if matches else 0.0
                                    for f in FIELDS},
                citation_accuracy=sum(p.get("status") == "verified" for p, _ in matches) / len(predictions) if predictions else 0.0,
                unverified_rate=sum(p.get("status") != "verified" for p in predictions) / len(predictions) if predictions else 0.0,
                distractor_false_positives=sum((p["agreement"], p["clause_id"]) in negative_clauses for p in predictions),
                top_error_types=[{"type": field, "count": count} for field, count in
                                 sorted(detailed_errors, key=lambda x: -x[1]) if count > 0][:3])


def evaluate(provider: LLMProvider, root: Path = Path(".")) -> dict:
    # Only this evaluation module reads expected answers.
    gold = [json.loads(line) for line in (root / "data/golden/covenants.jsonl").read_text().splitlines() if line.strip()]
    predictions = []
    latencies = []
    tokens_in = tokens_out = calls = failed_calls = repair_attempts = 0
    for path in sorted((root / "data/agreements").glob("*.txt")):
        result = extract(path.read_text(), provider)
        predictions.extend({**c.model_dump(mode="json"), "agreement": path.stem} for c in result.covenants)
        latencies.append(result.usage.latency_ms)
        tokens_in += result.usage.input_tokens
        tokens_out += result.usage.output_tokens
        calls += result.usage.calls
        failed_calls += result.usage.failed_calls
        repair_attempts += result.repair_attempts
    if not latencies:
        raise ValueError("no agreements found for evaluation")
    return {"provider": provider.name, "model": provider.model, "metrics": score(predictions, gold),
            "agreements": len(latencies), "mean_latency_ms": mean(latencies), "max_latency_ms": max(latencies),
            "input_tokens": tokens_in, "output_tokens": tokens_out, "calls": calls,
            "failed_calls": failed_calls, "repair_attempts": repair_attempts,
            "latency_source": "sum of provider-call elapsed times per agreement; replay preserves recorded timings; "
                              "fake/rules timings measure local rule processing, not model inference"}


def cost_estimate(report: dict, pricing: dict) -> dict:
    table = pricing.get("models", {})
    prices = table.get(report["model"])
    if prices is None:
        return {"usd_per_100_agreements": None, "pricing_note": "unknown model pricing; not assumed free"}
    cost = (report["input_tokens"] * prices["input_per_million"] +
            report["output_tokens"] * prices["output_per_million"]) / 1_000_000
    return {"usd_per_100_agreements": cost * 100 / report["agreements"],
            "pricing_note": prices["note"]}


def safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def write_eval(report: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"eval_{safe_name(report['provider'])}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return path


def compare(names: list[str], root: Path = Path("."), record: bool = False) -> list[dict]:
    if len(names) < 2 or len(set(names)) != len(names):
        raise ValueError("compare requires at least two distinct providers")
    pricing = yaml.safe_load((root / "config/pricing.yaml").read_text())
    reports = []
    for name in names:
        provider = get_provider(name)
        if record:
            if name.startswith("replay:"):
                raise ValueError("cannot record a replay provider")
            provider = ReplayProvider(root / "fixtures/recordings" / safe_name(name), provider)
        report = evaluate(provider, root)
        report.update(cost_estimate(report, pricing))
        write_eval(report, root / "reports")
        reports.append(report)
    lines = ["# Provider comparison", "", "All metrics below are measured on the committed synthetic corpus.", "",
             "| Provider | Model | Precision | Recall | F1 | Citation | Unverified | Mean ms | Max ms | Input tokens | Output tokens | USD / 100 |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in reports:
        m = r["metrics"]
        lines.append(f"| {r['provider']} | {r['model']} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} | "
                     f"{m['citation_accuracy']:.4f} | {m['unverified_rate']:.4f} | {r['mean_latency_ms']:.2f} | "
                     f"{r['max_latency_ms']:.2f} | {r['input_tokens']} | {r['output_tokens']} | {r['usd_per_100_agreements']} |")
    lines.extend(["", "## Field accuracy (matched records)", ""])
    for r in reports:
        lines.append(f"- {r['provider']}: " + json.dumps(r["metrics"]["per_field_accuracy"], sort_keys=True))
        lines.append(f"  Top error categories: " + json.dumps(r["metrics"]["top_error_types"]))
        lines.append(f"  Pricing: {r['pricing_note']}")
    lines.extend(["", "## Interpretation", "",
                  "Fake/rules results are deterministic baselines, not small/large LLM benchmarks. Their zero tokens "
                  "and inference API cost do not imply free hosting or production readiness. Their latency measures local rules.",
                  "Replay returns original recorded usage, not replay execution time. Quality and provider failures "
                  "must be assessed alongside human review needs. No production model is selected without a real-model evaluation.",
                  "", "See README for matching rules, dataset limitations, data residency, and reproduction commands."])
    (root / "reports/comparison.md").write_text("\n".join(lines) + "\n")
    return reports

