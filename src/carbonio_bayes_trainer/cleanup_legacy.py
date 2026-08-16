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
        legacy = self.database.legacy_messages()
        if dry_run:
            return LegacyCleanupResult(found=len(legacy), deleted=0)

        deleted = self.database.delete_legacy_messages()
        return LegacyCleanupResult(found=len(legacy), deleted=deleted)
