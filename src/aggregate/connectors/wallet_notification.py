"""The Wallet notification connector: one Shortcuts payload per Wallet notification.

Phase 1 recognizes the purchase shape and four known non-transactions; everything else
is stored and sent to review. See docs/SPEC.md → Wallet notification connector.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import JsonValue

from aggregate.connectors.base import Payload
from aggregate.merchants import merchant_key
from aggregate.money import parse_dollars
from aggregate.schemas import ObservationIn, ParseResult

FIELDS = ("app", "title", "subtitle", "body", "date")

# fullmatch, not `$`: in Python `$` also matches before a trailing newline.
PURCHASE_BODY = re.compile(r"\$(\d{1,3}(,\d{3})*|\d+)\.\d{2}", re.ASCII)
MERCHANT_CITY_REGION = re.compile(r"(.+), ([^,]+), ([A-Z]{2})")

SPENDING_SUMMARIES = frozenset({"Weekly Spending", "Monthly Spending"})


def normalize_key(key: str) -> str:
    """` Recipient  ` → `recipient`, `Associated Content` → `associated_content`."""
    return "_".join(key.lower().split())


def as_text(value: JsonValue) -> str:
    """A field's value as text: strings verbatim, null as empty, anything else as JSON."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def squash(text: str) -> str:
    """Runs of any whitespace to one space, trimmed. Apple writes `Daily Cash` with U+00A0."""
    return " ".join(text.split())


def read_fields(payload: Payload) -> tuple[dict[str, str], bool]:
    """The five fields the connector reads, and whether each arrived once, as a string.

    Missing fields read as empty strings. When two keys normalize to the same field,
    the later one wins, so the result is still deterministic.
    """
    fields = dict.fromkeys(FIELDS, "")
    seen: set[str] = set()
    well_formed = True
    for key, value in payload.items():
        name = normalize_key(key)
        if name not in fields:
            continue
        if name in seen or not isinstance(value, str | None):
            well_formed = False
        seen.add(name)
        fields[name] = as_text(value)
    return fields, well_formed


def parse_date(text: str) -> datetime | None:
    """An ISO 8601 timestamp with an offset, or None. A naive time names no instant."""
    try:
        moment = datetime.fromisoformat(text)
        if moment.utcoffset() is None:
            return None
        moment.astimezone(UTC)  # an offset can push year 1 or 9999 out of range
    except (ValueError, OverflowError):
        return None
    return moment


class WalletNotification:
    name: ClassVar[str] = "wallet_notification"
    parser_version: ClassVar[int] = 1

    def dedupe_key(self, payload: Payload) -> str:
        """SHA-256 of `app|title|subtitle|body|date`. Frozen: it is also the external_id."""
        fields, _ = read_fields(payload)
        joined = "|".join(fields[name] for name in FIELDS)
        return hashlib.sha256(joined.encode()).hexdigest()

    def parse(self, payload: Payload) -> ParseResult:
        fields, well_formed = read_fields(payload)
        # Compared with whitespace squashed; the raw event and dedupe key keep the original.
        title, subtitle, body = squash(fields["title"]), squash(fields["subtitle"]), fields["body"]

        if fields["app"] != "Wallet":
            return ParseResult.ignored("non_wallet_app")
        if ignored := self._known_non_transaction(title, subtitle):
            return ParseResult.ignored(ignored)
        if not (well_formed and title and subtitle and PURCHASE_BODY.fullmatch(body)):
            return ParseResult.unclassified("unknown_shape")
        moment = parse_date(fields["date"])
        if moment is None:
            return ParseResult.unclassified("invalid_date")

        if match := MERCHANT_CITY_REGION.fullmatch(subtitle):
            merchant, location = match[1], f"{match[2]}, {match[3]}"
        else:
            merchant, location = subtitle, None

        return ParseResult.parsed(
            ObservationIn(
                account_ref=title,
                external_id=self.dedupe_key(payload),
                status="pending",
                kind="purchase",
                amount_cents=-parse_dollars(body),
                occurred_at=moment.astimezone(UTC),
                local_date=moment.date(),  # the date where the purchase happened
                merchant_display=merchant,
                merchant_key=merchant_key(merchant) or None,
                location=location,
            )
        )

    @staticmethod
    def _known_non_transaction(title: str, subtitle: str) -> str | None:
        """The reason for a notification real captures show is not a card transaction."""
        if title == "Daily Cash":
            return "daily_cash"  # deposits go to Savings, not the card
        if title == "Savings Account":
            return "savings"
        if subtitle in SPENDING_SUMMARIES:
            return "spending_summary"
        if title.startswith("Order ") or title == "Problem with your order":
            return "order_tracking"
        if title == "Verification Required":
            return "card_verification"  # a card in Wallet needs setup steps
        if subtitle == "Upcoming Transactions":
            return "upcoming_charges"  # a count of predicted charges, no amount or merchant
        return None
