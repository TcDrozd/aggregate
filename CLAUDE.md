# aggregate

Connector-based personal finance ledger. Spec: `docs/SPEC.md` (read the relevant section before changing a module). Decisions and their reasons: `docs/decisions.md`.

## Commands
- `make setup` once; `make check` before every commit (same steps as CI)
- `make test` for tests only; `make migrate` to apply migrations
- `make fmt` to format and apply safe lint fixes

## Rules
- Public repo: no secrets, real transactions, hostnames or personal data anywhere, including fixtures, commit messages and PR descriptions
- Money is integer cents; negative = money out. Never use float for money
- Only `reconcile.py` writes `transactions` and `transaction_links`
- `raw_events` is append-only: never update `payload`
- Every schema change ships with an Alembic migration; `alembic check` must pass
- Work on a branch and open a PR with `gh`; never push to `main`, never merge a PR. Trevor reviews and merges every PR
- Ask before changing a table, a column's meaning or a convention; log agreed changes in `docs/decisions.md` and update `docs/SPEC.md`
- No new dependencies without asking
- Deployment details (hosts, relays) belong in the gitignored `CLAUDE.local.md`, never here

## Gotchas
- A Stop hook (`.claude/hooks/stop-check.sh`) runs `make check` when a turn ends with uncommitted changes, and blocks once on failure
- `aggregate db upgrade` finds `alembic.ini` relative to the source tree, so the project must be installed editable (the default for `uv sync`)
- SQLite needs `PRAGMA foreign_keys=ON` per connection; `db.make_engine` sets it, so always create engines through it
