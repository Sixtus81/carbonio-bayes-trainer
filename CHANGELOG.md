# Changelog

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
