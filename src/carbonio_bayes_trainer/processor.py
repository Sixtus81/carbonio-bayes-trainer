from __future__ import annotations

import logging
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Protocol

from .backend import MailboxBackend, MailboxMessage
from .database import MessageState, StateDatabase
from .state_engine import TrainingAction, decide_transition

LOGGER = logging.getLogger(__name__)
SLOW_EXPORT_SECONDS = 2.0
PendingItem = tuple[MailboxMessage, str, str | None]


class TrainingBackend(Protocol):
    def train_batch(
        self,
        message_paths: Sequence[Path],
        action: TrainingAction,
    ) -> tuple[bool, str]:
        """Train several RFC822 messages as one batch."""


@dataclass(frozen=True)
class BatchResult:
    successful: int = 0
    failed: int = 0

    def __add__(self, other: BatchResult) -> BatchResult:
        return BatchResult(
            successful=self.successful + other.successful,
            failed=self.failed + other.failed,
        )


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
        return self.process_batch((message,)).failed == 0

    def _resolve_previous(
        self, message: MailboxMessage, previous: MessageState | None
    ) -> tuple[MessageState | None, str | None]:
        stable_key = previous.stable_key if previous else None
        needs_identity = previous is None or (
            previous.stable_key is None and previous.trained_as == "spam"
        )
        if not needs_identity:
            return previous, stable_key

        stable_key = self.backend.stable_message_key(message)
        stable_previous = self.database.get_by_stable_key(message.account, stable_key)
        if stable_previous is not None:
            previous = stable_previous
        return previous, stable_key

    def observe(self, message: MailboxMessage) -> None:
        previous = self.database.get(message.account, message.message_key)
        previous, stable_key = self._resolve_previous(message, previous)
        trained_as = previous.trained_as if previous else None

        self.database.upsert(
            message.account,
            message.message_key,
            message.folder,
            trained_as,
            stable_key,
        )

    def process_batch(self, messages: Sequence[MailboxMessage]) -> BatchResult:
        pending: dict[TrainingAction, list[PendingItem]] = {
            "spam": [],
            "ham": [],
        }
        successful = 0

        for message in messages:
            previous = self.database.get(message.account, message.message_key)
            previous, stable_key = self._resolve_previous(message, previous)

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
                    stable_key,
                )

                LOGGER.debug(
                    "No training for %s: %s",
                    message.message_key,
                    decision.reason,
                )
                successful += 1
                continue

            pending[decision.action].append((message, decision.reason, stable_key))

        result = BatchResult(successful=successful)

        for action, items in pending.items():
            if items:
                result += self._train_batch(action, items)

        return result

    def _export_message(
        self,
        export: tuple[MailboxMessage, Path],
    ) -> Path:
        message, message_path = export
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

    def _record_training(
        self,
        items: Sequence[PendingItem],
        action: TrainingAction,
        success: bool,
        details: str,
    ) -> None:
        for message, reason, stable_key in items:
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
                    stable_key,
                )
                LOGGER.info(
                    "Trained %s as %s: %s",
                    message.message_key,
                    action,
                    reason,
                )

    def _train_exported(
        self,
        action: TrainingAction,
        items: Sequence[PendingItem],
        paths: Sequence[Path],
    ) -> BatchResult:
        training_started = perf_counter()
        success, details = self.trainer.train_batch(paths, action)
        training_seconds = perf_counter() - training_started
        LOGGER.info(
            "sa-learn processed %d %s message(s) in %.3f s",
            len(paths),
            action,
            training_seconds,
        )

        if success:
            self._record_training(items, action, True, details)
            LOGGER.info(
                "Batch trained %d message(s) as %s",
                len(items),
                action,
            )
            return BatchResult(successful=len(items))

        if len(items) == 1:
            self._record_training(items, action, False, details)
            LOGGER.error(
                "Training failed for %s message %s: %s",
                action,
                items[0][0].message_key,
                details,
            )
            return BatchResult(failed=1)

        LOGGER.warning(
            "Batch training failed for %d %s message(s); retrying individually: %s",
            len(items),
            action,
            details,
        )

        result = BatchResult()
        for item, path in zip(items, paths, strict=True):
            result += self._train_exported(action, (item,), (path,))
        return result

    def _train_batch(
        self,
        action: TrainingAction,
        items: Sequence[PendingItem],
    ) -> BatchResult:
        batch_started = perf_counter()

        with tempfile.TemporaryDirectory(prefix="carbonio-bayes-") as temp_dir:
            exports = [
                (
                    message,
                    Path(temp_dir) / f"{index:04d}-{message.message_key}.eml",
                )
                for index, (message, _, _) in enumerate(items, start=1)
            ]
            export_started = perf_counter()
            worker_count = min(self.export_workers, len(exports))

            LOGGER.info(
                "Exporting %d message(s) with %d worker(s)",
                len(exports),
                worker_count,
            )

            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                paths = list(executor.map(self._export_message, exports))

            export_seconds = perf_counter() - export_started
            LOGGER.info(
                "Exported %d message(s) for %s training in %.3f s",
                len(paths),
                action,
                export_seconds,
            )

            database_started = perf_counter()
            result = self._train_exported(action, items, paths)
            database_seconds = perf_counter() - database_started

        batch_seconds = perf_counter() - batch_started
        LOGGER.info(
            "Updated database for %d message(s) in %.3f s; whole batch took %.3f s",
            len(items),
            database_seconds,
            batch_seconds,
        )
        return result
