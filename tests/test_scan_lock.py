from __future__ import annotations

from pathlib import Path

import pytest

from carbonio_bayes_trainer.scan_lock import ScanAlreadyRunning, ScanLock


def test_second_scan_lock_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "state.db.scan.lock"

    with ScanLock(path):
        with pytest.raises(ScanAlreadyRunning, match="already running"):
            with ScanLock(path):
                pass


def test_scan_lock_can_be_reacquired_after_release(tmp_path: Path) -> None:
    path = tmp_path / "state.db.scan.lock"

    with ScanLock(path):
        assert path.is_file()

    with ScanLock(path):
        assert path.is_file()
