from pathlib import Path

from carbonio_bayes_trainer.cleanup_legacy import LegacyStateCleaner
from carbonio_bayes_trainer.database import StateDatabase


def _database(path: Path) -> StateDatabase:
    database = StateDatabase(path)
    database.upsert("a@example.test", "legacy-1", "/Inbox", None)
    database.upsert("a@example.test", "legacy-2", "/Junk", "spam")
    database.upsert(
        "a@example.test",
        "stable-1",
        "/Inbox",
        None,
        "message-id:<stable-1@example.test>",
    )
    database.record_event("a@example.test", "legacy-2", "spam", True, "learned")
    return database


def test_cleanup_dry_run_only_counts_legacy_rows(tmp_path: Path) -> None:
    with _database(tmp_path / "state.db") as database:
        result = LegacyStateCleaner(database).run(dry_run=True)

        assert result.found == 2
        assert result.deleted == 0
        assert len(database.legacy_messages()) == 2
        assert database.get("a@example.test", "stable-1") is not None
        assert database.training_event_counts()["spam"] == 1


def test_cleanup_deletes_only_legacy_message_state(tmp_path: Path) -> None:
    with _database(tmp_path / "state.db") as database:
        result = LegacyStateCleaner(database).run()

        assert result.found == 2
        assert result.deleted == 2
        assert database.legacy_messages() == ()
        assert database.get("a@example.test", "stable-1") is not None
        assert database.training_event_counts()["spam"] == 1
