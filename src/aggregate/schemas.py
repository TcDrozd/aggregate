"""Pydantic models: the connector contract and API responses."""

from datetime import date
from typing import Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictInt,
    model_validator,
)

from aggregate.vocab import Kind, ObservationStatus, ParseOutcome

# Kinds whose sign never depends on the account. The rest can go either way: a payment is
# money in on a card and money out of checking, and savings earn interest that a card charges.
MONEY_OUT: frozenset[Kind] = frozenset({"purchase", "fee"})
MONEY_IN: frozenset[Kind] = frozenset({"refund", "cashback"})


class ObservationIn(BaseModel):
    """One connector's claim about one transaction, before the pipeline stores it.

    `account_ref` is the connector's own name for the account; the pipeline resolves it
    through `account_links`. Money is integer cents, negative for money out.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    account_ref: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    supersedes_external_id: str | None = None
    status: ObservationStatus
    kind: Kind
    amount_cents: StrictInt  # a plain int field would accept 12.0, "12" and True
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    occurred_at: AwareDatetime | None = None
    local_date: date
    posted_on: date | None = None
    merchant_display: str | None = None
    merchant_key: str | None = None
    location: str | None = None
    category_hint: str | None = None
    extra: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def _sign_matches_kind(self) -> Self:
        if self.kind in MONEY_OUT and self.amount_cents > 0:
            raise ValueError(f"a {self.kind} is money out, so amount_cents must not be positive")
        if self.kind in MONEY_IN and self.amount_cents < 0:
            raise ValueError(f"a {self.kind} is money in, so amount_cents must not be negative")
        return self


class ParseResult(BaseModel):
    """What `Connector.parse` returns for one payload.

    `parsed` carries one or more observations; every other outcome carries a reason
    and no observations, so the review queue can say why a payload was set aside.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ParseOutcome
    reason: str | None = None
    observations: list[ObservationIn] = []

    @classmethod
    def parsed(cls, *observations: ObservationIn) -> Self:
        return cls(status="parsed", observations=list(observations))

    @classmethod
    def ignored(cls, reason: str) -> Self:
        return cls(status="ignored", reason=reason)

    @classmethod
    def unclassified(cls, reason: str) -> Self:
        return cls(status="unclassified", reason=reason)

    @model_validator(mode="after")
    def _outcome_is_consistent(self) -> Self:
        if self.status != "parsed":
            if self.observations:
                raise ValueError(f"a {self.status} result carries no observations")
            if not self.reason:
                raise ValueError(f"a {self.status} result needs a reason")
            return self
        if not self.observations:
            raise ValueError("a parsed result needs at least one observation")
        external_ids = [o.external_id for o in self.observations]
        if len(set(external_ids)) != len(external_ids):
            raise ValueError("external_id must be unique within a result")
        return self


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorBody(BaseModel):
    """The one shape every error response uses."""

    error: ErrorDetail


class Health(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
