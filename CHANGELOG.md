# Changelog

## [0.4.1] - 2026-09-08

### Added

- Read-only operational statistics with Bayes, state, mailbox, configuration,
  and recent-scan data.
- Health evaluation with actionable checks and recommendations.
- Persistent scan history and per-mailbox analytics.
- A non-blocking process lock that prevents overlapping trainer scans.
- Explicit tools to migrate stable message keys and clean up unreachable
  legacy state rows without retraining SpamAssassin.

### Changed

- Display statistics timestamps in the server's local timezone.
- Use a calendar-based 15-minute systemd timer by default and document how to
  size the interval for larger installations.
- Backfill stable identities for observable legacy messages during normal
  scans without triggering duplicate Spam/Ham training.
- Report stable-key coverage and remaining legacy rows in the health output.

### Fixed

- Prevent concurrent scans from inflating per-run training statistics.
- Avoid leaving old message-state rows without stable identities indefinitely.
- Correct misleading health text about automatic legacy-key migration.

### Production validation

- Completed a continuous production test from 2026-08-10 through 2026-09-08.
- Processed 16,064 known message states with 100% stable-key coverage and no
  remaining legacy rows.
- Recorded 9,549 Spam and 9 Ham training events without failed messages in the
  final scan history.
- Used a production Bayes database containing 14,497 Spam and 96,911 Ham
  messages.
- Maintained a healthy 10-minute schedule with recent scan durations between
  83 and 116 seconds.

## [0.2.0] - 2026-07-23

### Added

- Batch training with SpamAssassin.
- Parallel message export.
- Configurable export worker count.
- Configurable maximum message size for `sa-learn`.
- Exact success and failure reporting.
- Extended `doctor` diagnostics.

### Changed

- Retry failed batches message by message.
- Update the SQLite state only after successful training.
- Improve processing logs and runtime measurements.
- Improve performance when scanning large mailboxes.

### Fixed

- Correct handling of large messages.
- Accurate success and failure accounting.
- Robust handling of failed batch training.
- SpamAssassin Bayes database access from the hardened systemd service.

## [0.1.0]

- Activate the `scan` command for productive Carbonio mailbox processing.
- Add a safe dry-run mode that only discovers accounts and counts messages.
- Connect Carbonio export, transition detection, SQLite state, and SpamAssassin training.
- Make the per-folder message limit configurable.
