from __future__ import annotations

import argparse
import logging
import re
import shutil
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TypeVar

from .backend import MailboxMessage
from .carbonio_backend import CarbonioBackend
from .config import AppConfig, load_config
from .database import StateDatabase
from .processor import MessageProcessor
from .spamassassin import SpamAssassinTrainer

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


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


def _build_backend(config: AppConfig) -> CarbonioBackend:
    return CarbonioBackend(
        zmmailbox_path=config.zmmailbox_path,
        max_messages_per_folder=config.max_messages_per_folder,
    )


def _accounts(config: AppConfig, backend: CarbonioBackend) -> tuple[str, ...]:
    discovered = config.accounts or tuple(backend.list_accounts())
    return _filter_accounts(tuple(discovered), config.exclude_accounts)


def run_doctor(config_path: str) -> int:
    config = load_config(config_path)
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
    print(f"[INFO] Dry-run: {config.dry_run}")
    print(f"[INFO] Database: {config.database_path}")
    print(f"[INFO] Training batch size: {config.batch_size}")
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
        trainer = SpamAssassinTrainer(sa_learn_path=config.sa_learn_path)
        processor = MessageProcessor(
            backend=backend,
            database=database,
            trainer=trainer,
            inbox_folder=config.inbox_folder,
            junk_folder=config.junk_folder,
        )
        for account in accounts:
            for folder in folders:
                messages = backend.list_messages(account, folder)
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
    config = load_config(config_path)
    backend = _build_backend(config)
    accounts = _accounts(config, backend)
    folders = (config.inbox_folder, config.junk_folder)

    scanned = 0
    succeeded = 0
    failed = 0

    if config.dry_run:
        for account in accounts:
            for folder in folders:
                messages = backend.list_messages(account, folder)
                scanned += len(messages)
                print(f"[DRY-RUN] {account} {folder}: {len(messages)} message(s)")
        print(f"Dry-run complete: {len(accounts)} account(s), {scanned} message(s)")
        return 0

    trainer = SpamAssassinTrainer(sa_learn_path=config.sa_learn_path)
    with StateDatabase(config.database_path) as database:
        processor = MessageProcessor(
            backend=backend,
            database=database,
            trainer=trainer,
            inbox_folder=config.inbox_folder,
            junk_folder=config.junk_folder,
        )
        for account in accounts:
            for folder in folders:
                messages = list(backend.list_messages(account, folder))
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
                        if processor.process_batch(batch):
                            succeeded += len(batch)
                        else:
                            failed += len(batch)
                    except Exception:
                        failed += len(batch)
                        keys = ", ".join(message.message_key for message in batch)
                        LOGGER.exception("Failed to process batch containing: %s", keys)

    print(
        f"Scan complete: {len(accounts)} account(s), {scanned} message(s), "
        f"{succeeded} successful, {failed} failed"
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
