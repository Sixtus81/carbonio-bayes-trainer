from pathlib import Path

import pytest

from carbonio_bayes_trainer.config import load_config


def test_load_config_defaults(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("dry_run: true\n", encoding="utf-8")

    config = load_config(config_file)

    assert config.dry_run is True
    assert config.scan_interval_seconds == 300
    assert config.inbox_folder == "/Inbox"
    assert config.junk_folder == "/Junk"


def test_rejects_short_scan_interval(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("scan_interval_seconds: 5\n", encoding="utf-8")

    with pytest.raises(ValueError, match="at least 30"):
        load_config(config_file)
