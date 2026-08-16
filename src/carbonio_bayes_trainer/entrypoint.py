from __future__ import annotations

import argparse
import logging
import sys

from .bootstrap import HamBootstrapper, MailFolder
from .carbonio_backend import CarbonioBackend
from .cleanup_legacy import LegacyStateCleaner
from .cli import main as legacy_main
from .config import load_config
from .database import StateDatabase
from .migrate_stable_keys import StableKeyMigrator
from .scan_lock import ScanAlreadyRunning, ScanLock
from .spamassassin import SpamAssassinTrainer
from .stats_command import run_stats


def _bootstrap_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="carbonio-bayes-trainer bootstrap-ham",
        description="Learn all messages in an administrator-selected Carbonio folder as Ham.",
    )
    parser.add_argument("--config", default="/etc/carbonio-bayes-trainer.yaml")
    parser.add_argument("--account", required=True, help="Carbonio mailbox address")
    parser.add_argument("--folder", required=True, help="Full mailbox folder path")
    parser.add_argument("--recursive", action="store_true", help="Include subfolders")
    parser.add_argument("--dry-run", action="store_true", help="Export and count without training")
    parser.add_argument("--limit", type=int, help="Maximum number of messages to process")
    parser.add_argument("--verbose", action="store_true")
    return parser


def _migration_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="carbonio-bayes-trainer migrate-stable-keys",
        description="Backfill stable message identities without SpamAssassin training.",
    )
    parser.add_argument("--config", default="/etc/carbonio-bayes-trainer.yaml")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count legacy rows without exporting or changing messages",
    )
    parser.add_argument("--limit", type=int, help="Maximum number of legacy rows to process")
    parser.add_argument("--verbose", action="store_true")
    return parser


def _cleanup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="carbonio-bayes-trainer cleanup-legacy",
        description="Remove legacy message-state rows that have no stable key.",
    )
    parser.add_argument("--config", default="/etc/carbonio-bayes-trainer.yaml")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count legacy rows without deleting anything",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def _print_progress(
    folder_number: int,
    total_folders: int,
    folder: MailFolder,
    exported: int | None,
) -> None:
    prefix = f"[{folder_number:>{len(str(total_folders))}}/{total_folders}]"
    if exported is None:
        print(f"{prefix} Exporting {folder.path} ...", flush=True)
        return

    suffix = "message" if exported == 1 else "messages"
    empty = " (empty)" if exported == 0 else ""
    print(f"{prefix} Done: {exported} {suffix}{empty}", flush=True)


def run_bootstrap(argv: list[str]) -> int:
    args = _bootstrap_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    trainer = SpamAssassinTrainer(
        sa_learn_path=config.sa_learn_path,
        spamassassin_home=config.spamassassin_home,
        max_message_size=config.max_message_size,
    )
    bootstrapper = HamBootstrapper(
        zmmailbox_path=config.zmmailbox_path,
        trainer=trainer,
        batch_size=config.batch_size,
    )

    print(f"Account:   {args.account}")
    print(f"Folder:    {args.folder}")
    print(f"Recursive: {args.recursive}")
    print(f"Mode:      {'dry-run' if args.dry_run else 'learn'}")
    if args.limit is not None:
        print(f"Limit:     {args.limit}")
    print(f"SA HOME:   {config.spamassassin_home or 'process default'}")
    print()

    result = bootstrapper.run(
        account=args.account,
        folder_path=args.folder,
        recursive=args.recursive,
        dry_run=args.dry_run,
        limit=args.limit,
        progress=_print_progress,
    )

    print()
    print("Ham bootstrap complete")
    print(f"Folders:  {result.folders}")
    print(f"Exported: {result.exported}")
    print(f"Learned:  {result.learned}")
    print(f"Failed:   {result.failed}")
    print(f"Duration: {result.duration_seconds:.1f} seconds")
    if args.dry_run:
        print("No training was performed.")
    return 1 if result.failed else 0


def run_migration(argv: list[str]) -> int:
    args = _migration_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    backend = CarbonioBackend(
        zmmailbox_path=config.zmmailbox_path,
        max_messages_per_folder=config.max_messages_per_folder,
    )

    with StateDatabase(config.database_path) as database:
        result = StableKeyMigrator(backend, database).run(
            dry_run=args.dry_run,
            limit=args.limit,
        )

    print("Stable-key migration complete")
    print(f"Legacy rows: {result.total}")
    print(f"Migrated:    {result.migrated}")
    print(f"Skipped:     {result.skipped}")
    print(f"Failed:      {result.failed}")
    if args.dry_run:
        print("Dry-run only: no messages were exported and no database rows were changed.")
    else:
        print("No SpamAssassin training was performed.")
    return 1 if result.failed else 0


def run_cleanup(argv: list[str]) -> int:
    args = _cleanup_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    lock_path = config.database_path.with_name(f"{config.database_path.name}.scan.lock")

    try:
        with ScanLock(lock_path):
            with StateDatabase(config.database_path) as database:
                result = LegacyStateCleaner(database).run(dry_run=args.dry_run)
    except ScanAlreadyRunning as exc:
        print(str(exc), file=sys.stderr)
        return 75

    print("Legacy state cleanup complete")
    print(f"Legacy rows found:   {result.found}")
    print(f"Legacy rows deleted: {result.deleted}")
    if args.dry_run:
        print("Dry-run only: no database rows were changed.")
    else:
        print("SpamAssassin Bayes data and training history were not changed.")
        print("Messages still present in Carbonio will be rediscovered on normal scans.")
    return 0


def _forward_global_args(arguments: list[str]) -> list[str]:
    forwarded: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--config" and index + 1 < len(arguments):
            forwarded.extend((argument, arguments[index + 1]))
            index += 2
            continue
        if argument == "--verbose":
            forwarded.append(argument)
            index += 1
            continue
        raise SystemExit(f"Unknown global argument before command: {argument}")
    return forwarded


def _config_path(arguments: list[str]) -> str:
    try:
        index = arguments.index("--config")
    except ValueError:
        return "/etc/carbonio-bayes-trainer.yaml"
    if index + 1 >= len(arguments):
        raise SystemExit("--config requires a path")
    return arguments[index + 1]


def _run_legacy_with_scan_lock(argv: list[str]) -> None:
    if "scan" not in argv:
        legacy_main()
        return

    config = load_config(_config_path(argv))
    lock_path = config.database_path.with_name(f"{config.database_path.name}.scan.lock")
    try:
        with ScanLock(lock_path):
            legacy_main()
    except ScanAlreadyRunning as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(75) from exc


def main() -> None:
    argv = sys.argv[1:]
    known_commands = (
        "bootstrap-ham",
        "cleanup-legacy",
        "migrate-stable-keys",
        "stats",
    )
    commands = [command for command in known_commands if command in argv]
    if not commands:
        _run_legacy_with_scan_lock(argv)
        return
    if len(commands) > 1:
        raise SystemExit("Only one command may be specified")

    command = commands[0]
    command_index = argv.index(command)
    forwarded = _forward_global_args(argv[:command_index])
    command_args = argv[command_index + 1 :]

    if command == "bootstrap-ham":
        raise SystemExit(run_bootstrap([*forwarded, *command_args]))
    if command == "cleanup-legacy":
        raise SystemExit(run_cleanup([*forwarded, *command_args]))
    if command == "migrate-stable-keys":
        raise SystemExit(run_migration([*forwarded, *command_args]))
    raise SystemExit(run_stats([*forwarded, *command_args]))


if __name__ == "__main__":
    main()
