"""Dollar strings to integer cents: exact, or an error."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aggregate.money import parse_dollars


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("$12.34", 1234),
        ("$1,234.56", 123456),
        ("$1234.56", 123456),
        ("$0.99", 99),
        ("0.00", 0),
        ("-0.00", 0),
        ("-12.34", -1234),
        ("-$12.34", -1234),
        ("$1,000,000.01", 100000001),
    ],
)
def test_parses_dollar_amounts(text: str, cents: int) -> None:
    assert parse_dollars(text) == cents


@pytest.mark.parametrize(
    "text",
    [
        "",
        "12",
        "12.3",
        "$12.345",
        "$12.",
        "$.99",
        "1,23.45",
        "12,34",
        "$1,2345.00",
        "$ 12.34",
        " $12.34",
        "$12.34 ",
        "+12.34",
        "$-12.34",
        "--12.34",
        "NaN",
        "Infinity",
        "1e3.00",
        "\u0661\u0662.\u0663\u0664",  # Arabic-Indic digits, which Decimal would accept
    ],
)
def test_rejects_anything_else(text: str) -> None:
    with pytest.raises(ValueError, match="two decimal places"):
        parse_dollars(text)


def test_the_error_message_leaves_the_amount_out() -> None:
    with pytest.raises(ValueError, match="dollar amount") as error:
        parse_dollars("$98,765.4")

    assert "98" not in str(error.value)


@given(
    cents=st.integers(min_value=-(10**30), max_value=10**30),
    dollar_sign=st.booleans(),
    grouped=st.booleans(),
)
def test_any_valid_amount_parses_to_its_cents(cents: int, dollar_sign: bool, grouped: bool) -> None:
    dollars, remainder = divmod(abs(cents), 100)
    whole = f"{dollars:,}" if grouped else str(dollars)
    text = f"{'-' if cents < 0 else ''}{'$' if dollar_sign else ''}{whole}.{remainder:02d}"

    assert parse_dollars(text) == cents
