from __future__ import annotations

from pathlib import Path

from carbonio_bayes_trainer.database import StateDatabase


def test_records_and_reads_recent_scan_runs(tmp_path: Path) -> None:
    database_path = tmp_path / "state.db"

    with StateDatabase(database_path) as database:
        database.record_scan_run(
            started_at="2026-08-06T06:30:00+00:00",
            finished_at="2026-08-06T06:31:30+00:00",
            duration_seconds=90.5,
            accounts=30,
            messages=7200,
            successful=7199,
            skipped=0,
            failed=1,
            spam_trained=4,
            ham_trained=1,
            dry_run=False,
        )
        runs = database.recent_scan_runs()

    assert len(runs) == 1
    assert runs[0].accounts == 30
    assert runs[0].messages == 7200
    assert runs[0].spam_trained == 4
    assert runs[0].ham_trained == 1
    assert runs[0].failed == 1
    assert runs[0].dry_run is False


def test_recent_scan_runs_are_returned_newest_first(tmp_path: Path) -> None:
    with StateDatabase(tmp_path / "state.db") as database:
        for number in range(3):
            database.record_scan_run(
                started_at=f"2026-08-06T06:3{number}:00+00:00",
                finished_at=f"2026-08-06T06:3{number}:30+00:00",
                duration_seconds=30.0,
                accounts=1,
                messages=number,
                successful=number,
                skipped=0,
                failed=0,
                spam_trained=0,
                ham_trained=0,
                dry_run=False,
            )

        runs = database.recent_scan_runs(limit=2)

    assert [run.messages for run in runs] == [2, 1]
