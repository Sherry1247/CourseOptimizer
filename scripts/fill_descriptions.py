"""Restore course descriptions that the first Guide scrape cut at 600 characters.

Earlier snapshots stored ``desc[:600]``. This script looks up each truncated
course in uw-coursemap-data (MIT, mirrors the Guide description) and replaces
the text only when the published description starts with what we already
have, so a mismatch can never swap in another course's text.

    python scripts/fill_descriptions.py && python scripts/init_db.py --force
"""

from __future__ import annotations

import concurrent.futures
import gzip
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "snapshot" / "badgerplan-2026-27.json.gz"
BASE = "https://raw.githubusercontent.com/twangodev/uw-coursemap-data/main/course/"
TRUNCATED_AT = 598


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def squash(text: str) -> str:
    return re.sub(r"\W+", "", text or "").lower()


def lookup(course: dict) -> str | None:
    subjects = course["subjects"]
    if isinstance(subjects, str):
        subjects = json.loads(subjects.replace("'", '"'))
    have = norm(course["description"])
    for subject in subjects:
        name = f"{subject.replace(' ', '')}_{course['number']}.json"
        try:
            with urllib.request.urlopen(BASE + urllib.parse.quote(name), timeout=30) as response:
                text = norm(json.load(response).get("description", ""))
        except (urllib.error.URLError, ValueError, OSError):
            continue
        if len(text) > len(have) and squash(text)[:160] == squash(have)[:160]:
            return text
    return None


def main() -> int:
    with gzip.open(SNAPSHOT, "rt", encoding="utf-8") as handle:
        snapshot = json.load(handle)
    todo = [c for c in snapshot["courses"] if len(c.get("description") or "") >= TRUNCATED_AT]
    print(f"{len(todo)} descriptions at the old 600-character cap")
    fixed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        for course, text in zip(todo, pool.map(lookup, todo)):
            if text:
                course["description"] = text
                fixed += 1
    with gzip.open(SNAPSHOT, "wt", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, separators=(",", ":"))
    print(f"restored {fixed}; {len(todo) - fixed} left as-is")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
