# Project Headroom

Read synthetic corporate loan agreements, extract financial covenants with checked citations, and check quarterly figures using deterministic arithmetic. Failed evidence checks remain visible and uncertain results go to review.

This is an assignment implementation with production-oriented safeguards, not an approved production credit-decision system. The default application and tests run locally; GitHub publication does not deploy a live application or submit the assignment by email.

## Quick start

Requires Python 3.11+ (tested on 3.12). Install dependencies once with network access; tests and the default demo then run offline.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install -e .
pytest
covenants extract data/agreements/loan_01.txt --provider fake --out out/loan_01.json
covenants eval --provider fake
python scripts/verify_replay.py
uvicorn covenants.api:app --host 127.0.0.1 --port 8000
```

In another activated terminal: `python scripts/smoke_http.py`. This uploads all six agreements, checks all eight borrower/quarter combinations, verifies citations, exercises invalid/missing inputs, and saves `reports/http_smoke.json`. API docs: <http://127.0.0.1:8000/docs>.

The virtual environment, `.env`, runtime database, and `out/` are ignored. No real model or API key is required for the commands above. Use synthetic information only.

A complete sample extraction is saved in [reports/sample_extraction.json](reports/sample_extraction.json); the verified record quotes its original numbered clause and includes all required model fields and extraction metadata.

Validation: **110 tests pass locally and in a Linux container with networking disabled**. A fresh-container HTTP run checked six agreements, 39 extractions, eight financial periods, and nine audit entries (including one missing-input check). See [reports/validation.json](reports/validation.json) and [reports/http_smoke.json](reports/http_smoke.json). One upstream Starlette TestClient deprecation warning remains with the pinned HTTPX setup; it does not fail tests.

## Architecture

```text
FastAPI routes / Typer CLI
          |
          +-- extract --> parse clauses --> LLMProvider --> validate --> verify --> repair once --> SQLite / JSON
          |
          +-- compliance --> select dated rules --> Python Decimal arithmetic --> review / result --> SQLite audit
          |
          +-- evaluate --> extraction + independent gold --> one-to-one matching --> metrics + comparison

