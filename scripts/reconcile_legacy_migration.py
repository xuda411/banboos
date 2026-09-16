"""CLI: reconcile Canonical records with a verified legacy snapshot."""
import argparse
import json

from packages.application.legacy_reconciliation import reconcile_legacy_migration


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    print(json.dumps(reconcile_legacy_migration(args.manifest, args.target), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
