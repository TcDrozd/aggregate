"""The closed sets of values the ledger uses.

Shared by the Pydantic schemas (as types) and the tables (as CHECK constraints),
so the two can't drift apart.
"""

from typing import Literal, get_args

AccountType = Literal["credit_card", "checking", "savings", "other"]
LinkRole = Literal["ledger", "signal"]
ParseStatus = Literal["pending", "parsed", "ignored", "unclassified", "unmapped_account", "error"]
ObservationStatus = Literal["pending", "posted"]
TransactionStatus = Literal["pending", "posted", "voided"]
MatchMethod = Literal["created", "same_external_id", "supersedes", "rule_match", "manual"]

# Payments and transfers never count as spending.
Kind = Literal[
    "purchase",
    "refund",
    "payment",
    "fee",
    "interest",
    "cashback",
    "transfer",
    "adjustment",
    "other",
]


def values(literal: object) -> tuple[str, ...]:
    """The allowed strings of a Literal type, in declaration order."""
    return tuple(str(v) for v in get_args(literal))
