# Productive mailbox scan

The `scan` command now connects the Carbonio mailbox backend, SQLite state database,
transition engine, RFC822 exporter, and SpamAssassin trainer.

Keep `dry_run: true` for the first run. In dry-run mode the command discovers the
configured accounts and counts messages in Inbox and Junk without creating the state
database or invoking `sa-learn`.

After the dry-run output has been verified, set `dry_run: false` and run:

```bash
carbonio-bayes-trainer --config /etc/carbonio-bayes-trainer.yaml scan
```

The command exits with status 1 when one or more messages could not be processed.
Successful training transitions are persisted in SQLite so unchanged messages are not
trained repeatedly.
