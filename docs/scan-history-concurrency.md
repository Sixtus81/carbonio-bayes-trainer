# Scan history concurrency

Scan history must record only the work performed by the current process.

Global before/after counts from `training_events` are not safe when a manual scan and the systemd service overlap. Each batch therefore reports its own Spam and Ham training counts, and the scan aggregates those local results before writing `scan_runs`.
