"""Inspect explicitly supplied PUBLIC JSONL only, in no-credential isolation.

Never point this helper at real DSH homes/private logs. Native events are counted
but not represented as validated DSH persistence/recovery evidence.
"""
import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("public_jsonl", type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.public_jsonl.read_text(encoding="utf-8").splitlines()]
    print(json.dumps({"rows": len(rows), "json_parsed": True, "sdk_restore_verified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
