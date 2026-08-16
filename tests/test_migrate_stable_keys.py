from __future__ import annotations

from pathlib import Path

from carbonio_bayes_trainer.backend import MailboxMessage, MailboxMessageUnavailable
from carbonio_bayes_trainer.database import StateDatabase
from carbonio_bayes_trainer.migrate_stable_keys import StableKeyMigrator


class FakeBackend:
    def stable_message_key(self, message: MailboxMessage) -> str:
        if message.message_key == "missing":
            raise MailboxMessageUnavailable("gone")
        if message.message_key == "broken":
            raise RuntimeError("export failed")
        return f"message-id:<{message.message_key}@example.test>"


def _database(path: Path) -> StateDatabase:
    database = StateDatabase(path)
    database.upsert("a@example.test", "1", "/Inbox", None)
    database.upsert("a@example.test", "2", "/Junk", "spam")
    database.upsert("a@example.test", "missing", "/Inbox", None)
    database.upsert("a@example.test", "broken", "/Inbox", None)
    database.upsert(
        "a@example.test",
        "stable",
        "/Inbox",
        None,
        "message-id:<stable@example.test>",
    )
    return database


def test_dry_run_only_counts_legacy_rows(tmp_path: Path) -> None:
    with _database(tmp_path / "state.db") as database:
        result = StableKeyMigrator(FakeBackend(), database).run(dry_run=True)  # type: ignore[arg-type]

        assert result.total == 4
        assert result.migrated == 0
        assert result.skipped == 0
        assert result.failed == 0
        assert len(database.legacy_messages()) == 4


def test_migration_backfills_stable_keys_without_training(tmp_path: Path) -> None:
    with _database(tmp_path / "state.db") as database:
        result = StableKeyMigrator(FakeBackend(), database).run()  # type: ignore[arg-type]

        assert result.total == 4
        assert result.migrated == 2
        assert result.skipped == 1
        assert result.failed == 1
        assert database.get("a@example.test", "1").stable_key == "message-id:<1@example.test>"  # type: ignore[union-attr]
        assert database.get("a@example.test", "2").stable_key == "message-id:<2@example.test>"  # type: ignore[union-attr]
        assert len(database.legacy_messages()) == 2


def test_limit_restricts_number_of_legacy_rows(tmp_path: Path) -> None:
    with _database(tmp_path / "state.db") as database:
        result = StableKeyMigrator(FakeBackend(), database).run(limit=1)  # type: ignore[arg-type]

        assert result.total == 1
        assert result.migrated == 1
        assert len(database.legacy_messages()) == 3
