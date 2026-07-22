from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from carbonio_bayes_trainer.spamassassin import SpamAssassinTrainer


def test_train_spam_builds_expected_command(tmp_path: Path) -> None:
    observed: list[str] = []

    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        observed.extend(command)
        return subprocess.CompletedProcess(
            list(command),
            0,
            "Learned tokens from 1 message(s) (1 message(s) examined)\n",
            "",
        )

    message = tmp_path / "message.eml"
    message.write_text("Message-ID: <test@example.test>\n", encoding="utf-8")
    trainer = SpamAssassinTrainer(runner=runner)

    success, details = trainer.train(message, "spam")

    assert success is True
    assert "--spam" in observed
    assert str(message) in observed
    assert "Learned tokens" in details


def test_train_ham_reports_nonzero_exit_as_failure(tmp_path: Path) -> None:
    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(command), 1, "", "database error")

    message = tmp_path / "message.eml"
    message.touch()
    trainer = SpamAssassinTrainer(runner=runner)

    success, details = trainer.train(message, "ham")

    assert success is False
    assert details == "database error"
