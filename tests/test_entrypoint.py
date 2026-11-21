from __future__ import annotations

import platform
import sys

import pytest

pytest.importorskip("fcntl")

from carbonio_bayes_trainer import __version__
from carbonio_bayes_trainer.entrypoint import main


def test_version_prints_application_and_python_versions(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(sys, "argv", ["carbonio-bayes-trainer", "--version"])

    main()

    assert capsys.readouterr().out == (
        f"carbonio-bayes-trainer {__version__} (Python {platform.python_version()})\n"
    )


def test_version_works_with_global_config_argument(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "carbonio-bayes-trainer",
            "--config",
            "/etc/carbonio-bayes-trainer.yaml",
            "--version",
        ],
    )

    main()

    assert capsys.readouterr().out.startswith("carbonio-bayes-trainer 0.4.2 (Python ")
