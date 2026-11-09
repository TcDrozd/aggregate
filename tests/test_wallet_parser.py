"""The Wallet notification connector, against synthetic fixtures and local real captures."""

import copy
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aggregate.connectors import default_registry
from aggregate.connectors.wallet_notification import PURCHASE_BODY, WalletNotification
from aggregate.merchants import merchant_key
from aggregate.schemas import ParseResult

FIXTURES = Path(__file__).parent / "fixtures"
CAPTURES = FIXTURES / "private" / "wallet_captures.jsonl"
wallet = WalletNotification()


@dataclass(frozen=True)
class Purchase:
    amount_cents: int
    merchant: str
    location: str | None
    local_date: date
    account_ref: str = "Apple Card"


# Parser-level results. The pipeline tests add the rest of the spec's table:
# `unmapped_title` becomes `unmapped_account`, and `chase_signal` creates no transaction.
EXPECTED: dict[str, Purchase | tuple[str, str]] = {
    "purchase": Purchase(-1234, "Example Diner", "Springfield, IL", date(2026, 10, 28)),
    "other_app": ("ignored", "non_wallet_app"),
    "online_no_location": Purchase(-999, "Example Streaming", None, date(2026, 10, 29)),
    "comma_merchant": Purchase(-4500, "Example Diner, Inc.", "Springfield, IL", date(2026, 10, 29)),
    "thousands": Purchase(-123456, "Example Furniture", "Springfield, IL", date(2026, 10, 30)),
    "unknown_shape": ("unclassified", "unknown_shape"),
    "unmapped_title": Purchase(
        -789, "Example Market", "Springfield, IL", date(2026, 10, 30), account_ref="Example Card"
    ),
    "curly_apostrophe": Purchase(-1840, "Joe\u2019s Diner", "Springfield, IL", date(2026, 10, 31)),
    "late_night": Purchase(-2150, "Example Pizza", None, date(2026, 10, 28)),
    "chase_signal": Purchase(
        -567, "Example Market", "Springfield, IL", date(2026, 11, 2), account_ref="Chase"
    ),
    "daily_cash": ("ignored", "daily_cash"),
    "savings_interest": ("ignored", "savings"),
    "spending_summary": ("ignored", "spending_summary"),
    "order_tracking": ("ignored", "order_tracking"),
}


