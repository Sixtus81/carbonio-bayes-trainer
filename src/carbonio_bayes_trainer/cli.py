from __future__ import annotations

import argparse
import logging
import re
import shutil
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import TypeVar

from .backend import MailboxMessage
from .carbonio_backend import CarbonioBackend
from .config import AppConfig, load_config
from .database import StateDatabase
from .processor import MessageProcessor
from .spamassassin import SpamAssassinTrainer

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")
MailboxListing = tuple[str, str, Sequence[MailboxMessage]]
_BAYES_COUNTER = re.compile(r"non-token data: (nspam|nham|ntokens)$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="carbonio-bayes-trainer")
    parser.add_argument(
        "--config",
        default="/etc/carbonio-bayes-trainer.yaml",
        help="Path to the YAML configuration file",
    )
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="Check local dependencies and configuration")
    subparsers.add_parser("stats", help="Show training statistics")
    subparsers.add_parser("init", help="Record the current mailbox state without training")
    subparsers.add_parser("scan", help="Run one mailbox scan")
    return parser


def _filter_accounts(
    accounts: tuple[str, ...],
    exclude_patterns: tuple[str, ...],
) -> tuple[str, ...]:
    patterns = tuple(re.compile(pattern) for pattern in exclude_patterns)
    return tuple(
        account
        for account in accounts
        if not any(pattern.search(account) for pattern in patterns)
    )


