"""Provider components; behavior preserved from the tested implementation."""

import re
from pathlib import Path
from .base import LLMProvider, ProviderError
from .fake import FakeProvider, RulesProvider
from .groq import GroqProvider
from .replay import ReplayProvider


def get_provider(name: str, model: str | None = None) -> LLMProvider:
    if name.startswith("replay:"):
        suffix = name.split(":", 1)[1]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", suffix):
            raise ProviderError("invalid recording name")
        return ReplayProvider(Path("fixtures/recordings") / suffix)
    if name == "fake":
        return FakeProvider()
    if name == "rules":
        return RulesProvider()
    if name == "groq" or name.startswith("groq:"):
        return GroqProvider(name.split(":", 1)[1] if ":" in name else model or "openai/gpt-oss-20b")
    raise ProviderError(f"unknown provider: {name}")
