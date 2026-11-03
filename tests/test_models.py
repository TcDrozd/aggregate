"""The schema as the migration builds it: tables, keys, constraints and types."""

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest
from alembic import command
from sqlalchemy import Engine, Integer, inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from aggregate.db import alembic_config
from aggregate.models import (
    Account,
    AccountLink,
    Base,
    Observation,
    RawEvent,
    Transaction,
    TransactionLink,
    UTCDateTime,
)
from aggregate.vocab import Kind, values

TABLES = {
    "accounts",
    "account_links",
    "raw_events",
    "observations",
    "transactions",
    "transaction_links",
}
EDT = timezone(timedelta(hours=-4))


def make_account(session: Session, slug: str = "test-card") -> Account:
    account = Account(slug=slug, display_name="Test Card", institution="Test", type="credit_card")
    session.add(account)
    session.flush()
    return account


def make_raw_event(session: Session, dedupe_key: str = "k1", **overrides: Any) -> RawEvent:
    fields: dict[str, Any] = {
        "connector": "wallet_notification",
        "dedupe_key": dedupe_key,
        "payload": {"Body": "$12.34"},
    }
    raw = RawEvent(**(fields | overrides))
    session.add(raw)
    session.flush()
    return raw


def make_observation(session: Session, external_id: str = "e1", **overrides: Any) -> Observation:
    fields: dict[str, Any] = {
        "raw_event_id": make_raw_event(session, dedupe_key=external_id).id,
        "connector": "wallet_notification",
        "parser_version": 1,
        "account_id": make_account(session, slug=f"card-{external_id}").id,
        "external_id": external_id,
        "status": "pending",
        "kind": "purchase",
        "amount_cents": -1234,
        "local_date": date(2026, 10, 28),
    }
    observation = Observation(**(fields | overrides))
    session.add(observation)
    session.flush()
    return observation


def make_transaction(session: Session, account_id: int, **overrides: Any) -> Transaction:
    fields: dict[str, Any] = {
        "account_id": account_id,
        "status": "pending",
        "kind": "purchase",
        "amount_cents": -1234,
        "currency": "USD",
        "local_date": date(2026, 10, 28),
    }
    transaction = Transaction(**(fields | overrides))
    session.add(transaction)
    session.flush()
    return transaction


def test_migration_creates_the_six_tables(engine: Engine) -> None:
    assert set(inspect(engine).get_table_names()) == TABLES | {"alembic_version"}


def test_migration_downgrades_and_reapplies(engine: Engine, database_url: str) -> None:
    config = alembic_config(database_url)

    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}

    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names()) == TABLES | {"alembic_version"}


