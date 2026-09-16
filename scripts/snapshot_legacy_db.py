"""CLI: make a verified, read-only snapshot of a 1.6.6 SQLite database."""
from __future__ import annotations

import argparse
import json

from packages.application.legacy_snapshot import snapshot_legacy_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="1.6.6 SQLite database path")
    parser.add_argument("--destination", default="var/legacy-snapshots")
    parser.add_argument("--migration-version", default="legacy-snapshot-v1")
    args = parser.parse_args()
    manifest = snapshot_legacy_database(args.source, args.destination, args.migration_version)
    print(json.dumps(json.loads(manifest.read_text(encoding="utf-8")), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
