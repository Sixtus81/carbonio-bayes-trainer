from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .stats import Statistics


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: HealthStatus
    summary: str
    details: str
    recommendation: str | None = None


@dataclass(frozen=True)
class HealthReport:
    overall: HealthStatus
    stars: int
    checks: tuple[HealthCheck, ...]
    recommendation: str


class HealthEvaluator:
    """Turn collected statistics into an explainable health report."""

    def evaluate(
        self,
        statistics: Statistics,
        *,
        now: datetime | None = None,
    ) -> HealthReport:
        evaluated_at = now or datetime.now(timezone.utc)
        if evaluated_at.tzinfo is None:
            evaluated_at = evaluated_at.replace(tzinfo=timezone.utc)

        checks = (
            self._scan_freshness(statistics, evaluated_at),
            self._failed_messages(statistics),
            self._bayes_database(statistics),
            self._stable_coverage(statistics),
            self._training_activity(statistics),
        )
        return HealthReport(
            overall=self._overall_status(checks),
            stars=self._stars(checks),
            checks=checks,
            recommendation=self._recommendation(checks),
        )

    def _scan_freshness(self, statistics: Statistics, now: datetime) -> HealthCheck:
        if not statistics.recent_scans:
            return HealthCheck(
                name="Scan freshness",
                status=HealthStatus.CRITICAL,
                summary="No productive scan history is available.",
                details="The trainer cannot confirm that scheduled scans are running.",
                recommendation="Run a productive scan and verify the systemd timer.",
            )

        started_at = datetime.fromisoformat(statistics.recent_scans[0].started_at)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        age_minutes = max(0.0, (now - started_at).total_seconds()) / 60

        if age_minutes < 20:
            return HealthCheck(
                name="Scan freshness",
                status=HealthStatus.HEALTHY,
                summary=f"Last scan started {age_minutes:.0f} minute(s) ago.",
                details="The scheduled trainer appears to be running normally.",
            )
        if age_minutes < 60:
            return HealthCheck(
                name="Scan freshness",
                status=HealthStatus.WARNING,
                summary=f"Last scan started {age_minutes:.0f} minute(s) ago.",
                details="The latest scan is older than expected for a frequent schedule.",
                recommendation="Check the timer schedule and the previous scan duration.",
            )
        return HealthCheck(
            name="Scan freshness",
            status=HealthStatus.CRITICAL,
            summary=f"Last scan started {age_minutes / 60:.1f} hour(s) ago.",
            details="No recent productive scan was recorded.",
            recommendation="Check the Carbonio Bayes Trainer service and timer.",
        )

    def _failed_messages(self, statistics: Statistics) -> HealthCheck:
        if not statistics.recent_scans:
            return HealthCheck(
                name="Failed messages",
                status=HealthStatus.INFO,
                summary="No recent scan is available for failure analysis.",
                details="Failure health will be evaluated after the first productive scan.",
            )

        failed = sum(scan.failed for scan in statistics.recent_scans)
        if failed == 0:
            return HealthCheck(
                name="Failed messages",
                status=HealthStatus.HEALTHY,
                summary="No failures in the recent scan history.",
                details="Recent message processing completed without recorded failures.",
            )
        return HealthCheck(
            name="Failed messages",
            status=HealthStatus.WARNING,
            summary=f"{failed} failed message(s) in recent scans.",
            details="Failed exports or training operations require investigation.",
            recommendation="Review the trainer journal for failed message IDs.",
        )

    def _bayes_database(self, statistics: Statistics) -> HealthCheck:
        ham = statistics.bayes.ham
        spam = statistics.bayes.spam
        if ham < 500:
            return HealthCheck(
                name="Bayes database",
                status=HealthStatus.CRITICAL,
                summary=f"Only {ham} Ham and {spam} Spam messages are learned.",
                details="SpamAssassin does not yet have a sufficient Ham foundation.",
                recommendation="Run bootstrap-ham on trusted mail folders.",
            )
        if ham < 5000 or spam < 200:
            return HealthCheck(
                name="Bayes database",
                status=HealthStatus.WARNING,
                summary=f"{ham} Ham and {spam} Spam messages are learned.",
                details="The Bayes database is usable but still has limited training data.",
                recommendation="Continue normal training and consider a Ham bootstrap.",
            )
        return HealthCheck(
            name="Bayes database",
            status=HealthStatus.HEALTHY,
            summary=f"{ham} Ham and {spam} Spam messages are learned.",
            details="The production Bayes database has a substantial training foundation.",
        )

    def _stable_coverage(self, statistics: Statistics) -> HealthCheck:
        known = statistics.state.known_messages
        stable = statistics.state.stable_keys
        legacy = statistics.state.legacy_keys
        if known == 0:
            return HealthCheck(
                name="Stable-key coverage",
                status=HealthStatus.INFO,
                summary="No message state is available yet.",
                details="Coverage will be calculated after messages have been scanned.",
            )

        coverage = stable / known * 100
        if coverage >= 90:
            status = HealthStatus.HEALTHY
            description = "Excellent coverage."
        elif coverage >= 75:
            status = HealthStatus.HEALTHY
            description = "Good coverage."
        elif coverage >= 50:
            status = HealthStatus.INFO
            description = "Coverage is improving as new messages receive stable keys."
        else:
            status = HealthStatus.WARNING
            description = "A large legacy message population remains."

        recommendation = None
        if status is HealthStatus.WARNING:
            recommendation = "Run migrate-stable-keys to backfill legacy message identities."
        return HealthCheck(
            name="Stable-key coverage",
            status=status,
            summary=f"{stable} of {known} messages ({coverage:.1f}%).",
            details=f"{description} {legacy} legacy entries remain.",
            recommendation=recommendation,
        )

    def _training_activity(self, statistics: Statistics) -> HealthCheck:
        if not statistics.recent_scans:
            return HealthCheck(
                name="Training activity",
                status=HealthStatus.INFO,
                summary="No recent scan history is available.",
                details="Training activity will be evaluated after productive scans.",
            )

        spam = sum(scan.spam_trained for scan in statistics.recent_scans)
        ham = sum(scan.ham_trained for scan in statistics.recent_scans)
        if spam + ham > 0:
            return HealthCheck(
                name="Training activity",
                status=HealthStatus.HEALTHY,
                summary=f"Recent scans learned {spam} Spam and {ham} Ham message(s).",
                details="Training activity is present in the recent scan history.",
            )
        return HealthCheck(
            name="Training activity",
            status=HealthStatus.INFO,
            summary="No messages were trained in the recent scan history.",
            details="This is not necessarily an error when no messages changed folders.",
        )

    @staticmethod
    def _overall_status(checks: tuple[HealthCheck, ...]) -> HealthStatus:
        statuses = {check.status for check in checks}
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        if HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        if HealthStatus.INFO in statuses:
            return HealthStatus.INFO
        return HealthStatus.HEALTHY

    @staticmethod
    def _stars(checks: tuple[HealthCheck, ...]) -> int:
        scores = {
            HealthStatus.HEALTHY: 1.0,
            HealthStatus.INFO: 0.8,
            HealthStatus.WARNING: 0.5,
            HealthStatus.CRITICAL: 0.0,
        }
        average = sum(scores[check.status] for check in checks) / len(checks)
        return max(1, min(5, round(average * 5)))

    @staticmethod
    def _recommendation(checks: tuple[HealthCheck, ...]) -> str:
        priority = (
            HealthStatus.CRITICAL,
            HealthStatus.WARNING,
            HealthStatus.INFO,
        )
        for status in priority:
            for check in checks:
                if check.status is status and check.recommendation:
                    return check.recommendation
        return "No action required."
