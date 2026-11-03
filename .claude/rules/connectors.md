---
paths:
  - "src/aggregate/connectors/**"
  - "tests/fixtures/**"
---
# Connector rules
- `parse()` is pure: no DB, no network, no clock
- Any parsing change bumps `parser_version` and adds a fixture
- Fixtures are synthetic copies of real shapes; real captures go in `tests/fixtures/private/`
- A connector's `dedupe_key` recipe is frozen once shipped: Wallet uses it as `external_id`, so changing it orphans transactions
