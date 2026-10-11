from __future__ import annotations

import argparse
import logging
import time

from .config import Config
from .pipeline import Pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Fantasy Premier League CSV datasets")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("refresh", help="run a full refresh now")
    commands.add_parser("update", help="refresh datasets whose configured interval has elapsed")
    commands.add_parser("backfill", help="refresh all players' full history now")
    commands.add_parser("schedule", help="run repeated refreshes")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = Config.from_env()
    if args.command == "refresh":
        report = Pipeline(config).refresh(full=True)
        return 1 if report["failed"] else 0
    if args.command == "update":
        report = Pipeline(config).refresh()
        return 1 if report["failed"] else 0
    if args.command == "backfill":
        report = Pipeline(config).refresh(full=True, historical_backfill=True)
        return 1 if report["failed"] else 0
    pipeline = Pipeline(config)
    while True:
        pipeline.refresh()
        time.sleep(min(config.refresh_hours * 3600, config.live_minutes * 60))


if __name__ == "__main__":
    raise SystemExit(main())
