from __future__ import annotations

from .health import HealthReport, HealthStatus

_STATUS_LABELS = {
    HealthStatus.HEALTHY: "OK",
    HealthStatus.INFO: "INFO",
    HealthStatus.WARNING: "WARN",
    HealthStatus.CRITICAL: "FAIL",
}


def format_health(report: HealthReport) -> str:
    stars = "★" * report.stars + "☆" * (5 - report.stars)
    lines = [
        "Health",
        "------",
        stars,
        f"Overall: {report.overall.value.title()}",
        "",
        "Checks",
        "------",
    ]
    for check in report.checks:
        label = _STATUS_LABELS[check.status]
        lines.append(f"[{label:4}] {check.name}: {check.summary}")
        lines.append(f"       {check.details}")

    lines.extend(
        (
            "",
            "Recommendation",
            "--------------",
            report.recommendation,
        )
    )
    return "\n".join(lines)
