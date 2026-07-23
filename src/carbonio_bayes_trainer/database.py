from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class MessageState:
    account: str
    message_key: str
    stable_key: str | None
    folder: str
    trained_as: str | None
    updated_at: str


class StateDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;

            CREATE TABLE IF NOT EXISTS messages (
                account TEXT NOT NULL,
                message_key TEXT NOT NULL,
                stable_key TEXT,
                folder TEXT NOT NULL,
                trained_as TEXT CHECK (trained_as IN ('spam', 'ham') OR trained_as IS NULL),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (account, message_key)
            );

            CREATE TABLE IF NOT EXISTS training_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT NOT NULL,
                message_key TEXT NOT NULL,
                action TEXT NOT NULL CHECK (action IN ('spam', 'ham')),
                success INTEGER NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        columns = {
            str(row["name"])
            for row in self.connection.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "stable_key" not in columns:
            self.connection.execute("ALTER TABLE messages ADD COLUMN stable_key TEXT")
        self.connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS messages_stable_identity "
            "ON messages(account, stable_key) WHERE stable_key IS NOT NULL"
        )
        self.connection.commit()

    def get(self, account: str, message_key: str) -> MessageState | None:
        row = self.connection.execute(
            "SELECT account, message_key, stable_key, folder, trained_as, updated_at "
            "FROM messages WHERE account = ? AND message_key = ?",
            (account, message_key),
        ).fetchone()
        return MessageState(**dict(row)) if row else None

    def get_by_stable_key(self, account: str, stable_key: str) -> MessageState | None:
        row = self.connection.execute(
            "SELECT account, message_key, stable_key, folder, trained_as, updated_at "
            "FROM messages WHERE account = ? AND stable_key = ?",
            (account, stable_key),
        ).fetchone()
        return MessageState(**dict(row)) if row else None

    def upsert(
        self,
        account: str,
        message_key: str,
        folder: str,
        trained_as: str | None,
        stable_key: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if stable_key is not None:
            existing = self.get_by_stable_key(account, stable_key)
            if existing is not None and existing.message_key != message_key:
                self.connection.execute(
                    "DELETE FROM messages WHERE account = ? AND message_key = ?",
                    (account, message_key),
                )
                self.connection.execute(
                    "UPDATE messages SET message_key = ?, folder = ?, trained_as = ?, "
                    "updated_at = ? WHERE account = ? AND stable_key = ?",
                    (message_key, folder, trained_as, now, account, stable_key),
                )
                self.connection.commit()
                return

        self.connection.execute(
            """
            INSERT INTO messages(account, message_key, stable_key, folder, trained_as, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account, message_key) DO UPDATE SET
                stable_key = COALESCE(excluded.stable_key, messages.stable_key),
                folder = excluded.folder,
                trained_as = excluded.trained_as,
                updated_at = excluded.updated_at
            """,
            (account, message_key, stable_key, folder, trained_as, now),
        )
        self.connection.commit()

    def record_event(
        self,
        account: str,
        message_key: str,
        action: str,
        success: bool,
        details: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """
            INSERT INTO training_events(account, message_key, action, success, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (account, message_key, action, int(success), details, now),
        )
        self.connection.commit()

    def stats(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT action, COUNT(*) AS count "
            "FROM training_events "
            "WHERE success = 1 "
            "GROUP BY action"
        ).fetchall()
        result = {"spam": 0, "ham": 0}
        result.update({str(row["action"]): int(row["count"]) for row in rows})
        return result

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> StateDatabase:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
