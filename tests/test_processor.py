from collections.abc import Sequence
from pathlib import Path

from carbonio_bayes_trainer.backend import MailboxMessage
from carbonio_bayes_trainer.database import StateDatabase
from carbonio_bayes_trainer.processor import BatchResult, MessageProcessor
from carbonio_bayes_trainer.state_engine import TrainingAction


class FakeBackend:
    def __init__(self) -> None:
        self.exports = 0

    def list_accounts(self) -> list[str]:
        return ["user@example.com"]

    def list_messages(self, account: str, folder: str) -> list[MailboxMessage]:
        return []

    def export_message(self, message: MailboxMessage, destination: Path) -> None:
        self.exports += 1
    destination.write_text(
        "Message-ID: <stable@example.com>\n"
        "Subject: test\n"
        "\n"
        "body\n",
        encoding="utf-8",
    )
    def stable_message_key(self, message: MailboxMessage) -> str:
        return "message-id:<stable@example.com>"


class FakeTrainer:
    def __init__(self) -> None:
        self.actions: list[TrainingAction] = []

    def train_batch(
        self,
        message_paths: Sequence[Path],
        action: TrainingAction,
    ) -> tuple[bool, str]:
        self.actions.append(action)
        return True, ""


class IsolatingTrainer:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def train_batch(
        self,
        message_paths: Sequence[Path],
        action: TrainingAction,
    ) -> tuple[bool, str]:
        self.batch_sizes.append(len(message_paths))
        if len(message_paths) > 1:
            return False, "batch failed"
        if message_paths[0].name.endswith("message-1.eml"):
            return True, "learned"
        return False, "0 message(s) examined"


def test_junk_message_is_trained_only_once(tmp_path: Path) -> None:
    backend = FakeBackend()
    trainer = FakeTrainer()
    message = MailboxMessage("user@example.com", "message-1", "/Junk")

    with StateDatabase(tmp_path / "state.db") as database:
        processor = MessageProcessor(
            backend,
            database,
            trainer,
            "/Inbox",
            "/Junk",
        )
        assert processor.process(message)
        assert processor.process(message)

    assert trainer.actions == ["spam"]
    assert backend.exports == 1


def test_spam_returned_to_inbox_is_ham(tmp_path: Path) -> None:
    backend = FakeBackend()
    trainer = FakeTrainer()

    with StateDatabase(tmp_path / "state.db") as database:
        processor = MessageProcessor(
            backend,
            database,
            trainer,
            "/Inbox",
            "/Junk",
        )
        assert processor.process(
            MailboxMessage("user@example.com", "message-1", "/Junk")
        )
        assert processor.process(
            MailboxMessage("user@example.com", "message-1", "/Inbox")
        )

    assert trainer.actions == ["spam", "ham"]
    assert backend.exports == 2


def test_spam_returned_to_inbox_with_changed_internal_id_is_ham(tmp_path: Path) -> None:
    backend = FakeBackend()
    trainer = FakeTrainer()

    with StateDatabase(tmp_path / "state.db") as database:
        processor = MessageProcessor(
            backend,
            database,
            trainer,
            "/Inbox",
            "/Junk",
        )
        assert processor.process(
            MailboxMessage("user@example.com", "junk-id", "/Junk")
        )
        assert processor.process(
            MailboxMessage("user@example.com", "inbox-id", "/Inbox")
        )

        state = database.get("user@example.com", "inbox-id")

    assert trainer.actions == ["spam", "ham"]
    assert state is not None
    assert state.stable_key == "message-id:<stable@example.com>"
    assert state.trained_as == "ham"


def test_failed_training_batch_is_retried_individually(tmp_path: Path) -> None:
    backend = FakeBackend()
    trainer = IsolatingTrainer()
    messages = (
        MailboxMessage("user@example.com", "message-1", "/Junk"),
        MailboxMessage("user@example.com", "message-2", "/Junk"),
    )

    with StateDatabase(tmp_path / "state.db") as database:
        processor = MessageProcessor(
            backend,
            database,
            trainer,
            "/Inbox",
            "/Junk",
        )
        result = processor.process_batch(messages)
        stats = database.stats()

    assert result == BatchResult(successful=1, failed=1)
    assert trainer.batch_sizes == [2, 1, 1]
    assert stats["spam"] == 1
