from __future__ import annotations

import logging
import subprocess
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class BayesTrainer:
    def __init__(self, executable: str, dry_run: bool = True) -> None:
        self.executable = executable
        self.dry_run = dry_run

    def train(self, message_path: Path, action: str) -> tuple[bool, str]:
        if action not in {"spam", "ham"}:
            raise ValueError(f"Unsupported training action: {action}")

        command = [self.executable, f"--{action}", str(message_path)]
        if self.dry_run:
            LOGGER.info("Dry-run: %s", " ".join(command))
            return True, "dry-run"

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        output = (completed.stdout + completed.stderr).strip()
        if completed.returncode != 0:
            LOGGER.error("sa-learn failed: %s", output)
            return False, output
        LOGGER.info("sa-learn %s succeeded for %s", action, message_path)
        return True, output
