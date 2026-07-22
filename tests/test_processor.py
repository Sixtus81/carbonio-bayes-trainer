from pathlib import Path

from carbonio_bayes_trainer.backend import MailboxMessage
from carbonio_bayes_trainer.database import StateDatabase
from carbonio_bayes_trainer.processor import MessageProcessor
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
        destination.write_text("Subject: test\n\nbody\n", encoding="utf-8")


class FakeTrainer:
    def __init__(self) -> None:
        self.actions: list[TrainingAction] = []

    def train(
        self,
        message_path: Path,
        action: TrainingAction,
    ) -> tuple[bool, str]:
        assert message_path.is_file()
        self.actions.append(action)
        return True, "learned"


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
