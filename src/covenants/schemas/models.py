"""Contracts shared by the CLI, API, providers, and deterministic engine."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CovenantType(StrEnum):
    LEVERAGE = "LEVERAGE"
    INTEREST_COVER = "INTEREST_COVER"
    DSCR = "DSCR"
    MIN_NET_WORTH = "MIN_NET_WORTH"
    CURRENT_RATIO = "CURRENT_RATIO"
    MAX_CAPEX = "MAX_CAPEX"
    OTHER = "OTHER"


class Clause(Record):
    clause_id: str
    heading: str
    text: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class CovenantDraft(Record):
    type: CovenantType
    operator: Literal["LTE", "GTE"]
    threshold: Decimal = Field(gt=0)
    unit: Literal["ratio", "currency", "percent"]
    test_frequency: Literal["quarterly"]
    effective_from: date
    effective_to: date | None
    clause_id: str = Field(min_length=1, max_length=40)
    quote: str = Field(min_length=1, max_length=20_000)
    confidence: float = Field(ge=0, le=1)
    supersedes_clause_id: str | None

    @model_validator(mode="after")
    def valid_period(self) -> "CovenantDraft":
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to precedes effective_from")
        return self

    @field_serializer("threshold", when_used="json")
    def numeric_threshold(self, value: Decimal) -> float:
        return float(value)


class ExtractionDraft(Record):
    covenants: list[CovenantDraft] = Field(max_length=500)


class Covenant(CovenantDraft):
    covenant_id: str
    status: Literal["verified", "unverified"]
    status_reason: str


class ExtractionMeta(Record):
    provider: str
    model: str
    prompt_version: str
    prompt_hash: str


class Usage(Record):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0, ge=0)
    calls: int = Field(default=0, ge=0)
    failed_calls: int = Field(default=0, ge=0)

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.latency_ms += other.latency_ms
        self.calls += other.calls
        self.failed_calls += other.failed_calls


class ExtractionResult(Record):
    agreement_id: str
    clauses: list[Clause]
    covenants: list[Covenant]
    extraction_meta: ExtractionMeta
    usage: Usage
    issues: list[str] = Field(default_factory=list)
    repair_attempts: int = Field(default=0, ge=0)


class AgreementInput(Record):
    text: str = Field(min_length=1, max_length=200_000)

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agreement must not be blank")
        return value


class CheckInput(Record):
    period_end: date
    financials: dict[str, Decimal]

    @field_validator("financials")
    @classmethod
    def finite_financials(cls, values: dict[str, Decimal]) -> dict[str, Decimal]:
        if len(values) > 30 or any(not v.is_finite() for v in values.values()):
            raise ValueError("financials must contain at most 30 finite numbers")
        return values


class CheckResult(Record):
    covenant_id: str
    type: CovenantType
    computed_value: Decimal | None
    applicable_threshold: Decimal | None
    status: Literal["PASS", "NEAR_BREACH", "BREACH", "NEEDS_REVIEW"]
    headroom_percent: Decimal | None
    clause_id: str
    quote: str
    reason: str

    @field_serializer("computed_value", "applicable_threshold", "headroom_percent", when_used="json")
    def numeric_values(self, value: Decimal | None) -> float | None:
        return None if value is None else float(value)

