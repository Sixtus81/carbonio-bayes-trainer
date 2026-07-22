from pathlib import Path

from carbonio_bayes_trainer.database import StateDatabase


def test_state_roundtrip(tmp_path: Path) -> None:
    database_path = tmp_path / "state.db"

    with StateDatabase(database_path) as database:
        database.upsert("user@example.com", "message-1", "/Junk", "spam")
        state = database.get("user@example.com", "message-1")

    assert state is not None
    assert state.folder == "/Junk"
    assert state.trained_as == "spam"


def test_training_stats(tmp_path: Path) -> None:
    with StateDatabase(tmp_path / "state.db") as database:
        database.record_event("user@example.com", "one", "spam", True)
        database.record_event("user@example.com", "two", "ham", True)
        database.record_event("user@example.com", "three", "spam", False)
        stats = database.stats()

    assert stats == {"spam": 1, "ham": 1}
