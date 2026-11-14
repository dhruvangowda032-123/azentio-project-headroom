"""Environment-only secrets and bounded application configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("runtime")
    provider: str = "fake"
    model: str = "openai/gpt-oss-20b"
    confidence_cutoff: float = 0.8
    near_breach_percent: float = 10.0
    max_agreement_chars: int = 200_000
    api_key: str = ""

    def __post_init__(self) -> None:
        if not 0 <= self.confidence_cutoff <= 1:
            raise ValueError("confidence cutoff must be between zero and one")
        if not 0 <= self.near_breach_percent <= 100:
            raise ValueError("near-breach percentage must be between zero and 100")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=False)
        return cls(
            data_dir=Path(os.getenv("HEADROOM_DATA_DIR", "runtime")),
            provider=os.getenv("HEADROOM_PROVIDER", "fake"),
            model=os.getenv("HEADROOM_MODEL", "openai/gpt-oss-20b"),
            confidence_cutoff=float(os.getenv("HEADROOM_CONFIDENCE_CUTOFF", "0.8")),
            near_breach_percent=float(os.getenv("HEADROOM_NEAR_BREACH_PERCENT", "10")),
            api_key=os.getenv("HEADROOM_API_KEY", ""),
        )

