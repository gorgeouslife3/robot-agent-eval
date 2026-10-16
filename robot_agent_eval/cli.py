"""CLI for the local evaluation workspace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import METHODS
from .common import ROBODOJO, SIM_PYTHON


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("methods")
    fetch = sub.add_parser("fetch-sources")
    fetch.add_argument("--jobs", type=int, default=4)
    snapshots = sub.add_parser("fetch-snapshots")
    snapshots.add_argument("--jobs", type=int, default=4)
    inventory = sub.add_parser("inventory")
    inventory.add_argument("--robodojo", type=Path, default=ROBODOJO)
    inventory.add_argument("--python", default=SIM_PYTHON)
    args = parser.parse_args()
    if args.command == "methods":
        print(json.dumps(METHODS, indent=2, ensure_ascii=False))
    elif args.command == "fetch-sources":
        from .sources import fetch_sources
        fetch_sources(args.root, args.jobs)
    elif args.command == "fetch-snapshots":
        from .snapshots import fetch_snapshots
        fetch_snapshots(args.root, args.jobs)
    elif args.command == "inventory":
        from .inventory import build_inventory
        p = build_inventory(args.robodojo, args.root, args.python)
        print(json.dumps({k: p[k] for k in ["counts", "test_cases", "development_cases"]}, indent=2))


if __name__ == "__main__":
    main()
