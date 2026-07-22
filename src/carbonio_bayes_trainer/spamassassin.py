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
        runner: CommandRunner = _run,
    ) -> None:
        self.sa_learn_path = sa_learn_path
        self.runner = runner

    def train(self, message_path: Path, action: TrainingAction) -> tuple[bool, str]:
        mode = "--spam" if action == TrainingAction.SPAM else "--ham"
        result = self.runner([self.sa_learn_path, mode, "--showdots", str(message_path)])
        details = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        success = result.returncode == 0 and "Learned tokens from 1 message" in details
        if not details:
            details = f"sa-learn exited with status {result.returncode}"
        return success, details
