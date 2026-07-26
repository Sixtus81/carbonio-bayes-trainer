# Ham bootstrap

`bootstrap-ham` seeds the SpamAssassin Bayes database from a mailbox folder that an administrator has selected as trustworthy Ham.

```bash
carbonio-bayes-trainer bootstrap-ham \
  --account christian.mueller@elektro-fred.de \
  --folder '/Inbox/04_Arbeit/AKOM' \
  --dry-run
```

After checking the exported message count, run the training without `--dry-run`:

```bash
carbonio-bayes-trainer bootstrap-ham \
  --account christian.mueller@elektro-fred.de \
  --folder '/Inbox/04_Arbeit/AKOM'
```

Options:

- `--recursive` includes all subfolders below the selected path.
- `--limit N` processes at most `N` messages across all selected folders.
- `--dry-run` exports and counts messages without invoking `sa-learn`.
- `--config PATH` selects a different YAML configuration.

The command deliberately learns every exported message as Ham. Existing `X-Spam-*` headers or a `***SPAM***` subject prefix are not treated as exclusion criteria because a manually selected Ham folder represents the administrator's classification.

Carbonio folder exports can contain many archive members with the same filename. The implementation reads the TGZ archive member by member and assigns unique temporary filenames before batch training, so no messages are overwritten.
