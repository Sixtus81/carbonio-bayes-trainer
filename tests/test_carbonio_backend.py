from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from carbonio_bayes_trainer.backend import MailboxMessage
from carbonio_bayes_trainer.carbonio_backend import CarbonioBackend


def completed(
    command: Sequence[str], *, stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(list(command), returncode, stdout, stderr)


def test_list_accounts_filters_non_account_output() -> None:
    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return completed(command, stdout="user@example.test\nINFO startup\nadmin@example.test\n")

    backend = CarbonioBackend(runner=runner)

    assert backend.list_accounts() == ("user@example.test", "admin@example.test")


def test_list_messages_parses_numeric_message_ids() -> None:
    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return completed(
            command,
            stdout=(
                "num: 2, more: false\n"
                "    10151  mess  user@example.test  Subject one\n"
                "    10132  mess  sender@example.test Subject two\n"
            ),
        )

    backend = CarbonioBackend(runner=runner)

    assert backend.list_messages("user@example.test", "/Junk") == (
        MailboxMessage("user@example.test", "10151", "/Junk"),
        MailboxMessage("user@example.test", "10132", "/Junk"),
    )


def test_list_messages_parses_carbonio_26_numbered_rows() -> None:
    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return completed(
            command,
            stdout=(
                "num: 2, more: true\n\n"
                "       Id  Type   From                  Subject\n"
                "   ------  ----   --------------------  -------\n"
                "1. 156438  mess   Slimming              Subject one\n"
                "2. 156437  mess   Window                Subject two\n"
            ),
        )

    backend = CarbonioBackend(runner=runner)

    assert backend.list_messages("user@example.test", "/Inbox") == (
        MailboxMessage("user@example.test", "156438", "/Inbox"),
        MailboxMessage("user@example.test", "156437", "/Inbox"),
    )


def test_rejects_zmmailbox_limit_above_1000() -> None:
    with pytest.raises(ValueError, match="between 1 and 1000"):
        CarbonioBackend(max_messages_per_folder=1001)


def test_export_message_uses_local_rest_url_and_validates_mail(tmp_path: Path) -> None:
    observed: list[str] = []

    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        observed.extend(command)
        command_list = list(command)
        output_path = Path(command_list[command_list.index("-o") + 1])
        output_path.write_bytes(
            b"Received: by mail.example.test\r\n"
            b"Message-ID: <test@example.test>\r\n"
            b"MIME-Version: 1.0\r\n\r\nbody"
        )
        return completed(command)

    backend = CarbonioBackend(rest_url="http://127.0.0.1:8080", runner=runner)
    destination = tmp_path / "message.eml"
    backend.export_message(
        MailboxMessage("user@example.test", "10151", "/Junk"), destination
    )

    assert destination.is_file()
    assert "http://127.0.0.1:8080" in observed
    assert "//?id=10151" in observed


def test_export_message_rejects_empty_file(tmp_path: Path) -> None:
    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        command_list = list(command)
        Path(command_list[command_list.index("-o") + 1]).touch()
        return completed(command)

    backend = CarbonioBackend(runner=runner)

    with pytest.raises(RuntimeError, match="empty RFC822"):
        backend.export_message(
            MailboxMessage("user@example.test", "10151", "/Junk"),
            tmp_path / "message.eml",
        )
