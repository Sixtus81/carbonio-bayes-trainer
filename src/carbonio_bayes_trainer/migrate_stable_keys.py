from __future__ import annotations

from dataclasses import dataclass

from .backend import MailboxMessage, MailboxMessageUnavailable
from .carbonio_backend import CarbonioBackend
from .database import StateDatabase


@dataclass(frozen=True)
class MigrationResult:
    total: int
    migrated: int
    skipped: int
    failed: int


class StableKeyMigrator:
    """Backfill stable identities for legacy state rows without retraining Bayes."""

    def __init__(self, backend: CarbonioBackend, database: StateDatabase) -> None:
        self.backend = backend
        self.database = database

    def run(self, *, dry_run: bool = False, limit: int | None = None) -> MigrationResult:
        legacy = self.database.legacy_messages()
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be at least 1")
            legacy = legacy[:limit]

        if dry_run:
            return MigrationResult(total=len(legacy), migrated=0, skipped=0, failed=0)

        migrated = 0
        skipped = 0
        failed = 0

        for state in legacy:
            message = MailboxMessage(
                account=state.account,
                message_key=state.message_key,
                folder=state.folder,
            )
            try:
                stable_key = self.backend.stable_message_key(message)
                self.database.upsert(
                    state.account,
                    state.message_key,
                    state.folder,
                    state.trained_as,
                    stable_key,
                )
            except MailboxMessageUnavailable:
                skipped += 1
            except Exception:
                failed += 1
            else:
                migrated += 1

        return MigrationResult(
            total=len(legacy),
            migrated=migrated,
            skipped=skipped,
            failed=failed,
        )
