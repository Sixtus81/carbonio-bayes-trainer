from __future__ import annotations

from pathlib import Path

from carbonio_bayes_trainer import cli
from carbonio_bayes_trainer.backend import MailboxMessage
from carbonio_bayes_trainer.config import AppConfig


class FakeBackend:
    def __init__(self, **_: object) -> None:
        pass

    def list_accounts(self) -> tuple[str, ...]:
        return ("user@example.test",)

    def list_messages(self, account: str, folder: str) -> tuple[MailboxMessage, ...]:
        return (MailboxMessage(account, "101", folder),)


def test_scan_dry_run_discovers_accounts_without_training(
    monkeypatch: object,
    tmp_path: Path,
    capsys: object,
) -> None:
    config = AppConfig(
        database_path=tmp_path / "state.db",
        dry_run=True,
        scan_interval_seconds=300,
        sa_learn_path="/opt/zextras/common/bin/sa-learn",
        zmmailbox_path="/opt/zextras/bin/zmmailbox",
        mailbox_user="zextras",
        accounts=(),
        inbox_folder="/Inbox",
        junk_folder="/Junk",
        max_messages_per_folder=5000,
    )

    monkeypatch.setattr(cli, "load_config", lambda _: config)
    monkeypatch.setattr(cli, "CarbonioBackend", FakeBackend)

    assert cli.run_scan("unused.yaml") == 0
    output = capsys.readouterr().out
    assert "1 account(s), 2 message(s)" in output
    assert not config.database_path.exists()
