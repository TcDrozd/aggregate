# aggregate

A small, self-hosted service that merges card transactions from several sources into one ledger you can trust.

Each source is a **connector**. Every payload a connector receives is stored verbatim before anything parses it, so when a source changes its format, fixing the parser and replaying is enough: nothing is lost. A reconciler turns what connectors report into canonical transactions.

> **Status:** Phase 1 in progress. The schema, the connector framework and the Wallet notification parser are in place; ingest, reconciliation and the API land next. See [`docs/SPEC.md`](docs/SPEC.md).

Not affiliated with, endorsed by or sponsored by Apple, Chase or Plaid.

## Sources

| Phase | Source | How |
| --- | --- | --- |
| 1 | iPhone Wallet notifications (Apple Card) | An iOS Shortcuts automation POSTs each notification as JSON |
| 2 | Apple Card monthly statement CSV | Import |
| 3 | Plaid (Chase) | Sync and webhooks |

## Wallet notification payload

The Shortcut sends each Wallet notification as one flat JSON object. The connector reads five keys, `App`, `Title`, `Subtitle`, `Body` and `Date`, ignoring their case and spacing; every other key is stored but not read.

```json
{"Date":"2026-10-28T12:30:00-04:00","Body":"$12.34","Title":"Apple Card","Subtitle":"Example Diner, Springfield, IL","App":"Wallet"}
```

- **Purchase:** `Body` is a dollar amount like `$12.34` or `$1,234.56`, and `Subtitle` names the merchant, optionally followed by `, City, ST`. `Title` names the card, and `Date` must be ISO 8601 with an offset.
- **Ignored:** notifications from other apps, Daily Cash deposits, Savings notices, weekly and monthly spending summaries, and Apple Pay order tracking.
- **Everything else** is stored and sent to review.

## Quickstart (Docker)

```sh
cp .env.example .env    # then fill it in
mkdir -p data           # the container runs as uid 1000 and must be able to write here
docker compose up -d --build
curl -fsS http://127.0.0.1:8000/healthz
```

The database lives in `./data/aggregate.db`. Back up `./data`, and treat backups as sensitive as the database itself.

## Development

Needs [uv](https://docs.astral.sh/uv/) and `make`.

```sh
make setup    # install dependencies and pre-commit hooks
make check    # lint, type check, tests with coverage, migration check: the same steps as CI
make run      # serve locally with auto-reload
```

`make help` lists every target.

Real captures make the best regression tests, but they never belong in the repository. Put them in the gitignored `tests/fixtures/private/wallet_captures.jsonl`, one per line as `{"expect": "parsed", "payload": {...}}` or with an expected outcome such as `"ignored/daily_cash"`. `make test` runs them locally, and CI skips them.

## Configuration

Settings come from environment variables with the `AGGREGATE_` prefix, or from `.env` in development. See [`.env.example`](.env.example).

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGGREGATE_DATABASE_URL` | `sqlite:///data/aggregate.db` (Docker: `/data/aggregate.db`) | SQLAlchemy database URL |

## Security

- Keep the service on a private network. Never expose it to the internet without TLS and the token check in front.
- Every route except `/healthz` will require a bearer token. Ingest and read access use separate tokens.
- Payloads are financial data: logs carry ids and statuses only.
- Real transactions never belong in this repository, including test fixtures. Real captures for local testing go in the gitignored `tests/fixtures/private/`.

## License

[MIT](LICENSE)