LLMProvider: FakeProvider | RulesProvider | optional GroqProvider | ReplayProvider
```

`src/covenants/` separates schemas, parsing, providers, verification, extraction, compliance, evaluation, storage, API, CLI, and settings. API and CLI share the extraction service. Compliance has no provider dependency. HTTPX calls Groq's OpenAI-compatible endpoint directly; an agent framework, vector database, external DB, and broker are unnecessary.

## Extraction design (under one page)

The parser recognizes headings such as `22.2 Leverage` (including Markdown), rejects duplicate IDs, and preserves original text with start/end character offsets. A SHA-256 prefix of the original input identifies an agreement. All clauses, including definitions and amendments, are included in one batched request for these small documents; keyword filtering is avoided to protect recall and cross-reference context.

The versioned prompt requests quarterly financial maintenance covenants, excludes numeric distractors, and requires one record per schedule step. A Pydantic schema enforces enum/operator/unit/date constraints. Groq uses strict structured output; local validation remains authoritative because valid JSON is not necessarily correct interpretation. Missing facts must not be guessed. The fake implements the documented synthetic grammar only and is not an LLM.

Verification looks up the cited clause, checks the verbatim quote after whitespace normalization (case and punctuation still matter), and parses complete numeric tokens with regex and Decimal. `4`, `4.0`, and `4.00` compare numerically; `14.0` does not match `4`. Commas in amounts are supported. A limited operator guard also catches contradictions with explicit "shall not exceed" / "shall not be less than" wording. Written-out numbers, scaling, and general semantic interpretation are beyond this verifier and need review or additional support.

Each failed citation gets exactly one correction request containing the error and candidate. A second failure, wrong response count, or repair-provider failure retains an unverified record with a reason. Initial provider/schema failures abort ingestion visibly instead of returning empty success. Empty extraction never authorizes a compliance pass. Output carries provider, model, prompt version, and prompt hash.

Dates are inclusive. Each step-down is a separate record. A verified amendment identifies `supersedes_clause_id`; the original interval closes the day before its start, and selection excludes replaced schedule records. Conflicting active rules, missing originals, unverified rules, and dates without a threshold require review. The corpus cross-reference points to a scoped definition inside the same numbered clause, allowing one quote to include obligation and numeric definition. Cross-clause evidence and separate amendment letters are future extensions.

## Synthetic corpus and labels

Regenerate with `python scripts/generate_data.py`. The generator imports no extractor code and renders text and labels from an explicit structured specification:

- Six fictional agreements, each with six covenant types and two numeric distractors.
- 39 positive labels and 12 negative labels in `data/golden/covenants.jsonl`.
- Two step-down agreements, one amendment, and one definition cross-reference.
- Two borrowers over four quarters; loan_01 breaches leverage in Q3.

All monetary inputs are INR in base units, not crores or millions. Leverage uses net debt / LTM EBITDA; interest cover uses LTM EBITDA / interest expense; DSCR uses cash available for debt service / debt service; current ratio uses current assets / current liabilities. Net worth and quarterly capex are direct amounts. The documents state this simplified convention; real contracts need validated accounting definitions.

Tags identify difficult cases. Negative records specify clauses that should yield no covenant and are excluded from recall's denominator; extracting one is a false positive. Automated checks cover counts, every labelled quote's presence, fields, and known boundaries. Design spot-checks covered loan_01's leverage periods, loan_03's July override, loan_04's scoped definition, and minimum/maximum wording. The candidate must personally confirm the labels before submission: AI-generated labels are not independent human ground truth. Perfect fake scores on this small, templated corpus do not establish generalization.

## Evaluation and reproducibility

```sh
covenants eval --provider fake
covenants compare --providers rules,fake --record
covenants compare --providers replay:rules,replay:fake
python scripts/verify_replay.py
```

Evaluation writes `reports/eval_<provider>.json`; comparison also writes `reports/comparison.md`. Replay preserves recorded responses, tokens, and call latency; it never silently calls a live model. Prompt/schema/model hashes select recordings. Agreement identity in the prompt prevents identical-content call collisions. Missing/incompatible recordings fail explicitly. Reported latency is provider-call elapsed time per agreement including successful repair calls, not replay speed or full HTTP request latency.

Matching is one-to-one on agreement + type + clause ID + overlapping inclusive dates. Among overlapping candidates, most matching fields are preferred; ties use stable gold order. A duplicate cannot consume the same gold record twice. A correct covenant requires correct operator, threshold, unit, and both dates: threshold absolute tolerance `0.000001`, other fields exact. A wrong matched prediction contributes a false positive and a missed correct covenant.

Reports include precision/recall/F1, field accuracy among matched records, citation accuracy (matched correct clause + verified, divided by all predictions), unverified rate, distractor false positives, latency, tokens, repair attempts, failed calls, estimated paid-rate USD/100 agreements, and top error categories. A hand-built test verifies P=0.5 and R=1/3. Unknown pricing is null, never assumed free. Fake/rules have zero model tokens and API cost but measured local rule-processing time; hosting cost is excluded. Failed calls without returned token usage cannot provide a complete billing estimate.

Measured deterministic comparison: fake P/R/F1 = 1/1/1; simpler regex baseline P≈0.9697, R≈0.8205, F1≈0.8889. Its top three reported errors are four missed schedule records, an incorrect original end date after amendment, and a missed amendment override. It also misses the definition cross-reference. These are not real small/large-model results. The brief permits rules vs fake without real-model access; their manifests say `deterministic-baseline`.

Recommendation: use FakeProvider for offline acceptance and demos; the simpler baseline is inadequate for dated obligations. Neither is recommended for unrestricted production extraction. Before a pilot, evaluate real models on separately reviewed holdout agreements; prioritize recall, operators, dates, false-safe decisions, and review burden, then choose the least expensive model meeting agreed requirements. Rules/replay stay local. Groq receives document text externally, so production requires an approved hosting/data-residency arrangement; no regional guarantee is assumed here.

## Optional live Groq extraction

Save a private replacement key in ignored `.env` or the environment as `GROQ_API_KEY`. Never reuse an exposed chat key.

```sh
covenants extract data/agreements/loan_01.txt --provider groq:openai/gpt-oss-20b --out out/groq.json
covenants compare --providers groq:openai/gpt-oss-20b,groq:openai/gpt-oss-120b --record
covenants compare --providers replay:groq_openai_gpt-oss-20b,replay:groq_openai_gpt-oss-120b
```

Both model names have [Groq structured-output support](https://console.groq.com/docs/structured-outputs). Account access/free quotas can change. 20B is smaller than 120B but exceeds the brief's example of a <=4B local model; do not describe it as <=4B. The committed comparison uses the no-real-model fallback. Live availability, quality, and real-model recordings remain unverified until a replacement key is configured and calls succeed.

For the API set `HEADROOM_PROVIDER=groq` and `HEADROOM_MODEL` before starting. CLI selection is explicit. Network timeouts and one bounded retry for transient HTTP errors are separate from the one citation-repair attempt. Refusals, truncation, schema errors, and exhausted HTTP retries produce visible failures, not silent substitution. Keys are never put into prompts or error responses.

## API example

`POST /agreements` accepts `{"text":"...numbered agreement text..."}` and extracts synchronously. Identical text reuses an immutable extraction. `GET /agreements/{agreement_id}/covenants` returns records, clauses, metadata, usage, and issues.

After ingesting `loan_01.txt`, send the third entry in `data/financials/loan_01.json` to `POST /agreements/{agreement_id}/compliance-check`:

```json
{
  "period_end": "2026-09-30",
  "financials": {"net_debt":450000000,"ltm_ebitda":100000000,"interest_expense":20000000,
    "cash_available_for_debt_service":60000000,"debt_service":40000000,"tangible_net_worth":80000000,
    "current_assets":200000000,"current_liabilities":100000000,"capex":10000000}
}
```

The leverage result includes the following fields; the full response also includes the exact quote, IDs, metadata, and other covenant results:

```json
{
  "type":"LEVERAGE", "computed_value":4.5, "applicable_threshold":3.5,
  "status":"BREACH", "headroom_percent":-28.571428571428573, "clause_id":"22.1"
}
```

Headroom percentage = `(threshold-actual)/threshold*100` for LTE and `(actual-threshold)/threshold*100` for GTE. Negative means breach; nonnegative below 10% means near breach. Exactly at the limit is compliant and near breach at the default setting. Missing inputs, invalid denominators, low confidence, unverified evidence, unsupported formulas/units, and ambiguous intervals produce `NEEDS_REVIEW`. Confidence is model-reported, not a calibrated probability. A verified citation does not establish semantic correctness or completeness.

Every check inserts one SQLite audit row: agreement ID, period, canonical input hash, per-covenant results, extraction metadata, and UTC timestamp. Update/delete triggers enforce append-only behavior, not cryptographic tamper-proofing against an administrator. Failed audit storage prevents successful check responses. Re-ingestion never overwrites the original extraction.

## Guardrails and tests

GitHub Actions runs the offline suite, dependency compatibility check, and exact replay verification on Python 3.11 and 3.12 for pull requests into `main` and configured branch pushes. Installation downloads dependencies; the pytest suite itself blocks network sockets and needs no API secrets. See `.github/workflows/tests.yml`. Hosted CI results must be checked on the actual pull request; local passing tests alone do not prove the hosted workflow passed.

`pytest` disables network sockets and removes API-key environment values. All model-dependent tests use FakeProvider; real-provider transport is tested with in-memory HTTP mocks. Tests cover offsets/duplicate IDs, schemas, quotes/numbers, one repair, both inequalities, denominators, missing inputs, step-downs/amendments, review routing, empty extraction, audits, CLI/API, known metrics, label leakage, replay identity, timeouts, rate limits, and malformed/truncated responses.

Agreement text is untrusted prompt data, not instructions; the model has no execution/browsing tools. This reduces injection impact without guaranteeing correct interpretation. Limits, validated outputs, Decimal arithmetic, parameterized SQLite, immutable extractions, optional `HEADROOM_API_KEY` authentication, bounded retries, and Docker secret exclusions add protection. Default binding is local. `/docs` and schema metadata are public locally; public deployment needs a separate review.

## Docker / Compose

Docker is optional. Reviewers can run plain `pytest` after installing dependencies without Docker or services.

```sh
docker compose build api test
docker compose --profile test run --rm --no-deps test
docker compose up -d --wait api
python scripts/smoke_http.py
docker compose down
```

Tests run with no network. The API uses a non-root user, localhost port publishing, dropped capabilities, a read-only root filesystem, and a named SQLite volume. `.env`, `.git`, `.venv`, and runtime data are excluded from images. A later local image build is `docker build --target base -t project-headroom:local .`; nothing is pushed.

## Scope, submission, and next steps

Implemented: the three core tasks, offline fallback comparison, optional real-provider adapter/recording, CLI/API, tests, and Docker Compose. Stretch memo generation, name redaction, review UI/corrections, and separate amendment-letter ingestion are excluded. `NEEDS_REVIEW` is a result for a human; core scope does not include a reviewer UI.

Before production: independently labelled holdouts and calibrated uncertainty; contract-specific formulas/currencies; multi-source evidence; explicit document/model/prompt version management; authenticated reviewer approvals; concurrency/rate budgets; organization identity/TLS; backups/migrations/retention; monitoring and load/security tests. SQLite and the intentionally synchronous API satisfy this local assignment; they do not demonstrate enterprise scale.

Initial implementation was performed locally and the candidate subsequently published the repository on GitHub. Use a feature branch and a GitHub pull request for subsequent changes, and verify its checks before merging. Email submission and compliance with the coordinator's timing rules remain the candidate's responsibility. See `AI_USAGE.md`. Never claim a retrospective submission or fabricated human review.

