from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from .state_engine import TrainingAction

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _run(
    command: Sequence[str],
    *,
    spamassassin_home: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if spamassassin_home is not None:
        env["HOME"] = str(spamassassin_home)
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


class SpamAssassinTrainer:
    """Train SpamAssassin's Bayes database using sa-learn."""

    def __init__(
        self,
        *,
        sa_learn_path: str = "/opt/zextras/common/bin/sa-learn",
        spamassassin_home: str | Path | None = None,
        max_message_size: int = 10 * 1024 * 1024,
        runner: CommandRunner | None = None,
    ) -> None:
        if max_message_size < 0:
            raise ValueError("max_message_size must be zero or greater")
        self.sa_learn_path = sa_learn_path
        self.spamassassin_home = (
            Path(spamassassin_home) if spamassassin_home is not None else None
        )
        self.max_message_size = max_message_size
        self.runner = runner or (
            lambda command: _run(command, spamassassin_home=self.spamassassin_home)
        )

    @property
    def bayes_directory(self) -> Path | None:
        if self.spamassassin_home is None:
            return None
        return self.spamassassin_home / ".spamassassin"

    def existing_bayes_files(self) -> tuple[Path, ...]:
        directory = self.bayes_directory
        if directory is None:
            return ()
        return tuple(
            path
            for path in (
                directory / "bayes_toks",
                directory / "bayes_seen",
                directory / "bayes_journal",
            )
            if path.is_file()
        )

    def dump_magic(self) -> tuple[bool, str]:
        result = self.runner((self.sa_learn_path, "--dump", "magic"))
        details = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        if not details:
            details = f"sa-learn exited with status {result.returncode}"
        return result.returncode == 0, details

    def train(self, message_path: Path, action: TrainingAction) -> tuple[bool, str]:
        return self.train_batch((message_path,), action)

    def train_batch(
        self,
        message_paths: Sequence[Path],
        action: TrainingAction,
    ) -> tuple[bool, str]:
        if not message_paths:
            raise ValueError("message_paths must not be empty")

        mode = "--spam" if action == "spam" else "--ham"
        command = [
            self.sa_learn_path,
            mode,
            "--max-size",
            str(self.max_message_size),
            "--showdots",
            *(str(path) for path in message_paths),
        ]
        result = self.runner(command)
        details = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        success = result.returncode == 0
        if not details:
            details = f"sa-learn exited with status {result.returncode}"
        return success, details
