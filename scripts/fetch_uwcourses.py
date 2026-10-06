"""Download the open uw-coursemap-data export (the data behind uwcourses.com).

    python scripts/fetch_uwcourses.py --out data/raw/uwcm

Source: https://github.com/twangodev/uw-coursemap-data (MIT license).  Each
course file holds Madgrades grade distributions per term (with instructors);
each instructor file holds Rate My Professors aggregates.  Only aggregates are
used by BadgerPlan -- review text is never stored or shown.

~8,900 course files + ~19,000 instructor files (~215 MB).  Re-running skips
files that already exist, so an interrupted download can be resumed.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import html
from pathlib import Path
import re
from urllib.parse import quote

import requests

RAW = "https://raw.githubusercontent.com/twangodev/uw-coursemap-data/main/"


def sitemap_ids(session: requests.Session, name: str, kind: str) -> list[str]:
    text = session.get(RAW + name, timeout=60).text
    return [html.unescape(match) for match in re.findall(rf"/{kind}/([^<]+)</loc>", text)]


def download(session: requests.Session, folder: Path, kind: str, item: str) -> bool:
    target = folder / kind / f"{item}.json"
    if target.exists() and target.stat().st_size > 20:
        return True
    for _ in range(4):
        try:
            response = session.get(RAW + f"{kind}/{quote(item)}.json", timeout=60)
            if response.status_code == 404:
                return False
            response.raise_for_status()
            target.write_bytes(response.content)
            return True
        except requests.RequestException:
            continue
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "raw" / "uwcm")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--skip-instructors", action="store_true")
    args = parser.parse_args()
    session = requests.Session()
    jobs = [("course", sitemap_ids(session, "courses-sitemap.xml", "courses"))]
    if not args.skip_instructors:
        jobs.append(("instructors", sitemap_ids(session, "instructors-sitemap.xml", "instructors")))
    for kind, ids in jobs:
        (args.out / kind).mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(args.workers) as pool:
            ok = sum(pool.map(lambda item: download(session, args.out, kind, item), ids))
        print(f"{kind}: {ok}/{len(ids)} files in {args.out / kind}")


if __name__ == "__main__":
    main()
