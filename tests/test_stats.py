from __future__ import annotations

import sqlite3
from pathlib import Path

from carbonio_bayes_trainer.config import load_config
from carbonio_bayes_trainer.stats import StatisticsCollector, format_statistics


class FakeTrainer:
    def dump_magic(self) -> tuple[bool, str]:
        return (
            True,
            "\n".join(
                (
                    "0.000 0 11391 0 non-token data: nspam",
                    "0.000 0 94924 0 non-token data: nham",
                    "0.000 0 169712 0 non-token data: ntokens",
                )
            ),
        )


def _create_database(path: Path, *, with_scan_history: bool = True) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE messages (
            account TEXT NOT NULL,
            message_key TEXT NOT NULL,
            stable_key TEXT,
            folder TEXT NOT NULL,
            trained_as TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE training_events (
            id INTEGER PRIMARY KEY,
            account TEXT NOT NULL,
            message_key TEXT NOT NULL,
            action TEXT NOT NULL,
            success INTEGER NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL
        );
        INSERT INTO messages VALUES
            ('a@example.test', '1', 'stable-1', '/Inbox', NULL, 'now'),
            ('a@example.test', '2', NULL, '/Junk', 'spam', 'now'),
            ('b@example.test', '3', 'stable-3', '/Inbox', 'ham', 'now');
        INSERT INTO training_events VALUES
            (1, 'a@example.test', '2', 'spam', 1, '', 'now'),
            (2, 'b@example.test', '3', 'ham', 1, '', 'now'),
            (3, 'b@example.test', '4', 'ham', 0, 'failed', 'now');
        """
    )
    if with_scan_history:
        connection.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                accounts INTEGER NOT NULL,
                messages INTEGER NOT NULL,
                successful INTEGER NOT NULL,
                skipped INTEGER NOT NULL,
                failed INTEGER NOT NULL,
                spam_trained INTEGER NOT NULL,
                ham_trained INTEGER NOT NULL,
                dry_run INTEGER NOT NULL
            );
            INSERT INTO scan_runs VALUES
                (1, '2026-08-06T06:30:00+00:00', '2026-08-06T06:31:30+00:00',
                 90.5, 30, 7200, 7199, 0, 1, 4, 1, 0);
            """
        )
    connection.commit()
    connection.close()


def _config_file(tmp_path: Path, database: Path) -> Path:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "\n".join(
            (
                f"database_path: {database}",
                "trainer:",
                "  home: /opt/zextras/data/amavisd",
                "  batch_size: 25",
                "  export_workers: 3",
                "carbonio:",
                "  list_workers: 4",
            )
        ),
        encoding="utf-8",
    )
    return config_file


def test_collects_state_bayes_configuration_and_scan_statistics(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _create_database(database)
    statistics = StatisticsCollector(
        load_config(_config_file(tmp_path, database)),
        trainer=FakeTrainer(),  # type: ignore[arg-type]
    ).collect()

    assert statistics.state.known_messages == 3
    assert statistics.state.stable_keys == 2
    assert statistics.state.legacy_keys == 1
    assert statistics.state.spam_events == 1
    assert statistics.state.ham_events == 1
    assert statistics.bayes.spam == 11391
    assert statistics.bayes.ham == 94924
    assert statistics.bayes.tokens == 169712
    assert statistics.configuration.batch_size == 25
    assert statistics.configuration.mailbox_workers == 4
    assert statistics.configuration.export_workers == 3
    assert len(statistics.recent_scans) == 1
    assert statistics.recent_scans[0].messages == 7200
    assert statistics.recent_scans[0].spam_trained == 4
    assert statistics.recent_scans[0].ham_trained == 1


def test_formats_compact_statistics_output(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _create_database(database)
    statistics = StatisticsCollector(
        load_config(_config_file(tmp_path, database)),
        trainer=FakeTrainer(),  # type: ignore[arg-type]
    ).collect()

    output = format_statistics(statistics)

    assert "Carbonio Bayes Trainer Statistics" in output
    assert "Known messages:  3" in output
    assert "Stable keys:     2" in output
    assert "Spam learned:    11391" in output
    assert "Ham learned:     94924" in output
    assert "Known tokens:    169712" in output
    assert "Recent scans" in output
    assert "7200 messages | spam +4 | ham +1 | failed 1 | 90.5s" in output
    assert "SA HOME:         /opt/zextras/data/amavisd" in output
    assert "Maximum size:    10 MiB" in output


def test_old_database_without_scan_history_is_supported(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _create_database(database, with_scan_history=False)
    statistics = StatisticsCollector(
        load_config(_config_file(tmp_path, database)),
        trainer=FakeTrainer(),  # type: ignore[arg-type]
    ).collect()

    assert statistics.recent_scans == ()
    assert "No scan history recorded yet." in format_statistics(statistics)
