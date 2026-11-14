"""Evidence verification is deterministic and independent of model confidence."""

import re
from decimal import Decimal, InvalidOperation

from covenants.schemas import Clause, CovenantDraft

NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w.]|,\d)")


def normalize(text: str) -> str:
    return " ".join(text.split())


def verify(covenant: CovenantDraft, clauses: dict[str, Clause]) -> str | None:
    clause = clauses.get(covenant.clause_id)
    if clause is None:
        return "cited clause does not exist"
    quote = normalize(covenant.quote)
    if not quote or quote not in normalize(clause.text):
        return "quote does not appear verbatim in cited clause"
    values = []
    for match in NUMBER.finditer(quote):
        try:
            values.append(Decimal(match.group().replace(",", "")))
        except InvalidOperation:
            continue
    if covenant.threshold not in values:
        return "threshold value does not appear in quote"
    # A limited, explicit consistency check, not a semantic proof of the contract.
    lower = quote.lower()
    maximum = "shall not exceed" in lower
    minimum = "shall not be less than" in lower
    if maximum != minimum:
        expected = "LTE" if maximum else "GTE"
        if covenant.operator != expected:
            return "operator contradicts explicit comparison wording in quote"
    return None

