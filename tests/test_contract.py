"""The connector contract: what a connector may return, and how the registry finds it."""

from datetime import UTC, date, datetime
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from aggregate.connectors.base import Payload, Registry
from aggregate.schemas import ObservationIn, ParseResult
from aggregate.vocab import ParseOutcome, ParseStatus, values


def observation(**overrides: Any) -> ObservationIn:
    fields: dict[str, Any] = {
        "account_ref": "Test Card",
        "external_id": "e1",
        "status": "pending",
        "kind": "purchase",
        "amount_cents": -1234,
        "local_date": date(2026, 10, 28),
    }
    return ObservationIn(**(fields | overrides))


class FakeConnector:
    name: ClassVar[str] = "fake"
    parser_version: ClassVar[int] = 1

    def dedupe_key(self, payload: Payload) -> str:
        return str(payload["id"])

    def parse(self, payload: Payload) -> ParseResult:
        return ParseResult.ignored("fake")


def connector_class(name: str, parser_version: Any = 1) -> type[FakeConnector]:
    return type("Custom", (FakeConnector,), {"name": name, "parser_version": parser_version})


def test_an_observation_fills_its_defaults() -> None:
    obs = observation()

    assert obs.currency == "USD"
    assert obs.occurred_at is None
    assert obs.extra is None


@pytest.mark.parametrize("amount", [12.0, -1234.0, "-1234", True])
def test_amount_cents_accepts_only_a_real_int(amount: Any) -> None:
    with pytest.raises(ValidationError, match="amount_cents"):
        observation(amount_cents=amount)


def test_occurred_at_must_carry_a_timezone() -> None:
    assert observation(occurred_at=datetime(2026, 10, 28, 16, 30, tzinfo=UTC)).occurred_at

    with pytest.raises(ValidationError, match="timezone"):
        observation(occurred_at=datetime(2026, 10, 28, 16, 30))  # noqa: DTZ001


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("account_ref", ""),
        ("external_id", ""),
        ("currency", "usd"),
        ("currency", "US"),
        ("status", "voided"),
        ("kind", "gift"),
        ("extra", {"tags": {"a", "b"}}),  # a set isn't JSON, and extra is stored as JSON
    ],
)
def test_observation_fields_are_validated(field: str, bad_value: Any) -> None:
    with pytest.raises(ValidationError, match=field):
        observation(**{field: bad_value})


def test_unknown_fields_are_rejected() -> None:
    # A typo in a connector fails loudly instead of dropping the value.
    with pytest.raises(ValidationError, match="amount"):
        observation(amount=-1234)


def test_observations_are_immutable() -> None:
    obs = observation()

    with pytest.raises(ValidationError, match="frozen"):
        obs.amount_cents = 0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kind", "amount_cents"),
    [("purchase", 100), ("fee", 1), ("refund", -100), ("cashback", -1)],
)
def test_sign_must_match_a_one_way_kind(kind: str, amount_cents: int) -> None:
    with pytest.raises(ValidationError, match=r"is money (in|out)"):
        observation(kind=kind, amount_cents=amount_cents)


@pytest.mark.parametrize(
    ("kind", "amount_cents"),
    [
        ("purchase", 0),  # a $0.00 card check
        ("refund", 0),
        ("payment", 5000),  # into a card
        ("payment", -5000),  # out of checking
        ("interest", -250),  # charged on a card
        ("interest", 250),  # earned on savings
        ("transfer", -1),
        ("adjustment", 1),
        ("other", -1),
    ],
)
def test_two_way_kinds_take_either_sign(kind: str, amount_cents: int) -> None:
    assert observation(kind=kind, amount_cents=amount_cents).amount_cents == amount_cents


def test_parsed_result_carries_its_observations() -> None:
    first, second = observation(external_id="a"), observation(external_id="b")

    result = ParseResult.parsed(first, second)

    assert result.status == "parsed"
    assert result.reason is None
    assert result.observations == [first, second]


@pytest.mark.parametrize("make", [ParseResult.ignored, ParseResult.unclassified])
def test_set_aside_results_carry_a_reason(make: Any) -> None:
    result = make("unknown_shape")

    assert result.reason == "unknown_shape"
    assert result.observations == []


def test_a_parsed_result_needs_an_observation() -> None:
    with pytest.raises(ValidationError, match="at least one observation"):
        ParseResult.parsed()


@pytest.mark.parametrize("status", ["ignored", "unclassified", "error"])
def test_a_set_aside_result_needs_a_reason_and_no_observations(status: str) -> None:
    with pytest.raises(ValidationError, match="needs a reason"):
        ParseResult(status=status)
    with pytest.raises(ValidationError, match="carries no observations"):
        ParseResult(status=status, reason="r", observations=[observation()])


def test_external_ids_are_unique_within_a_result() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ParseResult.parsed(observation(), observation(amount_cents=-1))


def test_parse_outcomes_are_parse_statuses() -> None:
    assert set(values(ParseOutcome)) < set(values(ParseStatus))


def test_registry_finds_connectors_by_name() -> None:
    fake = FakeConnector()
    other = connector_class("other_source", parser_version=3)()

    registry = Registry([fake, other])

    assert registry["fake"] is fake
    assert list(registry) == ["fake", "other_source"]
    assert len(registry) == 2
    assert "other_source" in registry
    assert registry.get("missing") is None
    assert registry["fake"].parse({"id": 1}).status == "ignored"


def test_registering_a_name_twice_fails() -> None:
    with pytest.raises(ValueError, match="registered twice"):
        Registry([FakeConnector(), FakeConnector()])


@pytest.mark.parametrize("name", ["", "Wallet", "wallet-notification", "1source", "a/b", "a "])
def test_names_must_be_url_and_column_safe(name: str) -> None:
    with pytest.raises(ValueError, match="must match"):
        Registry([connector_class(name)()])


@pytest.mark.parametrize("parser_version", [0, -1, True, 1.0, "1"])
def test_parser_version_must_be_a_positive_int(parser_version: Any) -> None:
    with pytest.raises(ValueError, match="parser_version"):
        Registry([connector_class("fake", parser_version)()])
