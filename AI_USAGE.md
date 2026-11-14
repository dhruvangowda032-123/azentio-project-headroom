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

AI mistakes, checks, and corrections will be recorded below as validation proceeds. The candidate should independently review this file, the generated corpus/labels, and every module before interview or submission; an AI-authored test run is not a claim of candidate review.

