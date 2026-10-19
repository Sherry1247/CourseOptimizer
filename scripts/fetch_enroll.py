"""Save a term from Course Search & Enroll into data/enroll/<term>.json.gz.

The snapshot holds the term dates, the add/drop deadlines of every session,
the list of courses with a published section and, unless --offered-only,
every course's enrollment packages (sections, meeting times, rooms, seats).

    python scripts/fetch_enroll.py                     # every term Enroll currently lists
    python scripts/fetch_enroll.py --term 1274         # Spring 2027 only
    python scripts/fetch_enroll.py --term 1274 --offered-only   # fast: ~15 requests
    python scripts/fetch_enroll.py --term 1274 --courses "COMP SCI 400,MATH 340"

Seats change by the minute; the app fetches a course live when it can, and
falls back to this snapshot when it cannot reach public.enroll.wisc.edu.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import enroll  # noqa: E402

OUT = ROOT / "data" / "enroll"


def offered_courses(term: str) -> list[dict]:
    rows, page = [], 1
    while True:
        result = enroll.search(term, "*", page=page, page_size=500)
        hits = result.get("hits") or []
        rows.extend(hits)
        if not hits or len(rows) >= (result.get("found") or 0) or page > 40:
            return rows
        page += 1


def packages_for(term: str, hit: dict, delay: float) -> dict:
    time.sleep(delay)
    code = " ".join(hit["courseDesignation"].split())
    raw = enroll._request(f"{enroll.API}/enrollmentPackages/{term}/{hit['subject']['subjectCode']}/{hit['courseId']}")
    return enroll.compact_course(code, hit, raw)


def save(term: str, snapshot: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{term}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(snapshot, handle, separators=(",", ":"))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--term", action="append", help="term code, e.g. 1274 (repeatable)")
    parser.add_argument("--offered-only", action="store_true", help="skip sections and seats")
    parser.add_argument("--courses", help="comma-separated course codes to fetch sections for")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.15, help="seconds between requests per worker")
    args = parser.parse_args()

    meta = enroll.aggregate()
    terms = {t["termCode"]: t for t in meta.get("terms") or []}
    sessions = {}
    for group in meta.get("sessions") or []:
        for raw in group.get("sessions") or []:
            if raw.get("medicalSession"):
                continue
            sessions.setdefault(raw["termCode"], {})[raw["sessionCode"]] = enroll.parse_session(raw)
    wanted = args.term or sorted(terms)
    for term in wanted:
        if term not in terms:
            print(f"{term}: Enroll does not list this term yet", file=sys.stderr)
            continue
        print(f"{term} {enroll.term_name(term)}: listing courses…", flush=True)
        hits = offered_courses(term)
        snapshot = {
            "term": enroll.parse_term(terms[term]),
            "sessions": sessions.get(term, {}),
            "offered": sorted({" ".join(h["courseDesignation"].split()) for h in hits}),
            "courses": {},
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "https://public.enroll.wisc.edu/",
        }
        targets = hits
        if args.courses:
            keys = {k for c in args.courses.split(",") for k in enroll.course_keys(c.strip())}
            targets = [h for h in hits if set(enroll.course_keys(h["courseDesignation"])) & keys]
        elif args.offered_only:
            targets = []
        print(f"  {len(hits)} courses offered; fetching sections for {len(targets)}", flush=True)
        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(packages_for, term, hit, args.delay): hit for hit in targets}
            for future in concurrent.futures.as_completed(futures):
                try:
                    course = future.result()
                    snapshot["courses"][course["code"]] = course
                except Exception as error:  # keep going; one bad course should not lose the term
                    print(f"  {futures[future].get('courseDesignation')}: {error}", file=sys.stderr)
                done += 1
                if done % 250 == 0:
                    print(f"  {done}/{len(targets)}", flush=True)
        path = save(term, snapshot)
        print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
