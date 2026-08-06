from __future__ import annotations

import fcntl
from pathlib import Path
from types import TracebackType
from typing import IO


class ScanAlreadyRunning(RuntimeError):
    """Raised when another trainer scan already owns the process lock."""


class ScanLock:
    """Hold a non-blocking advisory lock for the complete scan lifetime."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: IO[str] | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.close()
            raise ScanAlreadyRunning(
                "Another Carbonio Bayes Trainer scan is already running."
            ) from exc

        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f"{self.path}\n")
        lock_file.flush()
        self._file = lock_file

    def release(self) -> None:
        if self._file is None:
            return
        fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()
        self._file = None

    def __enter__(self) -> ScanLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
