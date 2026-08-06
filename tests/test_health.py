from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from carbonio_bayes_trainer.health import HealthEvaluator, HealthStatus
from carbonio_bayes_trainer.stats import (
    BayesStatistics,
    ConfigurationStatistics,
    ScanRunStatistics,
    StateStatistics,
    Statistics,
)


def _statistics(
    *,
    scan_started: str = "2026-08-06T09:55:00+00:00",
    failed: int = 0,
    spam_trained: int = 4,
    ham_trained: int = 1,
    known: int = 10000,
    stable: int = 6000,
    bayes_ham: int = 95000,
    bayes_spam: int = 11500,
    include_scan: bool = True,
) -> Statistics:
    scans = ()
    if include_scan:
        scans = (
            ScanRunStatistics(
                started_at=scan_started,
                duration_seconds=120.0,
                accounts=30,
                messages=4200,
                successful=4200 - failed,
                skipped=0,
                failed=failed,
                spam_trained=spam_trained,
                ham_trained=ham_trained,
            ),
        )
    return Statistics(
        version="0.4.0",
        state=StateStatistics(
            known_messages=known,
            stable_keys=stable,
            legacy_keys=known - stable,
            spam_events=4500,
            ham_events=8,
        ),
        bayes=BayesStatistics(spam=bayes_spam, ham=bayes_ham, tokens=180000),
        mailboxes=(),
        recent_scans=scans,
        configuration=ConfigurationStatistics(
            database_path=Path("/var/lib/carbonio-bayes-trainer/state.db"),
            spamassassin_home=Path("/opt/zextras/data/amavisd"),
            batch_size=50,
            mailbox_workers=5,
            export_workers=3,
            max_message_size=10 * 1024 * 1024,
        ),
    )


def test_healthy_production_statistics_receive_five_stars() -> None:
    report = HealthEvaluator().evaluate(
        _statistics(),
        now=datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
    )

    assert report.stars == 5
    assert report.overall is HealthStatus.INFO
    assert report.recommendation == "No action required."
    assert [check.name for check in report.checks] == [
        "Scan freshness",
        "Failed messages",
        "Bayes database",
        "Stable-key coverage",
        "Training activity",
    ]


def test_stale_scan_is_critical_and_recommends_timer_check() -> None:
    report = HealthEvaluator().evaluate(
        _statistics(scan_started="2026-08-06T06:00:00+00:00"),
        now=datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
    )

    assert report.overall is HealthStatus.CRITICAL
    assert report.stars < 5
    assert report.recommendation == "Check the Carbonio Bayes Trainer service and timer."


def test_failed_messages_are_reported_as_warning() -> None:
    report = HealthEvaluator().evaluate(
        _statistics(failed=3),
        now=datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
    )

    failed_check = next(check for check in report.checks if check.name == "Failed messages")
    assert failed_check.status is HealthStatus.WARNING
    assert "3 failed" in failed_check.summary


def test_small_bayes_database_recommends_ham_bootstrap() -> None:
    report = HealthEvaluator().evaluate(
        _statistics(bayes_ham=100, bayes_spam=50),
        now=datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
    )

    assert report.overall is HealthStatus.CRITICAL
    assert report.recommendation == "Run bootstrap-ham on trusted mail folders."


def test_missing_scan_history_is_critical() -> None:
    report = HealthEvaluator().evaluate(
        _statistics(include_scan=False),
        now=datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
    )

    assert report.overall is HealthStatus.CRITICAL
    assert report.recommendation == "Run a productive scan and verify the systemd timer."
