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
- Amounts go through `money.parse_dollars` and merchant names through `merchants.merchant_key`; never compute cents any other way
- In Python strings, write non-ASCII characters as `\uXXXX` escapes: ruff (RUF001) flags curly quotes that look like ASCII ones, and escapes show in a diff which character it is
