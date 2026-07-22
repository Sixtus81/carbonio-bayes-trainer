from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from .state_engine import TrainingAction

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )


class SpamAssassinTrainer:
    """Train SpamAssassin's Bayes database using sa-learn."""

    def __init__(
        self,
        *,
        sa_learn_path: str = "/opt/zextras/common/bin/sa-learn",
        max_message_size: int = 10 * 1024 * 1024,
        runner: CommandRunner = _run,
    ) -> None:
        if max_message_size < 0:
            raise ValueError("max_message_size must be zero or greater")
        self.sa_learn_path = sa_learn_path
        self.max_message_size = max_message_size
        self.runner = runner

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
