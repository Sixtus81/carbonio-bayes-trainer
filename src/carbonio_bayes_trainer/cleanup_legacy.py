from __future__ import annotations

from dataclasses import dataclass

from .database import StateDatabase


@dataclass(frozen=True)
class LegacyCleanupResult:
    found: int
    deleted: int


class LegacyStateCleaner:
    """Remove legacy message-state rows without touching SpamAssassin Bayes data."""

    def __init__(self, database: StateDatabase) -> None:
        self.database = database

    def run(self, *, dry_run: bool = False) -> LegacyCleanupResult:
        found = len(self.database.legacy_messages())
        if dry_run:
            return LegacyCleanupResult(found=found, deleted=0)

        cursor = self.database.connection.execute(
            "DELETE FROM messages WHERE stable_key IS NULL"
        )
        self.database.connection.commit()
        return LegacyCleanupResult(found=found, deleted=int(cursor.rowcount))
