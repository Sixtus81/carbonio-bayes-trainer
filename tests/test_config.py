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
    assert config.max_messages_per_folder == 1000
    assert r"^spam\." in config.exclude_accounts
    assert r"^ham\." in config.exclude_accounts


def test_loads_custom_account_exclusions(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "carbonio:\n  exclude_accounts:\n    - '^scanner@'\n",
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.exclude_accounts == ("^scanner@",)


def test_rejects_short_scan_interval(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("scan_interval_seconds: 5\n", encoding="utf-8")

    with pytest.raises(ValueError, match="at least 30"):
        load_config(config_file)


def test_rejects_limit_above_zmmailbox_maximum(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "carbonio:\n  max_messages_per_folder: 1001\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="between 1 and 1000"):
        load_config(config_file)


def test_rejects_invalid_account_exclusion_regex(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "carbonio:\n  exclude_accounts:\n    - '[broken'\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid carbonio.exclude_accounts regex"):
        load_config(config_file)