def fixture(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((FIXTURES / "wallet" / f"{name}.json").read_text())
    return payload


def purchase(**fields: Any) -> dict[str, Any]:
    """purchase.json with some fields replaced, by their payload key."""
    return fixture("purchase") | fields


def outcome(payload: dict[str, Any]) -> tuple[str, str | None]:
    result = wallet.parse(payload)
    return result.status, result.reason


def test_every_fixture_has_an_expectation() -> None:
    assert {path.stem for path in (FIXTURES / "wallet").glob("*.json")} == set(EXPECTED)


@pytest.mark.parametrize("name", EXPECTED)
def test_fixture_gives_its_expected_result(name: str) -> None:
    payload, expected = fixture(name), EXPECTED[name]

    result = wallet.parse(payload)

    if not isinstance(expected, Purchase):
        assert (result.status, result.reason, result.observations) == (*expected, [])
        return
    assert result.status == "parsed"
    [obs] = result.observations
    assert obs.account_ref == expected.account_ref
    assert obs.external_id == wallet.dedupe_key(payload)
    assert (obs.status, obs.kind, obs.currency) == ("pending", "purchase", "USD")
    assert obs.amount_cents == expected.amount_cents
    assert obs.merchant_display == expected.merchant
    assert obs.merchant_key == merchant_key(expected.merchant)
    assert obs.location == expected.location
    assert obs.local_date == expected.local_date
    assert obs.occurred_at == datetime.fromisoformat(payload["Date"])
    assert obs.occurred_at is not None
    assert obs.occurred_at.tzinfo is UTC


def test_purchase_matches_the_acceptance_criteria() -> None:
    [obs] = wallet.parse(fixture("purchase")).observations

    assert obs.model_dump(exclude={"external_id"}) == {
        "account_ref": "Apple Card",
        "supersedes_external_id": None,
        "status": "pending",
        "kind": "purchase",
        "amount_cents": -1234,
        "currency": "USD",
        "occurred_at": datetime(2026, 10, 28, 16, 30, tzinfo=UTC),
        "local_date": date(2026, 10, 28),
        "posted_on": None,
        "merchant_display": "Example Diner",
        "merchant_key": "example diner",
        "location": "Springfield, IL",
        "category_hint": None,
        "extra": None,
    }


def test_late_night_keeps_the_payloads_own_date() -> None:
    [obs] = wallet.parse(fixture("late_night")).observations

    assert obs.occurred_at == datetime(2026, 10, 29, 3, 45, tzinfo=UTC)
    assert obs.local_date == date(2026, 10, 28)


def test_curly_and_straight_apostrophes_give_one_merchant_key() -> None:
    curly = fixture("curly_apostrophe")
    straight = curly | {"Subtitle": curly["Subtitle"].replace("\u2019", "'")}

    [curly_obs] = wallet.parse(curly).observations
    [straight_obs] = wallet.parse(straight).observations

    assert curly_obs.merchant_key == straight_obs.merchant_key == "joes diner"


def test_dedupe_key_recipe_is_frozen() -> None:
    # If this fails, the recipe changed: every stored Wallet observation would be orphaned.
    # SHA-256 of:
    #   Wallet|Apple Card|Example Diner, Springfield, IL|$12.34|2026-10-28T12:30:00-04:00
    expected = "8411e78711544d11cf5258a37c4f5e7e52c4116fe1104221ba1c5597170911bc"
    assert wallet.dedupe_key(fixture("purchase")) == expected
    # Missing fields read as empty strings: SHA-256 of "||||".
    assert wallet.dedupe_key({}) == (
        "45ca31c3315a5978f40438aab46040d75e99c9b125c2fd01db6e10ac80bef906"
    )


def test_dedupe_key_ignores_key_spelling_order_and_unread_keys() -> None:
    reordered = {
        " DATE ": "2026-10-28T12:30:00-04:00",
        "subtitle": "Example Diner, Springfield, IL",
        "App": "Wallet",
        "TITLE": "Apple Card",
        "Body  ": "$12.34",
        "Name": "something else",
        "Extra Key": {"nested": [1, 2]},
    }

    assert wallet.dedupe_key(reordered) == wallet.dedupe_key(fixture("purchase"))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("App", "Wallet "),
        ("Title", "Apple card"),
        ("Subtitle", "Example Diner, Springfield, IL "),
        ("Body", "$12.35"),
        ("Date", "2026-10-28T12:30:01-04:00"),
    ],
)
def test_dedupe_key_changes_with_any_read_value(key: str, value: str) -> None:
    # Values are hashed verbatim, untrimmed.
    assert wallet.dedupe_key(purchase(**{key: value})) != wallet.dedupe_key(fixture("purchase"))


def test_null_reads_as_missing_and_other_values_as_json() -> None:
    assert wallet.dedupe_key({"Title": None}) == wallet.dedupe_key({})
    assert wallet.dedupe_key({"Title": 5}) == wallet.dedupe_key({"Title": "5"})
    assert wallet.dedupe_key({"Title": {"b": 1, "a": [True]}}) == wallet.dedupe_key(
        {"Title": '{"a":[true],"b":1}'}
    )


def test_keys_match_whatever_their_case_and_spacing() -> None:
    payload = {
        " APP ": "Wallet",
        "title": "Apple Card",
        "SubTitle": "Example Diner, Springfield, IL",
        "BODY  ": "$12.34",
        "  Date": "2026-10-28T12:30:00-04:00",
    }

    assert wallet.parse(payload) == wallet.parse(fixture("purchase"))


