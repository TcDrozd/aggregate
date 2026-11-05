"""The connector contract and the registry that maps names to connectors.

A connector turns one source's payloads into observations and nothing else: no database,
no network, no clock, no reconciliation. See docs/SPEC.md → Connector contract.
"""

import re
from collections.abc import Iterable, Iterator, Mapping
from typing import ClassVar, Protocol

from pydantic import JsonValue

from aggregate.schemas import ParseResult

# A payload is one JSON object, read-only: raw_events stores it verbatim.
type Payload = Mapping[str, JsonValue]

# The name is both a URL segment (`/ingest/NAME`) and the `connector` column's value.
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class Connector(Protocol):
    name: ClassVar[str]
    parser_version: ClassVar[int]  # bump on any parsing change

    def dedupe_key(self, payload: Payload) -> str:
        """Identifies the payload: re-sending it yields the same key. Frozen once shipped."""
        ...

    def parse(self, payload: Payload) -> ParseResult:
        """Pure: the same payload and parser version always give the same result."""
        ...


class Registry(Mapping[str, Connector]):
    """The connectors the service knows, by name. Unknown names are absent, not errors."""

    def __init__(self, connectors: Iterable[Connector]) -> None:
        self._connectors: dict[str, Connector] = {}
        for connector in connectors:
            self._check(connector)
            self._connectors[connector.name] = connector

    def _check(self, connector: Connector) -> None:
        name, version = connector.name, connector.parser_version
        if not NAME_PATTERN.fullmatch(name):
            raise ValueError(f"connector name {name!r} must match {NAME_PATTERN.pattern}")
        if name in self._connectors:
            raise ValueError(f"connector name {name!r} is registered twice")
        if type(version) is not int or version < 1:
            raise ValueError(f"connector {name!r} needs a parser_version of 1 or more")

    def __getitem__(self, name: str) -> Connector:
        return self._connectors[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._connectors)

    def __len__(self) -> int:
        return len(self._connectors)
