from __future__ import annotations

import logging
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from .backend import MailboxBackend, MailboxMessage
from .database import StateDatabase
from .state_engine import TrainingAction, decide_transition

LOGGER = logging.getLogger(__name__)


class TrainingBackend(Protocol):
    def train_batch(
        self,
        message_paths: Sequence[Path],
        action: TrainingAction,
    ) -> tuple[bool, str]:
        """Train several RFC822 messages as one batch."""


class MessageProcessor:
    def __init__(
        self,
        backend: MailboxBackend,
        database: StateDatabase,
        trainer: TrainingBackend,
        inbox_folder: str,
        junk_folder: str,
    ) -> None:
        self.backend = backend
        self.database = database
        self.trainer = trainer
        self.inbox_folder = inbox_folder
        self.junk_folder = junk_folder

    def process(self, message: MailboxMessage) -> bool:
        return self.process_batch((message,))

    def observe(self, message: MailboxMessage) -> None:
        previous = self.database.get(message.account, message.message_key)
        trained_as = previous.trained_as if previous else None

        self.database.upsert(
            message.account,
            message.message_key,
            message.folder,
            trained_as,
        )

    def process_batch(self, messages: Sequence[MailboxMessage]) -> bool:
        pending: dict[TrainingAction, list[tuple[MailboxMessage, str]]] = {
            "spam": [],
            "ham": [],
        }

        for message in messages:
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

                LOGGER.debug(
                    "No training for %s: %s",
                    message.message_key,
                    decision.reason,
                )
                continue

            pending[decision.action].append(
                (message, decision.reason)
            )

        all_successful = True

        for action, items in pending.items():
            if not items:
                continue

            if not self._train_batch(action, items):
                all_successful = False

        return all_successful

    def _train_batch(
        self,
        action: TrainingAction,
        items: Sequence[tuple[MailboxMessage, str]],
    ) -> bool:
        with tempfile.TemporaryDirectory(
            prefix="carbonio-bayes-"
        ) as temp_dir:
            paths: list[Path] = []

            for index, (message, _) in enumerate(items, start=1):
                message_path = (
                    Path(temp_dir)
                    / f"{index:04d}-{message.message_key}.eml"
                )

                self.backend.export_message(
                    message,
                    message_path,
                )

                paths.append(message_path)

            success, details = self.trainer.train_batch(
                paths,
                action,
            )

        for message, reason in items:
            self.database.record_event(
                message.account,
                message.message_key,
                action,
                success,
                details,
            )

            if success:
                self.database.upsert(
                    message.account,
                    message.message_key,
                    message.folder,
                    action,
                )

                LOGGER.info(
                    "Trained %s as %s: %s",
                    message.message_key,
                    action,
                    reason,
                )

        if success:
            LOGGER.info(
                "Batch trained %d message(s) as %s",
                len(items),
                action,
            )
        else:
            LOGGER.error(
                "Batch training failed for %d %s message(s): %s",
                len(items),
                action,
                details,
            )

        return success