def test_an_empty_payload_is_not_from_wallet() -> None:
    assert outcome({}) == ("ignored", "non_wallet_app")


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"Title": "Daily\u00a0Cash"}, "daily_cash"),  # how Apple actually writes it
        ({"Title": "Daily Cash"}, "daily_cash"),
        ({"Title": "Savings Account", "Subtitle": "Interest Paid"}, "savings"),
        ({"Subtitle": "Weekly Spending"}, "spending_summary"),
        ({"Subtitle": "Monthly Spending"}, "spending_summary"),
        ({"Title": "Order shipped"}, "order_tracking"),
        ({"Title": "Order ready for pickup"}, "order_tracking"),
        ({"Title": "Problem with your order"}, "order_tracking"),
    ],
)
def test_known_non_transactions_are_ignored(fields: dict[str, str], reason: str) -> None:
    # Even in the purchase shape: these rules run first.
    assert outcome(purchase(**fields)) == ("ignored", reason)


def test_only_the_wallet_app_counts() -> None:
    assert outcome(purchase(App="wallet")) == ("ignored", "non_wallet_app")
    assert outcome(purchase(App=["Wallet"])) == ("ignored", "non_wallet_app")


def test_whitespace_in_the_title_does_not_change_the_account() -> None:
    [obs] = wallet.parse(purchase(Title=" Apple\u00a0 Card ")).observations

    assert obs.account_ref == "Apple Card"


@pytest.mark.parametrize(
    "fields",
    [
        {"Body": "$12"},
        {"Body": "12.34"},
        {"Body": "$12.345"},
        {"Body": "$12.3"},
        {"Body": "-$12.34"},
        {"Body": "$ 12.34"},
        {"Body": "$1,23.45"},
        {"Body": "$12.34 "},
        {"Body": "$12.34\n"},  # `$` in a regex would accept this
        {"Body": "$\u0661\u0662.\u0663\u0664"},  # Arabic-Indic digits
        {"Body": "$12.34 at Example Diner"},
        {"Subtitle": ""},
        {"Subtitle": " \u00a0 "},
        {"Title": ""},
        {"Title": "Orders", "Body": "Your orders are ready."},  # "Order " needs the space
        {"Title": 7},
        {"Subtitle": ["Example Diner"]},
        {"Body": 12.34},
    ],
)
def test_anything_else_is_unclassified(fields: dict[str, Any]) -> None:
    assert outcome(purchase(**fields)) == ("unclassified", "unknown_shape")


def test_a_field_sent_twice_is_unclassified() -> None:
    payload = fixture("purchase") | {"body": "$99.99"}

    assert outcome(payload) == ("unclassified", "unknown_shape")
    # The dedupe key still works, with the later value.
    assert wallet.dedupe_key(payload) == wallet.dedupe_key(purchase(Body="$99.99"))


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not a date",
        "Oct 28, 2026 at 12:30 PM",
        "2026-10-28",
        "2026-10-28T12:30:00",  # no offset: names no instant
        "0001-01-01T00:00:00+01:00",  # before year 1 in UTC
        "9999-12-31T23:59:59-01:00",  # after year 9999 in UTC
    ],
)
def test_a_purchase_without_a_usable_date_is_unclassified(value: str) -> None:
    assert outcome(purchase(Date=value)) == ("unclassified", "invalid_date")


def test_a_utc_date_is_accepted() -> None:
    [obs] = wallet.parse(purchase(Date="2026-10-28T16:30:00Z")).observations

    assert obs.occurred_at == datetime(2026, 10, 28, 16, 30, tzinfo=UTC)
    assert obs.local_date == date(2026, 10, 28)


