"""CLI: migrate a verified 1.6.6 snapshot into Raw/Quality/Canonical staging."""
import argparse
import json

from packages.application.legacy_migration import migrate_legacy_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="snapshot manifest.json")
    parser.add_argument("--target", required=True, help="staging SQLite path on E:")
    args = parser.parse_args()
    print(json.dumps(migrate_legacy_snapshot(args.manifest, args.target), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
