from __future__ import annotations

import argparse
import os
import time

from .app import create_app
from .storage import cleanup_orphan_files


def run_once(dry_run=False):
    app = create_app()
    with app.app_context():
        result = cleanup_orphan_files(app, dry_run=dry_run)
        print(
            f"orphan-cleanup deleted={len(result['deleted'])} "
            f"skipped_recent={len(result['skipped_recent'])} "
            f"retention_hours={result['retention_hours']} dry_run={dry_run}"
        )


def main():
    parser = argparse.ArgumentParser(description="colf-manager storage maintenance")
    parser.add_argument("--once", action="store_true", help="run one cleanup and exit")
    parser.add_argument("--loop", action="store_true", help="run cleanup periodically")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.loop:
        interval = max(int(os.getenv("COLF_MANAGER_MAINTENANCE_INTERVAL_SECONDS", "86400")), 3600)
        while True:
            run_once(args.dry_run)
            time.sleep(interval)
    run_once(args.dry_run)


if __name__ == "__main__":
    main()
