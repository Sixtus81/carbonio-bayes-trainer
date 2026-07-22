from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_EXCLUDE_ACCOUNTS = (
    r"^spam\.",
    r"^ham\.",
    r"^virus-quarantine\.",
    r"^galsync(?:\.|@)",
)


@dataclass(frozen=True)
class AppConfig:
    database_path: Path
    dry_run: bool
    scan_interval_seconds: int
    sa_learn_path: str
    zmmailbox_path: str
    mailbox_user: str
    accounts: tuple[str, ...]
    exclude_accounts: tuple[str, ...]
    inbox_folder: str
    junk_folder: str
    max_messages_per_folder: int
    batch_size: int


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _string_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return tuple(value)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    root = _require_mapping(raw, "configuration")
    carbonio = _require_mapping(root.get("carbonio", {}), "carbonio")
    trainer = _require_mapping(root.get("trainer", {}), "trainer")

    accounts = _string_list(carbonio.get("accounts", []), "carbonio.accounts")
    exclude_accounts = _string_list(
        carbonio.get("exclude_accounts", list(_DEFAULT_EXCLUDE_ACCOUNTS)),
        "carbonio.exclude_accounts",
    )
    for pattern in exclude_accounts:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid carbonio.exclude_accounts regex {pattern!r}: {exc}") from exc

    interval = int(root.get("scan_interval_seconds", 300))
    limit = int(carbonio.get("max_messages_per_folder", 1000))
    batch_size = int(trainer.get("batch_size", 50))
    if interval < 30:
        raise ValueError("scan_interval_seconds must be at least 30")
    if not 1 <= limit <= 1000:
        raise ValueError("max_messages_per_folder must be between 1 and 1000")
    if not 1 <= batch_size <= 1000:
        raise ValueError("trainer.batch_size must be between 1 and 1000")

    return AppConfig(
        database_path=Path(root.get("database_path", "/var/lib/carbonio-bayes-trainer/state.db")),
        dry_run=bool(root.get("dry_run", True)),
        scan_interval_seconds=interval,
        sa_learn_path=str(
            trainer.get("sa_learn_path", "/opt/zextras/common/bin/sa-learn")
        ),
        zmmailbox_path=str(carbonio.get("zmmailbox_path", "/opt/zextras/bin/zmmailbox")),
        mailbox_user=str(carbonio.get("run_as_user", "zextras")),
        accounts=accounts,
        exclude_accounts=exclude_accounts,
        inbox_folder=str(carbonio.get("inbox_folder", "/Inbox")),
        junk_folder=str(carbonio.get("junk_folder", "/Junk")),
        max_messages_per_folder=limit,
        batch_size=batch_size,
    )
