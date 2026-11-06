"""merchant_key: a merchant's name reduced to a form that matches across sources."""

import re
import unicodedata

# Straight and curly apostrophes are removed outright, so `Joe's Diner` written with iOS's
# U+2019 gives `joes diner` and matches a statement's `JOES DINER`. U+02BC, the modifier
# letter apostrophe, counts as a letter in Unicode, so without this it would survive.
_APOSTROPHES = str.maketrans("", "", "'\u2018\u2019\u201b\u02bc")

# Runs of anything but Unicode letters and digits (`\w` minus the underscore).
_SEPARATORS = re.compile(r"[\W_]+")


def merchant_key(name: str) -> str:
    """NFKC, apostrophes removed, lowercase, other non-alphanumeric runs to one space, trimmed.

    Curly double quotes need no mapping: like straight ones, they become a space. The result
    is empty when the name has no letters or digits. Applying it twice changes nothing.
    """
    text = unicodedata.normalize("NFKC", name).translate(_APOSTROPHES).lower()
    # Removing an apostrophe or lowercasing can leave text NFKC would change again,
    # for example two Hangul jamo that now sit together.
    text = unicodedata.normalize("NFKC", text)
    return _SEPARATORS.sub(" ", text).strip()
