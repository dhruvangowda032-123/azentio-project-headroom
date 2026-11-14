"""A bounded extract / verify / repair workflow shared by all entry points."""

import hashlib
import json
import time
from datetime import timedelta

from covenants.parser import parse_clauses
from covenants.providers import LLMProvider, ProviderError
from covenants.schemas import Covenant, ExtractionDraft, ExtractionMeta, ExtractionResult, Usage
from covenants.verification import verify

PROMPT_VERSION = "headroom-extract-v1"
INSTRUCTIONS = (
    "Extract ALL financial maintenance covenants; exclude margins, fees, and unrelated definitions. "
    "Use one record per schedule step with inclusive ISO dates. LTE means maximum; GTE means minimum. "
    "For amendments set supersedes_clause_id to the replaced clause. Do not drop the original covenant. "
    "A quote must occur verbatim in its cited clause and contain the threshold. Include scoped definitions "
    "in the quote when needed. Use numeric amounts in the same currency units as the document. "
    "Do not assume a date, amount, or financial formula absent from the text. "
    "Only quarterly covenants are supported; unsupported or ambiguous obligations belong in human review."
)


def extract(text: str, provider: LLMProvider, max_chars: int = 200_000) -> ExtractionResult:
    if not text.strip() or len(text) > max_chars:
        raise ValueError("agreement empty or exceeds size limit")
    clauses = parse_clauses(text)
    clause_map = {c.clause_id: c for c in clauses}
    agreement_id = hashlib.sha256(text.encode()).hexdigest()[:24]
    # All clauses retained for recall and cross-reference context. Batch once for this small corpus.
    request = {"agreement_id": agreement_id, "instructions": INSTRUCTIONS, "prompt_version": PROMPT_VERSION,
               "clauses": [{"clause_id": c.clause_id, "heading": c.heading, "text": c.text} for c in clauses]}
    prompt = json.dumps(request, sort_keys=True)
    draft, usage = provider.generate(prompt, ExtractionDraft)
    covenants = []
    issues = []
    repair_attempts = 0
    for index, initial in enumerate(draft.covenants):
        record = initial
        reason = verify(record, clause_map)
        if reason:
            repair_attempts += 1
            repair_started = time.perf_counter()
            repair_request = {**request, "repair": {"error": reason,
                               "candidate": record.model_dump(mode="json"),
                               "instruction": "Return exactly one corrected version of this candidate only."}}
            try:
                repaired, repair_usage = provider.generate(json.dumps(repair_request, sort_keys=True), ExtractionDraft)
                usage.add(repair_usage)
                if len(repaired.covenants) == 1:
                    record = repaired.covenants[0]
                    reason = verify(record, clause_map)
                else:
                    reason = f"repair must return exactly one record; original error: {reason}"
            except ProviderError as error:
                usage.add(error.usage or Usage(calls=1, failed_calls=1,
                                              latency_ms=(time.perf_counter() - repair_started) * 1000))
                reason = f"repair provider failed; original error: {reason}"
        covenants.append(Covenant(**record.model_dump(), covenant_id=f"{agreement_id}-{index + 1:03}",
                                  status="unverified" if reason else "verified", status_reason=reason or "quote and threshold verified"))
    # Close original intervals only when the amendment itself has verified evidence.
    for amendment in covenants:
        if not amendment.supersedes_clause_id:
            continue
        originals = [c for c in covenants if c.clause_id == amendment.supersedes_clause_id and c.type == amendment.type]
        if not originals:
            amendment.status = "unverified"
            amendment.status_reason = "amendment refers to missing original covenant"
            continue
        if amendment.status == "verified":
            for original in originals:
                if original.effective_from < amendment.effective_from and (
                    original.effective_to is None or original.effective_to >= amendment.effective_from
                ):
                    original.effective_to = amendment.effective_from - timedelta(days=1)
        else:
            issues.append("Unverified amendment: affected periods must be reviewed")
    if not covenants:
        issues.append("No financial covenants extracted; absence of obligations has not been established")
    return ExtractionResult(agreement_id=agreement_id, clauses=clauses, covenants=covenants,
                            extraction_meta=ExtractionMeta(provider=provider.name, model=provider.model,
                                prompt_version=PROMPT_VERSION, prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()),
                            usage=usage, issues=issues, repair_attempts=repair_attempts)

