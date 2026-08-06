from __future__ import annotations

import argparse

from .config import load_config
from .health import HealthEvaluator
from .health_format import format_health
from .stats import StatisticsCollector, format_statistics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="carbonio-bayes-trainer stats",
        description="Show operational statistics for Carbonio Bayes Trainer.",
    )
    parser.add_argument(
        "--config",
        default="/etc/carbonio-bayes-trainer.yaml",
        help="Path to the YAML configuration file",
    )
    return parser


def run_stats(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    statistics = StatisticsCollector(load_config(args.config)).collect()
    health = HealthEvaluator().evaluate(statistics)
    print(format_statistics(statistics))
    print()
    print(format_health(health))
    return 0
