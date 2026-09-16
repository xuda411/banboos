"""CLI: reconcile Canonical records with a verified legacy snapshot."""
import argparse
import json

from packages.application.legacy_reconciliation import reconcile_legacy_migration


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--target", required=True)
    parser.add_argument("--node-id", type=int)
    parser.add_argument("--market", choices=["日前", "实时"])
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = json.dumps(reconcile_legacy_migration(args.manifest, args.target, args.node_id, args.market, args.start_date, args.end_date), ensure_ascii=False, indent=2)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
