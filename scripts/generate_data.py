"""Generate fictional agreements and independent expected labels from one explicit specification.

No application/extractor code is imported. Re-run from the repository root.
Amounts and financial inputs use INR (not crores/millions); dates are inclusive.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = [
    ("LEVERAGE", "Leverage", "Net Debt / LTM EBITDA", "LTE", 4.0, "ratio"),
    ("INTEREST_COVER", "Interest cover", "LTM EBITDA / interest expense", "GTE", 3.0, "ratio"),
    ("DSCR", "Debt service coverage", "cash available for debt service / debt service", "GTE", 1.2, "ratio"),
    ("MIN_NET_WORTH", "Minimum net worth", "tangible net worth", "GTE", 50_000_000, "currency"),
    ("CURRENT_RATIO", "Current ratio", "current assets / current liabilities", "GTE", 1.5, "ratio"),
    ("MAX_CAPEX", "Capital expenditure", "quarterly capex", "LTE", 20_000_000, "currency"),
]


def generate(root: Path = ROOT) -> None:
    for folder in ("agreements", "golden", "financials"):
        (root / "data" / folder).mkdir(parents=True, exist_ok=True)
    gold = []
    for number in range(1, 7):
        name = f"loan_{number:02}"
        text = [f"# FICTIONAL {name}: Example Borrower {number} Ltd\n",
                "Synthetic training document. No real borrower. All monetary values and financial inputs are INR.\n",
                "Financial ratios use quarter-end net debt and LTM EBITDA/interest expense; DSCR uses the supplied "
                "cash available for debt service and debt service for the same reporting period. Capex is quarterly.\n"]
        for offset, (kind, heading, metric, operator, threshold, unit) in enumerate(METRICS, 1):
            clause_id = f"22.{offset}"
            text.append(f"\n{clause_id} {heading}\nTest frequency: quarterly, at quarter end.\n")
            steps = [("2026-01-01", "2026-12-31", threshold)]
            tags = ["minimum_wording" if operator == "GTE" else "maximum_wording"]
            if number in (1, 2) and kind == "LEVERAGE":
                steps = [("2026-01-01", "2026-06-30", 4.0), ("2026-07-01", "2026-12-31", 3.5)]
                tags.append("step_down")
            for start, end, limit in steps:
                wording = "shall not exceed" if operator == "LTE" else "shall not be less than"
                if number == 4 and kind == "LEVERAGE":
                    quote = (f"22.1 {heading}\nTest frequency: quarterly, at quarter end.\n"
                             f"From {start} through {end}, the Borrower shall ensure Net Debt / LTM EBITDA "
                             "shall not exceed the Defined Leverage Limit.\n"
                             f"For this clause only, Defined Leverage Limit means {limit} ratio.")
                    text.append(quote.split("at quarter end.\n", 1)[1] + "\n")
                    record_tags = tags + ["cross_reference"]
                else:
                    quote = f"From {start} through {end}, the Borrower shall ensure {metric} {wording} {limit} {unit}."
                    text.append(quote + "\n")
                    record_tags = tags
                gold.append(dict(agreement=name, kind="positive", type=kind, operator=operator,
                                 threshold=limit, unit=unit, effective_from=start,
                                 effective_to="2026-06-30" if number == 3 and kind == "LEVERAGE" else end,
                                 clause_id=clause_id, quote=quote,
                                 tags=record_tags + (["amendment_original"] if number == 3 and kind == "LEVERAGE" else [])))
        if number == 3:
            quote = ("From 2026-07-01 through 2026-12-31, the Borrower shall ensure "
                     "Net Debt / LTM EBITDA shall not exceed 3.0 ratio.")
            text.append("\n23.1 Amendment to leverage\nThis amendment replaces clause 22.1 from 2026-07-01.\n"
                        "Test frequency: quarterly, at quarter end.\n" + quote + "\n")
            gold.append(dict(agreement=name, kind="positive", type="LEVERAGE", operator="LTE", threshold=3.0,
                             unit="ratio", effective_from="2026-07-01", effective_to="2026-12-31",
                             clause_id="23.1", quote=quote, tags=["amendment_override"]))
        for clause_id, heading, body in [("30.1", "Interest margin", "The applicable interest margin is 2.0 percent per annum."),
                                         ("30.2", "Commitment fee", "The commitment fee is 0.5 percent on the undrawn amount.")]:
            text.append(f"\n{clause_id} {heading}\n{body}\n")
            gold.append(dict(agreement=name, kind="negative", clause_id=clause_id, tags=["numeric_distractor"]))
        (root / "data/agreements" / f"{name}.txt").write_text("".join(text))
    (root / "data/golden/covenants.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in gold))
    for borrower in (1, 3):
        quarters = []
        for quarter, period in enumerate(("2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31"), 1):
            financials = dict(net_debt=250_000_000, ltm_ebitda=100_000_000, interest_expense=20_000_000,
                              cash_available_for_debt_service=60_000_000, debt_service=40_000_000,
                              tangible_net_worth=80_000_000, current_assets=200_000_000,
                              current_liabilities=100_000_000, capex=10_000_000)
            if borrower == 1 and quarter == 3:
                financials["net_debt"] = 450_000_000
            quarters.append(dict(period_end=period, financials=financials))
        (root / "data/financials" / f"loan_{borrower:02}.json").write_text(json.dumps(quarters, indent=2) + "\n")
    print(f"Generated 6 agreements, {sum(r['kind'] == 'positive' for r in gold)} positive labels, "
          f"{sum(r['kind'] == 'negative' for r in gold)} negative labels, and 8 quarterly inputs.")


if __name__ == "__main__":
    generate()

