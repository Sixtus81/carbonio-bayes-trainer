# Carbonio Bayes Trainer 0.4.2

Version 0.4.2 is a small maintenance release that adds a reliable command-line
version check for installation and support diagnostics.

## New version command

```bash
cd /opt/carbonio-bayes-trainer
.venv/bin/carbonio-bayes-trainer --version
```

Example output:

```text
carbonio-bayes-trainer 0.4.2 (Python 3.12.3)
```

The option also works with the command form previously used in the installation
documentation:

```bash
.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml \
  --version
```

The configuration file is not loaded for a version check.

## Fresh installation

```bash
cd /opt
git clone https://github.com/Sixtus81/carbonio-bayes-trainer.git
cd carbonio-bayes-trainer
python3 -m venv .venv
.venv/bin/pip install .
cp config.example.yaml /etc/carbonio-bayes-trainer.yaml
```

Configure the required mailboxes and keep `dry_run: true` for the first test.
Then verify the installation with `doctor` and a manual `scan` as described in
the README. Only after a successful test set `dry_run: false` and enable the
timer:

```bash
cp systemd/carbonio-bayes-trainer.service /etc/systemd/system/
cp systemd/carbonio-bayes-trainer.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now carbonio-bayes-trainer.timer
```

## Upgrade from an existing installation

```bash
cd /opt/carbonio-bayes-trainer
git pull --ff-only
.venv/bin/pip install .

cp systemd/carbonio-bayes-trainer.service /etc/systemd/system/
cp systemd/carbonio-bayes-trainer.timer /etc/systemd/system/
systemctl daemon-reload
systemctl restart carbonio-bayes-trainer.timer
```

Verify the installed version and health afterwards:

```bash
.venv/bin/carbonio-bayes-trainer --version

su - zextras -c '
cd /opt/carbonio-bayes-trainer &&
.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml doctor
'

su - zextras -c '
cd /opt/carbonio-bayes-trainer &&
.venv/bin/carbonio-bayes-trainer \
  --config /etc/carbonio-bayes-trainer.yaml stats
'
```

This release does not change the configuration format, SQLite state, Bayes
database, scan behavior, or systemd schedule.
