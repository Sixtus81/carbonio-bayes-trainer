from __future__ import annotations

import argparse
import logging
import sys

from .bootstrap import HamBootstrapper, MailFolder
from .cli import main as legacy_main
from .config import load_config
from .spamassassin import SpamAssassinTrainer


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


def main() -> None:
    argv = sys.argv[1:]
    if "bootstrap-ham" not in argv:
        legacy_main()
        return

    command_index = argv.index("bootstrap-ham")
    global_args = argv[:command_index]
    command_args = argv[command_index + 1 :]

    # Accept the existing global options before the subcommand.
    forwarded: list[str] = []
    index = 0
    while index < len(global_args):
        argument = global_args[index]
        if argument == "--config" and index + 1 < len(global_args):
            forwarded.extend((argument, global_args[index + 1]))
            index += 2
            continue
        if argument == "--verbose":
            forwarded.append(argument)
            index += 1
            continue
        raise SystemExit(f"Unknown global argument before bootstrap-ham: {argument}")

    raise SystemExit(run_bootstrap([*forwarded, *command_args]))


if __name__ == "__main__":
    main()