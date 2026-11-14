# AI usage

Tool: OpenAI Codex. The candidate requested a fresh end-to-end implementation of Project Headroom, including all required tests and Docker Compose, after discussing the assignment and architecture.

Key prompts / instructions:
- Read the five-page assignment and explain its business problem before writing code.
- Use Python 3.11+, FastAPI, Pydantic v2, pytest; all tests must run offline without API keys.
- Implement extraction with exact citations and one repair, golden-set evaluation and provider comparison, deterministic quarterly compliance with audit logging.
- Add appropriate guardrails and Docker Compose without changing the assignment flow.
- Inspect an existing project's folder structure only; do not copy its code.

Design decisions owned by this implementation:
- A bounded Python workflow, without an agent framework or vector database.
- Shared application logic behind CLI and API.
- Fake/rules providers and explicit replay fixtures for offline review; live model results will only be claimed if actually measured.
- No actual API keys or existing-project source code are included.

## Errors caught and corrected

- The first CLI definition made `providers` positional, but the assignment requires `--providers`. A real command invocation caught this; it was changed to an explicit Typer option and an end-to-end CLI regression test was added.
- Initial recordings keyed identical agreement-content prompts to the same response file. Measuring fake latency exposed a replay timing mismatch. Adding stable agreement identity to the prompt made recording identities distinct; replay tests now assert original timing and metrics.
- Initial request limits checked only Content-Length. Code review identified chunked requests as a bypass. A bounded ASGI body reader now limits actual bytes and tests cover both forms.
- Initial repair failures did not count failed calls or elapsed time. Review added failure usage and repair-attempt accounting, with explicit tests.
- The code initially reported zero fake/rules latency. This was corrected to measured local rule-processing latency and documented separately from model inference or replay speed.
- An operator-consistency guard was added for explicit minimum/maximum phrasing. A targeted test confirms an exact quote with the wrong operator is not verified.

## Verification and limitations

The extraction, API/CLI, dataset, metric, compliance, provider-error, and audit tests are run with sockets disabled. Real network access is only used for dependency installation, documentation research, Docker base/dependency downloads, and explicit localhost smoke tests. Real Groq calls are not claimed without a replacement key and successful measured responses. The disclosed chat key was not reused.

Final recorded validation: 110 passing tests on the host and in a network-disabled Linux container; fresh-storage HTTP checks for six agreements, 39 covenants, eight reporting periods, and nine audit entries. Full details are in `reports/validation.json`. An upstream Starlette TestClient deprecation warning remains documented.

The existing `echo-sage` project was inspected only for high-level folder/dependency patterns; no source was copied. Generated corpus labels derive from an independent structured specification. Automated checks and AI design spot-checks are documented, but independent candidate manual review remains necessary.

Initial implementation remained local at the user's request. The candidate later created the GitHub repository and pushed `main`; the assistant confirmed the remote commit matched. No push, hosted PR creation/merge, or email submission was performed by the assistant. A subsequent local `ci/offline-validation` branch adds genuine automated validation and updates publication notes for the candidate to push and merge through a hosted PR. Its Python 3.11/3.12 matrix is a CI configuration, not a claim that hosted CI has already passed.

The candidate should independently review this file, the generated corpus/labels, and every module before interview or submission; an AI-authored test run is not a claim of candidate review.

