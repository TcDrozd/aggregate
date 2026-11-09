"""Connectors: one module per source, each satisfying `base.Connector`."""

from aggregate.connectors.base import Registry
from aggregate.connectors.wallet_notification import WalletNotification


def default_registry() -> Registry:
    """Every connector the service runs."""
    return Registry([WalletNotification()])