@pytest.mark.parametrize(
    ("subtitle", "merchant", "location"),
    [
        ("Example Diner, Springfield, il", "Example Diner, Springfield, il", None),
        ("Example Diner, IL", "Example Diner, IL", None),
        ("Example - Spri, Springfie", "Example - Spri, Springfie", None),  # truncated
        ("  Example Diner,  Springfield,  IL ", "Example Diner", "Springfield, IL"),
    ],
)
def test_merchant_and_location(subtitle: str, merchant: str, location: str | None) -> None:
    [obs] = wallet.parse(purchase(Subtitle=subtitle)).observations

    assert (obs.merchant_display, obs.location) == (merchant, location)


def test_a_merchant_without_letters_or_digits_has_no_key() -> None:
    [obs] = wallet.parse(purchase(Subtitle="!!!")).observations

    assert (obs.merchant_display, obs.merchant_key) == ("!!!", None)


def test_parsing_is_pure() -> None:
    payload = fixture("purchase")
    original = copy.deepcopy(payload)

    assert wallet.parse(payload) == wallet.parse(payload)
    assert payload == original


def test_the_default_registry_serves_wallet() -> None:
    assert isinstance(default_registry()["wallet_notification"], WalletNotification)


@given(cents=st.integers(min_value=0, max_value=10**15), grouped=st.booleans())
def test_any_wallet_amount_becomes_negative_cents(cents: int, grouped: bool) -> None:
    dollars, remainder = divmod(cents, 100)
    body = f"${dollars:,}.{remainder:02d}" if grouped else f"${dollars}.{remainder:02d}"

    [obs] = wallet.parse(purchase(Body=body)).observations

    assert obs.amount_cents == -cents


json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(),
    lambda children: st.lists(children, max_size=3) | st.dictionaries(st.text(), children),
    max_leaves=5,
)
offsets = st.timedeltas(min_value=timedelta(hours=-23), max_value=timedelta(hours=23))
dates = st.datetimes(timezones=st.builds(timezone, offsets)).map(datetime.isoformat)


def field(*known: str) -> st.SearchStrategy[Any]:
    return st.sampled_from(known) | st.text() | json_values


payloads = st.builds(
    lambda extra, read: extra | read,
    st.dictionaries(st.text(), json_values, max_size=3),
    st.fixed_dictionaries(
        {
            "App": field("Wallet"),
            "Title": field("Apple Card", "Daily\u00a0Cash", "Savings Account", "Order placed"),
            "Subtitle": field("Example Diner, Springfield, IL", "Weekly Spending", ""),
            "Body": st.from_regex(PURCHASE_BODY, fullmatch=True) | field("$12.34"),
            "Date": dates | field("2026-10-28T12:30:00-04:00"),
        }
    ),
)


@given(payloads)
def test_no_payload_makes_the_parser_raise(payload: dict[str, Any]) -> None:
    key = wallet.dedupe_key(payload)
    result = wallet.parse(payload)

    assert re.fullmatch(r"[0-9a-f]{64}", key)
    assert isinstance(result, ParseResult)
    assert result.status != "error"
    for obs in result.observations:
        assert obs.external_id == key
        assert obs.amount_cents <= 0


def captures() -> list[Any]:
    if not CAPTURES.exists():
        return []
    lines = CAPTURES.read_text().splitlines()
    return [pytest.param(json.loads(line), id=f"line{n}") for n, line in enumerate(lines, 1)]


@pytest.mark.private
@pytest.mark.parametrize("capture", captures())
def test_real_capture_gives_its_labelled_result(capture: dict[str, Any]) -> None:
    """Each line of the gitignored captures file: {"expect": "parsed" | "STATUS/REASON", ...}."""
    payload = capture["payload"]

    result = wallet.parse(payload)

    if capture["expect"] != "parsed":
        assert f"{result.status}/{result.reason}" == capture["expect"]
        return
    [obs] = result.observations
    assert obs.amount_cents < 0
    assert obs.local_date == date.fromisoformat(payload["Date"][:10])
    assert obs.external_id == wallet.dedupe_key(payload)
