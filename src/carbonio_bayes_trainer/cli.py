from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

from .config import load_config
from .database import StateDatabase


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
    subparsers.add_parser(
        "scan",
        help="Run one mailbox scan (backend follows in the next milestone)",
    )
    return parser


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
    return 1 if failed else 0


def run_stats(config_path: str) -> int:
    config = load_config(config_path)
    with StateDatabase(config.database_path) as database:
        stats = database.stats()
    print(f"Spam learned: {stats['spam']}")
    print(f"Ham learned:  {stats['ham']}")
    return 0


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
        print("Mailbox scanning is intentionally not active yet; use doctor to validate the host.")
        raise SystemExit(0)
    parser.error(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
