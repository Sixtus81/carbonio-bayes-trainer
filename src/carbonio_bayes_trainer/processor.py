from __future__ import annotations

import logging
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from typing import Protocol

from .backend import MailboxBackend, MailboxMessage
from .database import StateDatabase
from .state_engine import TrainingAction, decide_transition

LOGGER = logging.getLogger(__name__)
SLOW_EXPORT_SECONDS = 2.0


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
        export_workers: int = 5,
    ) -> None:
        if not 1 <= export_workers <= 32:
            raise ValueError("export_workers must be between 1 and 32")

        self.backend = backend
        self.database = database
        self.trainer = trainer
        self.inbox_folder = inbox_folder
        self.junk_folder = junk_folder
        self.export_workers = export_workers

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

    def _export_message(
        self,
        message: MailboxMessage,
        message_path: Path,
    ) -> Path:
        message_export_started = perf_counter()
        self.backend.export_message(message, message_path)
        message_export_seconds = perf_counter() - message_export_started

        if message_export_seconds >= SLOW_EXPORT_SECONDS:
            LOGGER.debug(
                "Export of message %s took %.3f s",
                message.message_key,
                message_export_seconds,
            )

        return message_path

    def _train_batch(
        self,
        action: TrainingAction,
        items: Sequence[tuple[MailboxMessage, str]],
    ) -> bool:
        batch_started = perf_counter()

        with tempfile.TemporaryDirectory(
            prefix="carbonio-bayes-"
        ) as temp_dir:
            exports = [
                (
                    message,
                    Path(temp_dir)
                    / f"{index:04d}-{message.message_key}.eml",
                )
                for index, (message, _) in enumerate(items, start=1)
            ]
            export_started = perf_counter()
            worker_count = min(self.export_workers, len(exports))

            LOGGER.info(
                "Exporting %d message(s) with %d worker(s)",
                len(exports),
                worker_count,
            )

            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                paths = list(
                    executor.map(
                        lambda item: self._export_message(*item),
                        exports,
                    )
                )

            export_seconds = perf_counter() - export_started
            LOGGER.info(
                "Exported %d message(s) for %s training in %.3f s",
                len(paths),
                action,
                export_seconds,
            )

            training_started = perf_counter()
            success, details = self.trainer.train_batch(
                paths,
                action,
            )
            training_seconds = perf_counter() - training_started
            LOGGER.info(
                "sa-learn processed %d %s message(s) in %.3f s",
                len(paths),
                action,
                training_seconds,
            )

        database_started = perf_counter()

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

        database_seconds = perf_counter() - database_started
        batch_seconds = perf_counter() - batch_started
        LOGGER.info(
            "Updated database for %d message(s) in %.3f s; "
            "whole batch took %.3f s",
            len(items),
            database_seconds,
            batch_seconds,
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
