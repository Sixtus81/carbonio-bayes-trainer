from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .config import AppConfig
from .spamassassin import SpamAssassinTrainer

_MAGIC_VALUE = re.compile(r"^\s*\S+\s+\S+\s+(\d+)\s+\S+\s+non-token data: (.+)$")


@dataclass(frozen=True)
class BayesStatistics:
    spam: int
    ham: int
    tokens: int


@dataclass(frozen=True)
class StateStatistics:
    known_messages: int
    stable_keys: int
    legacy_keys: int
    spam_events: int
    ham_events: int


@dataclass(frozen=True)
class ConfigurationStatistics:
    database_path: Path
    spamassassin_home: Path | None
    batch_size: int
    mailbox_workers: int
    export_workers: int
    max_message_size: int


@dataclass(frozen=True)
class Statistics:
    version: str
    state: StateStatistics
    bayes: BayesStatistics
    configuration: ConfigurationStatistics


class StatisticsCollector:
    """Collect read-only operational statistics for the trainer."""

    def __init__(
        self,
        config: AppConfig,
        *,
        trainer: SpamAssassinTrainer | None = None,
    ) -> None:
        self.config = config
        self.trainer = trainer or SpamAssassinTrainer(
            sa_learn_path=config.sa_learn_path,
            spamassassin_home=config.spamassassin_home,
            max_message_size=config.max_message_size,
        )

    def collect(self) -> Statistics:
        return Statistics(
            version=_package_version(),
            state=_state_statistics(self.config.database_path),
            bayes=_bayes_statistics(self.trainer),
            configuration=ConfigurationStatistics(
                database_path=self.config.database_path,
                spamassassin_home=self.config.spamassassin_home,
                batch_size=self.config.batch_size,
                mailbox_workers=self.config.list_workers,
                export_workers=self.config.export_workers,
                max_message_size=self.config.max_message_size,
            ),
        )


def _package_version() -> str:
    try:
        return version("carbonio-bayes-trainer")
    except PackageNotFoundError:
        return "development"


def _state_statistics(path: Path) -> StateStatistics:
    if not path.is_file():
        raise RuntimeError(f"State database does not exist: {path}")

    connection = sqlite3.connect(path)
    try:
        known_messages, stable_keys = connection.execute(
            "SELECT COUNT(*), COUNT(stable_key) FROM messages"
        ).fetchone()
        event_rows = connection.execute(
            "SELECT action, COUNT(*) FROM training_events "
            "WHERE success = 1 GROUP BY action"
        ).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError(f"Unable to read state database {path}: {exc}") from exc
    finally:
        connection.close()

    events = {str(action): int(count) for action, count in event_rows}
    known = int(known_messages)
    stable = int(stable_keys)
    return StateStatistics(
        known_messages=known,
        stable_keys=stable,
        legacy_keys=known - stable,
        spam_events=events.get("spam", 0),
        ham_events=events.get("ham", 0),
    )


def _bayes_statistics(trainer: SpamAssassinTrainer) -> BayesStatistics:
    success, details = trainer.dump_magic()
    if not success:
        raise RuntimeError(f"Unable to read SpamAssassin Bayes statistics: {details}")

    values: dict[str, int] = {}
    for line in details.splitlines():
        match = _MAGIC_VALUE.match(line)
        if match:
            values[match.group(2).strip()] = int(match.group(1))

    required = {
        "nspam": "spam",
        "nham": "ham",
        "ntokens": "tokens",
    }
    missing = [source for source in required if source not in values]
    if missing:
        raise RuntimeError(
            "SpamAssassin Bayes statistics are incomplete; missing " + ", ".join(missing)
        )

    return BayesStatistics(
        spam=values["nspam"],
        ham=values["nham"],
        tokens=values["ntokens"],
    )


def format_statistics(statistics: Statistics) -> str:
    config = statistics.configuration
    maximum_size = (
        "unlimited"
        if config.max_message_size == 0
        else _format_bytes(config.max_message_size)
    )
    home = str(config.spamassassin_home) if config.spamassassin_home else "not configured"

    return "\n".join(
        (
            "Carbonio Bayes Trainer Statistics",
            "",
            "Version",
            "-------",
            statistics.version,
            "",
            "State database",
            "--------------",
            f"Known messages:  {statistics.state.known_messages}",
            f"Stable keys:     {statistics.state.stable_keys}",
            f"Legacy keys:     {statistics.state.legacy_keys}",
            f"Spam events:     {statistics.state.spam_events}",
            f"Ham events:      {statistics.state.ham_events}",
            "",
            "Bayes database",
            "--------------",
            f"Spam learned:    {statistics.bayes.spam}",
            f"Ham learned:     {statistics.bayes.ham}",
            f"Known tokens:    {statistics.bayes.tokens}",
            "",
            "Configuration",
            "-------------",
            f"State database:  {config.database_path}",
            f"SA HOME:         {home}",
            f"Batch size:      {config.batch_size}",
            f"Mailbox workers: {config.mailbox_workers}",
            f"Export workers:  {config.export_workers}",
            f"Maximum size:    {maximum_size}",
        )
    )


def _format_bytes(value: int) -> str:
    if value % (1024 * 1024) == 0:
        return f"{value // (1024 * 1024)} MiB"
    if value % 1024 == 0:
        return f"{value // 1024} KiB"
    return f"{value} bytes"
