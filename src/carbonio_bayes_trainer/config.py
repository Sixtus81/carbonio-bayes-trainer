from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
    database_path: Path
    dry_run: bool
    scan_interval_seconds: int
    sa_learn_path: str
    zmmailbox_path: str
    mailbox_user: str
    accounts: tuple[str, ...]
    inbox_folder: str
    junk_folder: str
    max_messages_per_folder: int


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    root = _require_mapping(raw, "configuration")
    carbonio = _require_mapping(root.get("carbonio", {}), "carbonio")
    trainer = _require_mapping(root.get("trainer", {}), "trainer")

    accounts_raw = carbonio.get("accounts", [])
    accounts_are_strings = all(isinstance(item, str) for item in accounts_raw)
    if not isinstance(accounts_raw, list) or not accounts_are_strings:
        raise ValueError("carbonio.accounts must be a list of strings")

    interval = int(root.get("scan_interval_seconds", 300))
    limit = int(carbonio.get("max_messages_per_folder", 5000))
    if interval < 30:
        raise ValueError("scan_interval_seconds must be at least 30")
    if limit < 1:
        raise ValueError("max_messages_per_folder must be positive")

    return AppConfig(
        database_path=Path(root.get("database_path", "/var/lib/carbonio-bayes-trainer/state.db")),
        dry_run=bool(root.get("dry_run", True)),
        scan_interval_seconds=interval,
        sa_learn_path=str(trainer.get("sa_learn_path", "/usr/bin/sa-learn")),
        zmmailbox_path=str(carbonio.get("zmmailbox_path", "/opt/zextras/bin/zmmailbox")),
        mailbox_user=str(carbonio.get("run_as_user", "zextras")),
        accounts=tuple(accounts_raw),
        inbox_folder=str(carbonio.get("inbox_folder", "/Inbox")),
        junk_folder=str(carbonio.get("junk_folder", "/Junk")),
        max_messages_per_folder=limit,
    )
