"""Report whether the host can perform native Excel/WPS formula recalculation."""
from __future__ import annotations

import json

from packages.application.spreadsheet_engine import detect_spreadsheet_engines


def main() -> int:
    result = detect_spreadsheet_engines()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "available" else 2


if __name__ == "__main__":
    raise SystemExit(main())
