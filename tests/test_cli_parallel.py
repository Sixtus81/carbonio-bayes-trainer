from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from carbonio_bayes_trainer.backend import MailboxMessage
from carbonio_bayes_trainer.cli import _list_mailboxes


class FakeBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def list_messages(self, account: str, folder: str) -> Sequence[MailboxMessage]:
        self.calls.append((account, folder))
        return (
            MailboxMessage(
                account=account,
                message_key=f"{account}-{folder}",
                folder=folder,
            ),
        )

    def export_message(self, message: MailboxMessage, destination: Path) -> None:
        raise NotImplementedError

    def stable_message_key(self, message: MailboxMessage) -> str:
        raise NotImplementedError


def test_list_mailboxes_preserves_account_and_folder_order() -> None:
    backend = FakeBackend()

    listings = _list_mailboxes(
        backend,  # type: ignore[arg-type]
        ("one@example.com", "two@example.com"),
        ("/Inbox", "/Junk"),
        workers=4,
    )

    assert [(account, folder) for account, folder, _ in listings] == [
        ("one@example.com", "/Inbox"),
        ("one@example.com", "/Junk"),
        ("two@example.com", "/Inbox"),
        ("two@example.com", "/Junk"),
    ]
    assert sorted(backend.calls) == sorted(
        [
            ("one@example.com", "/Inbox"),
            ("one@example.com", "/Junk"),
            ("two@example.com", "/Inbox"),
            ("two@example.com", "/Junk"),
        ]
    )
