"""Provider components; behavior preserved from the tested implementation."""

from typing import Protocol
from pydantic import BaseModel
from covenants.schemas import Usage


class ProviderError(RuntimeError):
    """Sanitized, actionable provider failure. Never includes credentials or raw request headers."""

    def __init__(self, message: str, usage: Usage | None = None):
        super().__init__(message)
        self.usage = usage


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, prompt: str, target_schema: type[BaseModel]) -> tuple[BaseModel, Usage]: ...
