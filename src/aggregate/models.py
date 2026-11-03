"""SQLAlchemy tables. Every change here ships with an Alembic migration.

Six tables: `raw_events` is append-only, `observations` are derived and rebuildable,
and `transactions` keep a stable id across reparses. See docs/SPEC.md → Data model.
"""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Dialect,
    Float,
    ForeignKey,
    Index,
    MetaData,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from aggregate.vocab import (
    AccountType,
    Kind,
    LinkRole,
    MatchMethod,
    ObservationStatus,
    ParseStatus,
    TransactionStatus,
    values,
)

# Named constraints keep Alembic's SQLite batch migrations deterministic.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """A timestamp stored as naive UTC and returned as an aware UTC datetime.

    Naive datetimes are rejected on write: without an offset, nobody can say
    which instant they mean.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("naive datetime: timestamps must carry a timezone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"expected a datetime from the database, got {type(value).__name__}")
        return value.replace(tzinfo=UTC)


def one_of(column: str, literal: object) -> CheckConstraint:
    """CHECK that a text column holds one of a Literal type's values."""
    allowed = ", ".join(f"'{v}'" for v in values(literal))
    return CheckConstraint(f"{column} IN ({allowed})", name=column)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Account(Base):
    """One row per real account."""

    __tablename__ = "accounts"
    __table_args__ = (one_of("type", AccountType),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String)
    institution: Mapped[str] = mapped_column(String)
    type: Mapped[AccountType] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String, default="USD")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AccountLink(Base):
    """Maps a connector's identifier for an account (`account_ref`) to the account."""

    __tablename__ = "account_links"
    __table_args__ = (one_of("role", LinkRole),)

    connector: Mapped[str] = mapped_column(String, primary_key=True)
    external_ref: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    role: Mapped[LinkRole] = mapped_column(String)


class RawEvent(Base):
    """Every inbound payload, verbatim. Only the parse_* columns ever change."""

    __tablename__ = "raw_events"
    __table_args__ = (
        UniqueConstraint("connector", "dedupe_key"),
        one_of("parse_status", ParseStatus),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connector: Mapped[str] = mapped_column(String)
    dedupe_key: Mapped[str] = mapped_column(String)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    parse_status: Mapped[ParseStatus] = mapped_column(String, default="pending", index=True)
    parse_reason: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[int | None]
    parsed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Observation(Base):
    """One connector's normalized claim about one transaction."""

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("connector", "external_id"),
        one_of("status", ObservationStatus),
        one_of("kind", Kind),
        Index("ix_observations_account_id_local_date", "account_id", "local_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_event_id: Mapped[int] = mapped_column(ForeignKey("raw_events.id"))
    connector: Mapped[str] = mapped_column(String)
    parser_version: Mapped[int]
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    external_id: Mapped[str] = mapped_column(String)
    supersedes_external_id: Mapped[str | None] = mapped_column(String)
    status: Mapped[ObservationStatus] = mapped_column(String)
    kind: Mapped[Kind] = mapped_column(String)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String, default="USD")
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    local_date: Mapped[date] = mapped_column(Date)
    posted_on: Mapped[date | None] = mapped_column(Date)
    merchant_display: Mapped[str | None] = mapped_column(String)
    merchant_key: Mapped[str | None] = mapped_column(String, index=True)
    location: Mapped[str | None] = mapped_column(String)
    category_hint: Mapped[str | None] = mapped_column(String)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    retracted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Transaction(Base):
    """A canonical ledger row. Only reconcile.py writes this table."""

    __tablename__ = "transactions"
    __table_args__ = (
        one_of("status", TransactionStatus),
        one_of("kind", Kind),
        Index("ix_transactions_account_id_local_date", "account_id", "local_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    status: Mapped[TransactionStatus] = mapped_column(String, index=True)
    kind: Mapped[Kind] = mapped_column(String)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String)
    local_date: Mapped[date] = mapped_column(Date)
    posted_on: Mapped[date | None] = mapped_column(Date)
    merchant_display: Mapped[str | None] = mapped_column(String)
    merchant_key: Mapped[str | None] = mapped_column(String)
    # User-owned: recompute never overwrites these.
    category: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(Text)
    needs_review: Mapped[bool] = mapped_column(default=False)
    review_reason: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class TransactionLink(Base):
    """Which observations back which transaction. Only reconcile.py writes this table.

    No ON DELETE cascade: deleting a still-linked observation fails, so the
    reconciler has to unlink it first.
    """

    __tablename__ = "transaction_links"
    __table_args__ = (one_of("match_method", MatchMethod),)

    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    match_method: Mapped[MatchMethod] = mapped_column(String)
    match_score: Mapped[float | None] = mapped_column(Float)  # rule matches only; not money
    linked_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
