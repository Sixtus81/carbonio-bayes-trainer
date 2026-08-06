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


def _create_database(path: Path) -> None:
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
    connection.commit()
    connection.close()


def test_collects_state_bayes_and_configuration_statistics(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _create_database(database)
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

    statistics = StatisticsCollector(
        load_config(config_file),
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


def test_formats_compact_statistics_output(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    _create_database(database)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"database_path: {database}\ntrainer:\n  home: /opt/zextras/data/amavisd\n",
        encoding="utf-8",
    )
    statistics = StatisticsCollector(
        load_config(config_file),
        trainer=FakeTrainer(),  # type: ignore[arg-type]
    ).collect()

    output = format_statistics(statistics)

    assert "Carbonio Bayes Trainer Statistics" in output
    assert "Known messages:  3" in output
    assert "Stable keys:     2" in output
    assert "Spam learned:    11391" in output
    assert "Ham learned:     94924" in output
    assert "Known tokens:    169712" in output
    assert "SA HOME:         /opt/zextras/data/amavisd" in output
    assert "Maximum size:    10 MiB" in output
