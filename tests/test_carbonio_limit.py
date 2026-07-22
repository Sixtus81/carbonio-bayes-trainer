from __future__ import annotations

import subprocess
from collections.abc import Sequence

from carbonio_bayes_trainer.carbonio_backend import CarbonioBackend


def test_message_limit_is_forwarded_to_zmmailbox() -> None:
    observed: list[str] = []

    def runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        observed.extend(command)
        return subprocess.CompletedProcess(list(command), 0, "", "")

    backend = CarbonioBackend(max_messages_per_folder=1234, runner=runner)
    backend.list_messages("user@example.test", "/Junk")

    assert "1234" in observed
