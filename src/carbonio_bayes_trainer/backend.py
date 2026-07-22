from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


@dataclass(frozen=True)
class MailboxMessage:
    """Minimal message metadata required by the transition engine."""

    account: str
    message_key: str
    folder: str


class MailboxBackend(Protocol):
    """Interface implemented by Carbonio and future mailbox backends."""

    def list_accounts(self) -> Sequence[str]:
        """Return all accounts that should be scanned."""

    def list_messages(self, account: str, folder: str) -> Sequence[MailboxMessage]:
        """Return messages currently present in one folder."""

    def export_message(self, message: MailboxMessage, destination: Path) -> None:
        """Export the complete RFC822 message to destination."""
