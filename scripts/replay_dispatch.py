"""Replay a strict-dispatch snapshot without connecting to any database."""
from __future__ import annotations

import argparse
import json

from packages.application.dispatch_replay import replay


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_id", help="64-character snapshot hash")
    args = parser.parse_args()
    print(json.dumps(replay(args.snapshot_id).model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
