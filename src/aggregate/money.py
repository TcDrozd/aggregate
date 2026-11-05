"""Money is integer cents, parsed from strings with Decimal. No float ever holds money."""

import re
from decimal import MAX_PREC, Context, Decimal, Inexact

# An optional minus, an optional dollar sign, whole dollars with or without thousands
# separators, and exactly two decimal places. ASCII digits only: `\d` alone would accept
# other scripts' digits, which Decimal also reads.
_DOLLARS = re.compile(r"-?\$?(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}", re.ASCII)

# Wide enough for any input, and an inexact result raises instead of rounding.
_EXACT = Context(prec=MAX_PREC, traps=[Inexact])


def parse_dollars(text: str) -> int:
    """A dollar amount as text, to integer cents: `$1,234.56` → 123456, `-12.34` → -1234.

    Signs pass through unchanged; each connector applies the ledger's sign rule.
    """
    if not _DOLLARS.fullmatch(text):
        # The amount itself stays out of the message: it can end up in logs.
        raise ValueError("not a dollar amount with exactly two decimal places")
    amount = Decimal(text.replace("$", "").replace(",", ""))
    return int(amount.scaleb(2, _EXACT))
