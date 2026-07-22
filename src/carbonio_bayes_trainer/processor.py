from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from .backend import MailboxBackend, MailboxMessage
from .database import StateDatabase
from .state_engine import decide_transition
from .trainer import BayesTrainer

LOGGER = logging.getLogger(__name__)


class MessageProcessor:
    def __init__(
        self,
        backend: MailboxBackend,
        database: StateDatabase,
        trainer: BayesTrainer,
        inbox_folder: str,
        junk_folder: str,
    ) -> None:
        self.backend = backend
        self.database = database
        self.trainer = trainer
        self.inbox_folder = inbox_folder
        self.junk_folder = junk_folder

    def process(self, message: MailboxMessage) -> bool:
        previous = self.database.get(message.account, message.message_key)
        decision = decide_transition(
            previous,
            message.folder,
            self.inbox_folder,
            self.junk_folder,
        )

        if decision.action is None:
            trained_as = previous.trained_as if previous else None
            self.database.upsert(
                message.account,
                message.message_key,
                message.folder,
                trained_as,
            )
            LOGGER.debug("No training for %s: %s", message.message_key, decision.reason)
            return True

        with tempfile.TemporaryDirectory(prefix="carbonio-bayes-") as temp_dir:
            message_path = Path(temp_dir) / "message.eml"
            self.backend.export_message(message, message_path)
            success, details = self.trainer.train(message_path, decision.action)

        self.database.record_event(
            message.account,
            message.message_key,
            decision.action,
            success,
            details,
        )
        if not success:
            return False

        self.database.upsert(
            message.account,
            message.message_key,
            message.folder,
            decision.action,
        )
        LOGGER.info(
            "Trained %s as %s: %s",
            message.message_key,
            decision.action,
            decision.reason,
        )
        return True
