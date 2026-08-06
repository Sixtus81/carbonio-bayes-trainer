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
class MailboxStatistics:
    account: str
    known_messages: int
    inbox_messages: int
    junk_messages: int
    stable_keys: int
    spam_events: int
    ham_events: int
    last_updated: str


@dataclass(frozen=True)
class ScanRunStatistics:
    started_at: str
    duration_seconds: float
    accounts: int
    messages: int
    successful: int
    skipped: int
    failed: int
    spam_trained: int
    ham_trained: int


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
    mailboxes: tuple[MailboxStatistics, ...]
    recent_scans: tuple[ScanRunStatistics, ...]
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
        state, mailboxes, recent_scans = _database_statistics(
            self.config.database_path,
            inbox_folder=self.config.inbox_folder,
            junk_folder=self.config.junk_folder,
        )
        return Statistics(
            version=_package_version(),
            state=state,
            bayes=_bayes_statistics(self.trainer),
            mailboxes=mailboxes,
            recent_scans=recent_scans,
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


def _database_statistics(
    path: Path,
    *,
    inbox_folder: str,
    junk_folder: str,
) -> tuple[
    StateStatistics,
    tuple[MailboxStatistics, ...],
    tuple[ScanRunStatistics, ...],
]:
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
        mailbox_rows = connection.execute(
            "SELECT account, COUNT(*), "
            "SUM(CASE WHEN folder = ? THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN folder = ? THEN 1 ELSE 0 END), "
            "COUNT(stable_key), MAX(updated_at) "
            "FROM messages GROUP BY account ORDER BY COUNT(*) DESC, account",
            (inbox_folder, junk_folder),
        ).fetchall()
        mailbox_event_rows = connection.execute(
            "SELECT account, action, COUNT(*) FROM training_events "
            "WHERE success = 1 GROUP BY account, action"
        ).fetchall()
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'scan_runs'"
        ).fetchone()
        scan_rows = (
            connection.execute(
                "SELECT started_at, duration_seconds, accounts, messages, successful, "
                "skipped, failed, spam_trained, ham_trained "
                "FROM scan_runs WHERE dry_run = 0 ORDER BY id DESC LIMIT 5"
            ).fetchall()
            if table_exists
            else []
        )
    except sqlite3.Error as exc:
        raise RuntimeError(f"Unable to read state database {path}: {exc}") from exc
    finally:
        connection.close()

    events = {str(action): int(count) for action, count in event_rows}
    known = int(known_messages)
    stable = int(stable_keys)
    state = StateStatistics(
        known_messages=known,
        stable_keys=stable,
        legacy_keys=known - stable,
        spam_events=events.get("spam", 0),
        ham_events=events.get("ham", 0),
    )

    mailbox_events: dict[str, dict[str, int]] = {}
    for account, action, count in mailbox_event_rows:
        mailbox_events.setdefault(str(account), {})[str(action)] = int(count)

    mailboxes = tuple(
        MailboxStatistics(
            account=str(row[0]),
            known_messages=int(row[1]),
            inbox_messages=int(row[2]),
            junk_messages=int(row[3]),
            stable_keys=int(row[4]),
            spam_events=mailbox_events.get(str(row[0]), {}).get("spam", 0),
            ham_events=mailbox_events.get(str(row[0]), {}).get("ham", 0),
            last_updated=str(row[5]),
        )
        for row in mailbox_rows
    )
    recent_scans = tuple(
        ScanRunStatistics(
            started_at=str(row[0]),
            duration_seconds=float(row[1]),
            accounts=int(row[2]),
            messages=int(row[3]),
            successful=int(row[4]),
            skipped=int(row[5]),
            failed=int(row[6]),
            spam_trained=int(row[7]),
            ham_trained=int(row[8]),
        )
        for row in scan_rows
    )
    return state, mailboxes, recent_scans


def _bayes_statistics(trainer: SpamAssassinTrainer) -> BayesStatistics:
    success, details = trainer.dump_magic()
    if not success:
        raise RuntimeError(f"Unable to read SpamAssassin Bayes statistics: {details}")

    values: dict[str, int] = {}
    for line in details.splitlines():
        match = _MAGIC_VALUE.match(line)
        if match:
            values[match.group(2).strip()] = int(match.group(1))

    missing = [name for name in ("nspam", "nham", "ntokens") if name not in values]
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
    lines = [
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
        "Mailbox statistics",
        "------------------",
    ]
    if statistics.mailboxes:
        for mailbox in statistics.mailboxes:
            lines.extend(
                (
                    mailbox.account,
                    f"  Known: {mailbox.known_messages} | Inbox: {mailbox.inbox_messages} | "
                    f"Junk: {mailbox.junk_messages} | Stable: {mailbox.stable_keys}",
                    f"  Spam events: {mailbox.spam_events} | Ham events: {mailbox.ham_events} | "
                    f"Last update: {mailbox.last_updated}",
                )
            )
    else:
        lines.append("No mailbox state recorded yet.")

    lines.extend(("", "Recent scans", "------------"))
    if statistics.recent_scans:
        for run in statistics.recent_scans:
            lines.append(
                f"{run.started_at} | {run.messages} messages | "
                f"spam +{run.spam_trained} | ham +{run.ham_trained} | "
                f"failed {run.failed} | {run.duration_seconds:.1f}s"
            )
    else:
        lines.append("No scan history recorded yet.")

    lines.extend(
        (
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
    return "\n".join(lines)


def _format_bytes(value: int) -> str:
    if value % (1024 * 1024) == 0:
        return f"{value // (1024 * 1024)} MiB"
    if value % 1024 == 0:
        return f"{value // 1024} KiB"
    return f"{value} bytes"
