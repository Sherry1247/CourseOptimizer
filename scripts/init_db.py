"""Create (or rebuild with --force) the local SQLite catalog from the committed snapshot."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from catalog_db import DEFAULT_DB_PATH, DEFAULT_SNAPSHOT, initialize_database, meta  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--force", action="store_true", help="rebuild even if the database is current")
    args = parser.parse_args()
    path = initialize_database(args.db, args.snapshot, force=args.force)
    info = meta(path)
    stats = info["stats"]
    print(f"BadgerPlan catalog {info['catalog_year']} -> {path}")
    print(f"  courses {stats.get('courses')} | programs {stats.get('programs')} | instructors {stats.get('instructors')}")


if __name__ == "__main__":
    main()
