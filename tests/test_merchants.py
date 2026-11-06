"""merchant_key: one key for one merchant, whatever the source's spelling."""

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from aggregate.merchants import merchant_key


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Example Diner", "example diner"),
        ("Joe\u2019s Diner", "joes diner"),  # iOS's curly apostrophe
        ("Joe's Diner", "joes diner"),
        ("JOES DINER", "joes diner"),
        ("Joe\u02bcs Diner", "joes diner"),  # modifier letter apostrophe
        ("Joe\uff07s Diner", "joes diner"),  # full-width apostrophe, via NFKC
        ("\u201cQuoted\u201d Cafe", "quoted cafe"),
        ("ACME*STORE #0042", "acme store 0042"),
        ("Bait_and_Tackle", "bait and tackle"),
        ("  Spaced   Out  ", "spaced out"),
        ("Caf\u00e9", "caf\u00e9"),  # letters outside ASCII are kept
        ("Cafe\u0301", "caf\u00e9"),  # decomposed input composes to the same key
        ("\ufb01ne Foods", "fine foods"),  # the "fi" ligature, via NFKC
        ("Example Diner, Springfield", "example diner springfield"),
        ("!!!", ""),
    ],
)
def test_merchant_key(name: str, key: str) -> None:
    assert merchant_key(name) == key


@given(st.text())
@example("\u1100'\u1161")  # jamo that compose only once the apostrophe is gone
def test_applying_it_twice_changes_nothing(name: str) -> None:
    key = merchant_key(name)

    assert merchant_key(key) == key


@given(st.text())
def test_keys_are_words_separated_by_single_spaces(name: str) -> None:
    key = merchant_key(name)

    assert key == key.strip()
    assert "  " not in key
    assert all(char == " " or char.isalnum() for char in key)
    assert key == key.lower()
