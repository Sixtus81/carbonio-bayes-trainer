from __future__ import annotations

import argparse
import logging
import re
import shutil
from pathlib import Path

from .carbonio_backend import CarbonioBackend
from .config import load_config
from .database import StateDatabase
from .processor import MessageProcessor
from .spamassassin import SpamAssassinTrainer

LOGGER = logging.getLogger(__name__)


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
    print(f"[INFO] Account exclusions: {len(config.exclude_accounts)} pattern(s)")
    return 1 if failed else 0


def run_stats(config_path: str) -> int:
    config = load_config(config_path)
    with StateDatabase(config.database_path) as database:
        stats = database.stats()
    print(f"Spam learned: {stats['spam']}")
    print(f"Ham learned:  {stats['ham']}")
    return 0


def run_scan(config_path: str) -> int:
    config = load_config(config_path)
    backend = CarbonioBackend(
        zmmailbox_path=config.zmmailbox_path,
        max_messages_per_folder=config.max_messages_per_folder,
    )
    discovered = config.accounts or tuple(backend.list_accounts())
    accounts = _filter_accounts(tuple(discovered), config.exclude_accounts)
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
                messages = backend.list_messages(account, folder)
                LOGGER.info("Scanning %s %s: %d message(s)", account, folder, len(messages))
                for message in messages:
                    scanned += 1
                    try:
                        if processor.process(message):
                            succeeded += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1
                        LOGGER.exception(
                            "Failed to process %s:%s",
                            message.account,
                            message.message_key,
                        )

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
    if command == "scan":
        raise SystemExit(run_scan(args.config))
    parser.error(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