def _chunks(items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _list_mailbox(
    backend: CarbonioBackend,
    job: tuple[str, str],
) -> MailboxListing:
    account, folder = job
    return account, folder, backend.list_messages(account, folder)


def _list_mailboxes(
    backend: CarbonioBackend,
    accounts: Sequence[str],
    folders: Sequence[str],
    workers: int,
) -> tuple[MailboxListing, ...]:
    jobs = tuple((account, folder) for account in accounts for folder in folders)
    if not jobs:
        return ()

    worker_count = min(workers, len(jobs))
    LOGGER.info(
        "Listing %d mailbox folder(s) with %d worker(s)",
        len(jobs),
        worker_count,
    )
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return tuple(executor.map(lambda job: _list_mailbox(backend, job), jobs))


def _build_backend(config: AppConfig) -> CarbonioBackend:
    return CarbonioBackend(
        zmmailbox_path=config.zmmailbox_path,
        max_messages_per_folder=config.max_messages_per_folder,
    )


def _accounts(config: AppConfig, backend: CarbonioBackend) -> tuple[str, ...]:
    discovered = config.accounts or tuple(backend.list_accounts())
    return _filter_accounts(tuple(discovered), config.exclude_accounts)


def _build_trainer(config: AppConfig) -> SpamAssassinTrainer:
    return SpamAssassinTrainer(
        sa_learn_path=config.sa_learn_path,
        spamassassin_home=config.spamassassin_home,
        max_message_size=config.max_message_size,
    )


def _bayes_counters(output: str) -> dict[str, int]:
    counters: dict[str, int] = {}
    for line in output.splitlines():
        match = _BAYES_COUNTER.search(line.strip())
        if not match:
            continue
        fields = line.split()
        if len(fields) >= 3:
            counters[match.group(1)] = int(fields[2])
    return counters


def run_doctor(config_path: str) -> int:
    config = load_config(config_path)
    trainer = _build_trainer(config)
    checks = [
        ("Configuration", True, config_path),
        ("sa-learn", Path(config.sa_learn_path).is_file(), config.sa_learn_path),
        ("zmmailbox", Path(config.zmmailbox_path).is_file(), config.zmmailbox_path),
        ("su", shutil.which("su") is not None, shutil.which("su") or "not found"),
    ]
    failed = False
    print("Carbonio Bayes Trainer Doctor\n")
    for name, success, details in checks:
        symbol = "OK" if success else "FAIL"
        print(f"[{symbol:4}] {name}: {details}")
        failed = failed or not success

    if config.spamassassin_home is None:
        print("[WARN] SpamAssassin HOME: process default")
        print("[WARN] Carbonio commonly uses /opt/zextras/data/amavisd")
    else:
        home_exists = config.spamassassin_home.is_dir()
        symbol = "OK" if home_exists else "FAIL"
        print(f"[{symbol:4}] SpamAssassin HOME: {config.spamassassin_home}")
        failed = failed or not home_exists
        bayes_directory = trainer.bayes_directory
        bayes_files = trainer.existing_bayes_files()
        if bayes_files:
            names = ", ".join(path.name for path in bayes_files)
            print(f"[OK  ] Bayes database: {bayes_directory} ({names})")
        else:
            print(f"[WARN] Bayes database: no bayes_* files found in {bayes_directory}")

    if Path(config.sa_learn_path).is_file():
        success, output = trainer.dump_magic()
        if success:
            counters = _bayes_counters(output)
            print(f"[INFO] Bayes spam: {counters.get('nspam', 'unknown')}")
            print(f"[INFO] Bayes ham: {counters.get('nham', 'unknown')}")
            print(f"[INFO] Bayes tokens: {counters.get('ntokens', 'unknown')}")
        else:
            print("[FAIL] Unable to read Bayes statistics with sa-learn --dump magic")
            failed = True

    print(f"[INFO] Dry-run: {config.dry_run}")
    print(f"[INFO] Database: {config.database_path}")
    print(f"[INFO] Training batch size: {config.batch_size}")
    print(f"[INFO] Parallel mailbox listing workers: {config.list_workers}")
    print(f"[INFO] Parallel export workers: {config.export_workers}")
    size_description = (
        "unlimited"
        if config.max_message_size == 0
        else f"{config.max_message_size} bytes"
    )
    print(f"[INFO] Maximum training message size: {size_description}")
    print(f"[INFO] Account exclusions: {len(config.exclude_accounts)} pattern(s)")
    return 1 if failed else 0


def run_stats(config_path: str) -> int:
    config = load_config(config_path)
    with StateDatabase(config.database_path) as database:
        stats = database.stats()
    print(f"Spam learned: {stats['spam']}")
    print(f"Ham learned:  {stats['ham']}")
    return 0


def run_init(config_path: str) -> int:
    config = load_config(config_path)
    backend = _build_backend(config)
    accounts = _accounts(config, backend)
    folders = (config.inbox_folder, config.junk_folder)
    observed = 0

    with StateDatabase(config.database_path) as database:
        trainer = _build_trainer(config)
        processor = MessageProcessor(
            backend=backend,
            database=database,
            trainer=trainer,
            inbox_folder=config.inbox_folder,
            junk_folder=config.junk_folder,
            export_workers=config.export_workers,
        )
        listings = _list_mailboxes(backend, accounts, folders, config.list_workers)
        for account, folder, messages in listings:
            LOGGER.info("Initializing %s %s: %d message(s)", account, folder, len(messages))
            for message in messages:
                processor.observe(message)
                observed += 1

    print(
        f"Initialization complete: {len(accounts)} account(s), "
        f"{observed} message(s) recorded, no training performed"
    )
    return 0


def run_scan(config_path: str) -> int:
    started_at = datetime.now(timezone.utc)
    started_counter = perf_counter()
    config = load_config(config_path)
    backend = _build_backend(config)
    accounts = _accounts(config, backend)
    folders = (config.inbox_folder, config.junk_folder)

    scanned = 0
    succeeded = 0
    failed = 0
    skipped = 0
    listings = _list_mailboxes(backend, accounts, folders, config.list_workers)

    if config.dry_run:
        for account, folder, messages in listings:
            scanned += len(messages)
            print(f"[DRY-RUN] {account} {folder}: {len(messages)} message(s)")
        print(f"Dry-run complete: {len(accounts)} account(s), {scanned} message(s)")
        return 0

    trainer = _build_trainer(config)
    with StateDatabase(config.database_path) as database:
        events_before = database.training_event_counts()
        processor = MessageProcessor(
            backend=backend,
            database=database,
            trainer=trainer,
            inbox_folder=config.inbox_folder,
            junk_folder=config.junk_folder,
            export_workers=config.export_workers,
        )
        for account, folder, messages in listings:
            messages = list(messages)
            LOGGER.info("Scanning %s %s: %d message(s)", account, folder, len(messages))
            batches = list(_chunks(messages, config.batch_size))
            for batch_number, batch in enumerate(batches, start=1):
                scanned += len(batch)
                LOGGER.info(
                    "Processing batch %d/%d for %s %s (%d message(s))",
                    batch_number,
                    len(batches),
                    account,
                    folder,
                    len(batch),
                )
                try:
                    result = processor.process_batch(batch)
                    succeeded += result.successful
                    failed += result.failed
                    skipped += result.skipped
                except Exception:
                    failed += len(batch)
                    keys = ", ".join(message.message_key for message in batch)
                    LOGGER.exception("Failed to process batch containing: %s", keys)

        events_after = database.training_event_counts()
        finished_at = datetime.now(timezone.utc)
        database.record_scan_run(
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_seconds=perf_counter() - started_counter,
            accounts=len(accounts),
            messages=scanned,
            successful=succeeded,
            skipped=skipped,
            failed=failed,
            spam_trained=events_after["spam"] - events_before["spam"],
            ham_trained=events_after["ham"] - events_before["ham"],
            dry_run=False,
        )

    print(
        f"Scan complete: {len(accounts)} account(s), {scanned} message(s), "
        f"{succeeded} successful, {skipped} skipped, {failed} failed"
    )
    return 1 if failed else 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    command = args.command or "doctor"
    if command == "doctor":
        raise SystemExit(run_doctor(args.config))
    if command == "stats":
        raise SystemExit(run_stats(args.config))
    if command == "init":
        raise SystemExit(run_init(args.config))
    if command == "scan":
        raise SystemExit(run_scan(args.config))
    parser.error(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