def test_every_connection_enforces_foreign_keys_in_wal_mode(engine: Engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_foreign_keys_are_enforced(session: Session) -> None:
    session.add(AccountLink(connector="c", external_ref="r", account_id=999, role="ledger"))

    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        session.flush()


def test_account_link_is_keyed_by_connector_and_external_ref(session: Session) -> None:
    account = make_account(session)
    session.add(
        AccountLink(connector="c", external_ref="Card", account_id=account.id, role="ledger")
    )
    session.add(
        AccountLink(connector="other", external_ref="Card", account_id=account.id, role="signal")
    )
    session.flush()

    session.add(
        AccountLink(connector="c", external_ref="Card", account_id=account.id, role="signal")
    )
    with pytest.raises(IntegrityError, match="UNIQUE"):
        session.flush()


def test_raw_events_are_unique_per_connector_and_dedupe_key(session: Session) -> None:
    make_raw_event(session, dedupe_key="same")
    make_raw_event(session, dedupe_key="same", connector="another_connector")

    with pytest.raises(IntegrityError, match="UNIQUE"):
        make_raw_event(session, dedupe_key="same")


def test_observations_are_unique_per_connector_and_external_id(session: Session) -> None:
    first = make_observation(session, external_id="dup")
    session.add(
        Observation(
            raw_event_id=first.raw_event_id,
            connector="wallet_notification",
            parser_version=1,
            account_id=first.account_id,
            external_id="dup",
            status="pending",
            kind="purchase",
            amount_cents=-1,
            local_date=date(2026, 10, 28),
        )
    )

    with pytest.raises(IntegrityError, match="UNIQUE"):
        session.flush()


def test_payload_round_trips_with_every_key_untouched(session: Session) -> None:
    payload = {"Recipient ": "", "Associated Content": "", "Subtitle": "Café Ünïcode, X, YZ"}
    raw_id = make_raw_event(session, payload=payload).id
    session.commit()
    session.expire_all()

    assert session.get_one(RawEvent, raw_id).payload == payload


@pytest.mark.parametrize(
    ("make", "attribute", "bad_value"),
    [
        (lambda s: make_account(s), "type", "loan"),
        (lambda s: make_raw_event(s), "parse_status", "done"),
        (lambda s: make_observation(s), "kind", "gift"),
        (lambda s: make_observation(s), "status", "voided"),
        (lambda s: make_transaction(s, make_account(s).id), "status", "cleared"),
    ],
)
def test_check_constraints_reject_values_outside_the_vocabulary(
    session: Session, make: Any, attribute: str, bad_value: str
) -> None:
    row = make(session)
    setattr(row, attribute, bad_value)

    with pytest.raises(IntegrityError, match="CHECK"):
        session.flush()


def test_link_role_and_match_method_are_checked(session: Session) -> None:
    account = make_account(session)
    session.add(AccountLink(connector="c", external_ref="r", account_id=account.id, role="owner"))
    with pytest.raises(IntegrityError, match="CHECK"):
        session.flush()
    session.rollback()

    observation = make_observation(session)
    transaction = make_transaction(session, observation.account_id)
    session.add(
        TransactionLink(
            observation_id=observation.id, transaction_id=transaction.id, match_method="guess"
        )
    )
    with pytest.raises(IntegrityError, match="CHECK"):
        session.flush()


def test_an_observation_backs_at_most_one_transaction(session: Session) -> None:
    observation = make_observation(session)
    first = make_transaction(session, observation.account_id)
    second = make_transaction(session, observation.account_id)
    session.add(
        TransactionLink(
            observation_id=observation.id, transaction_id=first.id, match_method="created"
        )
    )
    session.flush()
    session.expunge_all()

    session.add(
        TransactionLink(
            observation_id=observation.id, transaction_id=second.id, match_method="manual"
        )
    )
    with pytest.raises(IntegrityError, match="UNIQUE"):
        session.flush()


def test_a_linked_observation_cannot_be_deleted(session: Session) -> None:
    # The reconciler must unlink an observation before a reparse deletes it.
    observation = make_observation(session)
    transaction = make_transaction(session, observation.account_id)
    session.add(
        TransactionLink(
            observation_id=observation.id, transaction_id=transaction.id, match_method="created"
        )
    )
    session.flush()

    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        session.execute(text("DELETE FROM observations WHERE id = :id"), {"id": observation.id})


def test_timestamps_are_stored_in_utc_and_read_back_aware(session: Session) -> None:
    observation_id = make_observation(
        session, occurred_at=datetime(2026, 10, 28, 12, 30, tzinfo=EDT)
    ).id
    session.commit()
    session.expire_all()

    occurred_at = session.get_one(Observation, observation_id).occurred_at
    assert occurred_at == datetime(2026, 10, 28, 16, 30, tzinfo=UTC)
    assert occurred_at is not None
    assert occurred_at.tzinfo is UTC
    stored = session.execute(
        text("SELECT occurred_at FROM observations WHERE id = :id"), {"id": observation_id}
    ).scalar()
    assert str(stored).startswith("2026-10-28 16:30:00")


def test_naive_datetimes_are_rejected(session: Session) -> None:
    with pytest.raises(StatementError, match="naive datetime"):
        make_observation(session, occurred_at=datetime(2026, 10, 28, 12, 30))  # noqa: DTZ001


def test_utc_datetime_rejects_non_datetime_results(engine: Engine) -> None:
    with pytest.raises(TypeError, match="expected a datetime"):
        UTCDateTime().process_result_value("2026-10-28", engine.dialect)


def test_defaults_fill_created_and_updated_timestamps(session: Session) -> None:
    account = make_account(session)
    transaction = make_transaction(session, account.id)
    created = transaction.updated_at

    transaction.notes = "changed"
    session.flush()

    assert account.currency == "USD"
    assert transaction.created_at.tzinfo is UTC
    assert transaction.needs_review is False
    assert transaction.updated_at > created


def test_money_columns_are_integers() -> None:
    money = [
        column
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.name.endswith("_cents")
    ]

    assert {f"{c.table.name}.{c.name}" for c in money} == {
        "observations.amount_cents",
        "transactions.amount_cents",
    }
    assert all(isinstance(c.type, Integer) for c in money)


def test_vocabulary_values_keep_declaration_order() -> None:
    assert values(Kind)[:3] == ("purchase", "refund", "payment")
