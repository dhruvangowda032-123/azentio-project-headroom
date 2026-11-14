"""Provider components; behavior preserved from the tested implementation."""

import hashlib
import json
from pathlib import Path
from pydantic import BaseModel
from covenants.schemas import Usage
from .base import LLMProvider, ProviderError
from .groq import GroqProvider


class ReplayProvider:
    """Content-addressed recordings keyed by prompt, schema, and model; no silent live fallback."""

    def __init__(self, directory: Path, wrapped: LLMProvider | None = None):
        self.directory = directory
        self.wrapped = wrapped
        self.name = f"replay:{directory.name}" if wrapped is None else wrapped.name
        manifest = directory / "manifest.json"
        if wrapped:
            self.model = wrapped.model
        elif manifest.exists():
            self.model = json.loads(manifest.read_text())["model"]
        else:
            raise ProviderError(f"no recording manifest in {directory}")

    def generate(self, prompt: str, target_schema: type[BaseModel]) -> tuple[BaseModel, Usage]:
        payload = json.dumps({"prompt": prompt, "schema": target_schema.model_json_schema(), "model": self.model}, sort_keys=True)
        key = hashlib.sha256(payload.encode()).hexdigest()
        path = self.directory / f"{key}.json"
        if self.wrapped:
            parsed, usage = self.wrapped.generate(prompt, target_schema)
            self.directory.mkdir(parents=True, exist_ok=True)
            manifest = {"provider": self.wrapped.name, "model": self.model,
                        "kind": "real" if isinstance(self.wrapped, GroqProvider) else "deterministic-baseline"}
            manifest_path = self.directory / "manifest.json"
            if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
                raise ProviderError("recording directory already belongs to a different provider/model")
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            path.write_text(json.dumps({"key": key, "response": parsed.model_dump(mode="json"),
                                        "usage": usage.model_dump()}, indent=2) + "\n")
            return parsed, usage
        if not path.exists():
            raise ProviderError("recording missing for this exact prompt/schema/model; replay never calls the network")
        recorded = json.loads(path.read_text())
        if recorded.get("key") != key:
            raise ProviderError("recording identity mismatch")
        return target_schema.model_validate(recorded["response"]), Usage.model_validate(recorded["usage"])
