"""Synchronous API with application factory and injectable offline dependencies."""

import hashlib
import secrets
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from covenants.compliance import check
from covenants.config import Settings
from covenants.extraction import extract
from covenants.middleware import BodyLimitMiddleware
from covenants.providers import LLMProvider, ProviderError, get_provider
from covenants.schemas import AgreementInput, CheckInput
from covenants.storage import Store


def create_app(settings: Settings | None = None, provider: LLMProvider | None = None) -> FastAPI:
    config = settings or Settings.from_env()

    @lru_cache(maxsize=1)
    def storage() -> Store:
        return Store(config.data_dir)

    def authorize(x_api_key: str | None = Header(default=None)) -> None:
        if config.api_key and not secrets.compare_digest(x_api_key or "", config.api_key):
            raise HTTPException(401, "invalid API key")

    application = FastAPI(title="Project Headroom", version="0.1.0", dependencies=[Depends(authorize)])

    application.add_middleware(BodyLimitMiddleware)

    @application.exception_handler(ProviderError)
    async def provider_failure(_request, error):
        return JSONResponse(status_code=502, content={"detail": str(error)})

    @application.get("/health")
    def health():
        return {"status": "ok"}

    @application.post("/agreements", status_code=201)
    def add_agreement(body: AgreementInput):
        store = storage()
        identity = hashlib.sha256(body.text.encode()).hexdigest()[:24]
        try:
            existing = store.get(identity)
            return {"agreement_id": existing.agreement_id, "issues": existing.issues, "cached": True}
        except KeyError:
            pass
        selected = provider if provider is not None else get_provider(config.provider, config.model)
        try:
            result = extract(body.text, selected, config.max_agreement_chars)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        store.save(body.text, result)
        return {"agreement_id": result.agreement_id, "issues": result.issues, "cached": False}

    def get_extraction(agreement_id: str):
        try:
            return storage().get(agreement_id)
        except KeyError:
            raise HTTPException(404, "agreement not found") from None

    @application.get("/agreements/{agreement_id}/covenants")
    def get_covenants(agreement_id: str):
        return get_extraction(agreement_id)

    @application.post("/agreements/{agreement_id}/compliance-check")
    def compliance_check(agreement_id: str, body: CheckInput):
        return check(get_extraction(agreement_id), body, storage(), config.confidence_cutoff, config.near_breach_percent)

    return application


app = create_app()

