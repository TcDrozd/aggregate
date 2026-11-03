# Decisions

Agreed changes to, and interpretations of, `docs/SPEC.md`. Newest last. `docs/SPEC.md` is kept current; this file records why.

## 2026-11-03 · Before the first commit

**D1. The project is named `aggregate` everywhere.** "finance" in Spec v1 was a placeholder. Package `src/aggregate/`, CLI `aggregate`, image `aggregate`, env prefix `AGGREGATE_`, database `/data/aggregate.db`.

**D2. Three dependencies added beyond the stack table.** `uvicorn` (the entrypoint serves with it), `httpx` (FastAPI's TestClient requires it; replaced by `httpx2` in D22) and `pre-commit` (`make setup` installs the hooks). gitleaks runs as a pre-commit hook and a checksum-verified binary in CI, not as a Python dependency.

**D3. Bootstrap and review flow.** The walking skeleton is the one commit pushed straight to `main`; an empty repository has nothing to open a pull request against, and branch protection can only require checks that have already run. Protection goes on once its CI is green. After that, every step is a pull request that Trevor reviews and merges.

**D4. CI runs on pushes to `main` and on pull requests**, not on every push to every branch, so a pull request's checks don't run twice.

**D5. The end-to-end check seeds explicitly.** On an empty `./data` there are no accounts, so `purchase.json` would land as `unmapped_account`. The README quickstart and the acceptance criterion run `aggregate seed` first; the entrypoint doesn't seed.

**D6. `merchant_key` removes apostrophes instead of turning them into spaces.** As written, `Joe’s` became `joe s`, which would never match a statement's `JOES`. Curly quotes are still straightened first, so `’` and `'` behave the same.

**D7. Reparse updates observations in place.** Keyed on (`connector`, `external_id`), so observation ids and transaction links survive a reparse. When a reparse stops producing an observation, it is unlinked and deleted, and a transaction left with none is flagged `needs_review` (`orphaned`). Transactions are never deleted.

**D8. Natural keys for the link tables.** `account_links` has primary key (`connector`, `external_ref`) and `transaction_links` has primary key `observation_id`. Both are lookup tables whose identity is already their natural key, nothing references them by id, and the primary key on `observation_id` makes "one observation backs one transaction" structural. `transactions.posted_on`, `merchant_display`, `merchant_key` and `review_reason` are nullable, since pending and online rows lack them.

**D9. The Stop hook skips clean trees and blocks once.** It runs `make check` only when the working tree has changes, so conversation-only turns stay fast. A failure blocks the turn once so Claude fixes it; if the check still fails on that retry, the turn ends with a warning rather than looping on something that needs a human.

**D10. Failures never lose a payload.** Ingest stays one DB transaction per payload, with parse, account resolution and reconciliation inside a savepoint. Any exception there, not only one from `parse()`, rolls back the savepoint and marks the raw event `error`.

**D11. "Ties go to the newest" means the highest observation `id`.** Observations have no timestamp of their own, and ids follow insertion order.

**D12. A connector's dedupe recipe is frozen once shipped.** Wallet uses its dedupe key as `external_id`, and `raw_events.dedupe_key` never changes, so a new recipe would orphan transactions. Recorded in `.claude/rules/connectors.md`.

**D13. Request errors.** Invalid or non-object JSON on ingest is a 400; invalid query parameters stay 422. Both use the error envelope.

**D14. CI generates throwaway tokens at run time**, so nothing in the workflow looks like a credential to gitleaks.

**D15. The architecture diagram is Mermaid** in `docs/SPEC.md`, redrawn from the original image so it renders on GitHub and diffs as text.

**D16. Four non-transaction Wallet shapes are ignored in Phase 1.** Real captures show that about half of all Wallet notifications are not card transactions: Daily Cash deposits (to Savings, not the card), Savings interest, weekly and monthly spending summaries, and Apple Pay order tracking. Left unclassified, they would fill the review queue daily. They are `ignored` with reasons `daily_cash`, `savings`, `spending_summary` and `order_tracking`; the raw payloads are kept, so a later parser version can reparse them, for example if a Savings account is added.

**D17. Chase's Wallet title is `Chase`, linked as `signal` by `aggregate seed`.** The title is generic, so it can live in the public seed. Chase notifications arrive in the purchase shape; the signal link stores them as evidence without creating transactions, and Plaid stays Chase's ledger source in Phase 3.

**D18. Filtering stays on the server.** The Shortcut filters only on the Wallet app. Filtering further on the phone with an allow list would silently drop purchases if Apple ever changes a notification's title or shape, and that defeats keeping every raw payload. A phone-side block list of known noise would be safe, but isn't needed.

**D19. The Shortcut keeps a local copy before posting.** It appends each payload to a note, then POSTs it. A failed POST leaves the note entry, which can be re-sent later; re-sending is a no-op for payloads already stored. The same applies to captures made before the service existed.

**D20. Deployment target: Docker on a Linux host**, behind a relay on the private network. The image runs as uid 1000; compose publishes on `127.0.0.1` by default and takes `AGGREGATE_UID`/`AGGREGATE_GID` for the bind mount's owner. The entrypoint stops with a clear message if `/data` isn't writable. Python 3.13 image.

**D21. The skeleton's Docker smoke test calls `/healthz` only.** POSTing `purchase.json` joins the smoke test with the ingest step, when the route exists.

## 2026-11-03 · After the skeleton

**D22. `httpx2` replaces `httpx` as the test client's HTTP library.** Starlette now deprecates `httpx` in its TestClient in favour of `httpx2`, Pydantic's maintained continuation of the same library under a new name; `httpx` itself has seen little activity. It's a dev-only dependency with the same API, and switching this early costs nothing.

## 2026-11-03 · Models and first migration

**D23. Timestamps use a `UTCDateTime` column type.** It stores naive UTC and returns aware UTC datetimes, and it rejects naive datetimes on write, since without an offset nobody can say which instant they mean. Migrations render it as a plain `sa.DateTime()`, so they never import application code.

**D24. Closed vocabularies are text columns with named CHECK constraints.** Kinds, statuses, roles and match methods are `Literal` types in `src/aggregate/vocab.py`, which both the tables and the Pydantic schemas use, so the two can't drift apart. Text plus CHECK works the same on SQLite and Postgres, where native enums would not.

**D25. `amount_cents` is `BIGINT`.** It's still an integer. On Postgres, a 32-bit `INTEGER` caps cents at about $21.4 million; `BIGINT` costs nothing on SQLite.

**D26. One index beyond the spec: `transaction_links(transaction_id)`.** Every recompute and every `GET /transactions/ID` reads a transaction's links by `transaction_id`, and the primary key (`observation_id`) doesn't cover that lookup.

**D27. No `ON DELETE` cascades.** Deleting an observation that still backs a transaction fails at the database. This enforces D7: the reconciler, the only writer of `transaction_links`, unlinks first.

**D28. Schema tests run against a database built by the migrations**, not by `create_all`, so they test what production runs. Autogenerated migrations are exempt from the line-length lint, because their CHECK constraint SQL stays on one line.
