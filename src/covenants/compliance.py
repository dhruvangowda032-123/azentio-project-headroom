"""Auditable arithmetic only. This module has no provider imports or LLM calls."""

import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, DecimalException

from covenants.schemas import CheckInput, CheckResult, Covenant, CovenantType, ExtractionResult
from covenants.storage import Store

RATIOS = {
    CovenantType.LEVERAGE: ("net_debt", "ltm_ebitda"),
    CovenantType.INTEREST_COVER: ("ltm_ebitda", "interest_expense"),
    CovenantType.DSCR: ("cash_available_for_debt_service", "debt_service"),
    CovenantType.CURRENT_RATIO: ("current_assets", "current_liabilities"),
}
DIRECT = {CovenantType.MIN_NET_WORTH: "tangible_net_worth", CovenantType.MAX_CAPEX: "capex"}


def calculate(covenant: Covenant, financials: dict[str, Decimal]) -> Decimal:
    expected_unit = "ratio" if covenant.type in RATIOS else "currency"
    if covenant.unit != expected_unit:
        raise ValueError("unsupported unit for this financial formula")
    if covenant.type in RATIOS:
        numerator, denominator = RATIOS[covenant.type]
        if financials[denominator] <= 0:
            raise ValueError(f"denominator {denominator} must be positive")
        return financials[numerator] / financials[denominator]
    if covenant.type in DIRECT:
        return financials[DIRECT[covenant.type]]
    raise ValueError("unsupported covenant formula; human interpretation required")


def in_period(covenant: Covenant, period: date) -> bool:
    return covenant.effective_from <= period and (covenant.effective_to is None or period <= covenant.effective_to)


def check(extraction: ExtractionResult, request: CheckInput, store: Store,
          confidence_cutoff: float = 0.8, near_breach_percent: float = 10) -> dict:
    if not 0 <= confidence_cutoff <= 1 or not 0 <= near_breach_percent <= 100:
        raise ValueError("invalid review configuration")
    groups: dict[CovenantType, list[Covenant]] = defaultdict(list)
    for covenant in extraction.covenants:
        groups[covenant.type].append(covenant)
    results = []
    for kind, records in groups.items():
        active = [c for c in records if in_period(c, request.period_end)]
        # An amendment supersedes the referenced clause at and after its effective date,
        # including future schedule steps. Unverified amendments remain in the conflict set.
        replaced = {c.supersedes_clause_id for c in active if c.status == "verified" and c.supersedes_clause_id}
        active = [c for c in active if c.clause_id not in replaced]
        candidates = active or [records[0]]
        for covenant in candidates:
            reason = ""
            actual = headroom = None
            if not active:
                reason = "no covenant threshold applies on this date"
            elif len(active) > 1:
                reason = "overlapping covenant periods or ambiguous amendment require review"
            elif covenant.status != "verified":
                reason = f"unverified extraction: {covenant.status_reason}"
            elif covenant.confidence < confidence_cutoff:
                reason = "extraction confidence below configured cutoff"
            if not reason:
                try:
                    actual = calculate(covenant, request.financials)
                    headroom = ((covenant.threshold - actual) if covenant.operator == "LTE" else
                                (actual - covenant.threshold)) / covenant.threshold * Decimal(100)
                except KeyError as error:
                    reason = f"missing financial input: {error.args[0]}"
                except (ValueError, DecimalException) as error:
                    reason = str(error)
            if reason:
                status = "NEEDS_REVIEW"
            elif headroom < 0:
                status = "BREACH"
                reason = "actual violates contractual limit"
            elif headroom < Decimal(str(near_breach_percent)):
                status = "NEAR_BREACH"
                reason = "compliant, but headroom is below warning percentage"
            else:
                status = "PASS"
                reason = "within limit with sufficient headroom"
            results.append(CheckResult(covenant_id=covenant.covenant_id, type=kind, computed_value=actual,
                                       applicable_threshold=covenant.threshold if active else None,
                                       status=status, headroom_percent=headroom, clause_id=covenant.clause_id,
                                       quote=covenant.quote, reason=reason).model_dump(mode="json"))
    canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    # No all-clear can be returned from an empty extraction.
    overall = ("NEEDS_REVIEW" if not results or any(r["status"] == "NEEDS_REVIEW" for r in results) else
               "BREACH" if any(r["status"] == "BREACH" for r in results) else
               "NEAR_BREACH" if any(r["status"] == "NEAR_BREACH" for r in results) else "PASS")
    meta = extraction.extraction_meta.model_dump(mode="json")
    store.audit(extraction.agreement_id, request.period_end.isoformat(), digest, results, meta)
    return dict(agreement_id=extraction.agreement_id, period_end=request.period_end.isoformat(),
                overall_status=overall, input_hash=digest, results=results,
                extraction_meta=meta, issues=extraction.issues)

