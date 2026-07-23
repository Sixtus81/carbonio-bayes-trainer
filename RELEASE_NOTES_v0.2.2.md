# Carbonio Bayes Trainer v0.2.2

## Highlights

- Parallel mailbox-folder listing for substantially faster scans
- Stable message identity using RFC822 `Message-ID` with SHA256 fallback
- Reliable Spam/Ham training even when Carbonio changes the internal mailbox ID

## Improvements

- New `carbonio.list_workers` setting (default: `5`)
- Inbox and Junk listings run concurrently
- Deterministic processing order is preserved
- `doctor` reports listing and export worker counts separately
- Documentation and example configuration updated

## Production validation

Validated on a Carbonio CE installation with:

- 30 accounts
- 7090 messages
- 7090 successful
- 0 failed
- Runtime reduced from about 3:57 to 1:26 (about 64%)

## Upgrade

```bash
cd /opt/carbonio-bayes-trainer
git pull --rebase
source .venv/bin/activate
pip install .
```

Optional configuration:

```yaml
carbonio:
  list_workers: 5
```
