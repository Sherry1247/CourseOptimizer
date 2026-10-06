"""Build the versioned BadgerPlan catalog snapshot from raw source exports.

    python scripts/build_snapshot.py \
        --guide data/raw/guide --uwcm data/raw/uwcm \
        --out data/snapshot/badgerplan-2026-27.json.gz

Inputs
  guide/courses_raw.json         every course block from guide.wisc.edu/courses/*
  guide/programs_raw.json        every bachelor's program requirements tab
  guide/named_options_raw.json   named-option pages linked from programs
  uwcm/course/*.json             uw-coursemap-data course exports (Madgrades history)
  uwcm/instructors/*.json        uw-coursemap-data instructor exports (RMP aggregates)

The snapshot is plain JSON so it can be diffed between catalog years and
loaded into SQLite (``scripts/init_db.py``) without network access.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from degree_rules import profile_for  # noqa: E402
from ingest.codes import CodeIndex, clean, parse_credit_range, split_code  # noqa: E402
from ingest.designations import parse_designations  # noqa: E402
from ingest.guide_parser import ProgramParser  # noqa: E402
from ingest import uwcm  # noqa: E402
from requisites import courses_in, parse_requisite  # noqa: E402

CATALOG_YEAR = "2026-2027"


def canonical_key(code: str) -> tuple:
    parts = split_code(code)
    if not parts:
        return (code,)
    return (tuple(sorted(parts[0])), parts[1])


SMALL_WORDS = {"and", "of", "in", "the", "for", "to", "a", "an", "on", "with", "at", "by", "or", "from"}
KEEP_UPPER = {"I", "II", "III", "IV", "V", "VI", "US", "U.S.", "UW", "AI", "HIV", "AIDS", "STEM", "DNA", "RNA", "GIS", "UI", "UX", "CAD", "ESL", "LGBTQ", "LGBTQ+", "ROTC", "MRI", "EU"}


def smart_title(text: str) -> str:
    words = clean(text).split(" ")
    out = []
    for index, word in enumerate(words):
        core = word.strip("():,-")
        if core.upper() in KEEP_UPPER:
            out.append(word.upper())
        elif index and word.lower() in SMALL_WORDS:
            out.append(word.lower())
        else:
            out.append("-".join(part[:1].upper() + part[1:].lower() for part in word.split("-")))
    return " ".join(out)


def guide_course_url(code: str) -> str:
    parts = split_code(code)
    subject = parts[0][0] if parts else code
    slug = re.sub(r"[^a-z0-9]+", "_", subject.lower()).strip("_")
    return f"https://guide.wisc.edu/courses/{slug}/"


def offering_summary(record: dict | None, last_taught: str | None) -> dict:
    seasons: list[str] = []
    confidence = "unknown"
    counts = (record or {}).get("season_counts") or {}
    typically = (record or {}).get("typically_offered")
    published = [s for s in ("Fall", "Spring", "Summer") if typically and s.lower() in typically.lower()]
    if counts and sum(counts.values()):
        # Five years of Madgrades history is the most reliable signal; the
        # published "typically offered" field is unioned in, never trusted alone.
        recent = set((record or {}).get("recent_seasons") or [])
        for season in ("Fall", "Spring", "Summer"):
            n = counts.get(season, 0)
            if n >= 2 or (n >= 1 and season in recent) or season in published:
                seasons.append(season)
        confidence = "history"
        if not seasons:
            seasons = [s for s in ("Fall", "Spring", "Summer") if counts.get(s)]
            confidence = "irregular"
    elif published:
        seasons = published
        confidence = "published"
    frequency = "unknown"
    if counts:
        fall, spring = counts.get("Fall", 0), counts.get("Spring", 0)
        if fall >= 4 and spring >= 4:
            frequency = "every semester"
        elif fall >= 3 or spring >= 3:
            frequency = "yearly"
        elif fall + spring:
            frequency = "irregular"
    return {"seasons": seasons, "confidence": confidence, "frequency": frequency, "counts": counts}


def _block_min_credits(block: dict, credit_of: dict[str, float]) -> float:
    def slot_credits(slot):
        if slot.get("credits"):
            return slot["credits"][0]
        if slot["options"]:
            return min(sum(credit_of.get(code, 3.0) for code in bundle) for bundle in slot["options"])
        return 0.0
    slots = block.get("slots", [])
    if block["rule"] == "all":
        return sum(slot_credits(s) for s in slots)
    if block["rule"] == "choose":
        values = sorted(slot_credits(s) for s in slots)
        return sum(values[: block.get("count") or 1])
    if block["rule"] in {"credits", "pattern", "text"}:
        return block.get("credits") or 0.0
    return 0.0


def build(guide_dir: Path, uwcm_dir: Path | None) -> dict:
    raw_courses = json.loads((guide_dir / "courses_raw.json").read_text(encoding="utf-8"))
    programs_raw = json.loads((guide_dir / "programs_raw.json").read_text(encoding="utf-8"))
    options_path = guide_dir / "named_options_raw.json"
    options_raw = json.loads(options_path.read_text(encoding="utf-8")) if options_path.exists() else []

    # --- courses: merge duplicate cross-list spellings ------------------------
    seen: dict[tuple, dict] = {}
    duplicate_aliases: dict[str, str] = {}
    for item in raw_courses:
        code = clean(item["code"]).upper()
        key = canonical_key(code)
        if key in seen:
            duplicate_aliases[code] = seen[key]["code"]
            continue
        seen[key] = {**item, "code": code}
    codes = CodeIndex([course["code"] for course in seen.values()])

    courses: list[dict] = []
    for item in seen.values():
        extras = item.get("x") or {}
        credits_min, credits_max = parse_credit_range(item.get("credits", ""))
        design = parse_designations(extras.get("Course Designation") or [])
        req = parse_requisite(extras.get("Requisites", ""), codes)
        parts = split_code(item["code"])
        courses.append({
            "code": item["code"],
            "subjects": parts[0] if parts else [],
            "number": parts[1] if parts else "",
            "title": smart_title(item.get("title", "")),
            "credits": [credits_min, credits_max],
            "description": clean(item.get("desc", "")),
            "requisite_text": req["text"],
            "requisites": req["tree"],
            "exclusions": req["exclusions"],
            "concurrent": req["concurrent"],
            "tags": design["tags"],
            "breadth_choice": design["breadth_choice"],
            "language_level": design["language_level"],
            "repeatable": clean(extras.get("Repeatable for Credit", "")),
            "last_taught": clean(extras.get("Last Taught", "")) or None,
            "guide_url": guide_course_url(item["code"]),
        })
    by_code = {course["code"]: course for course in courses}

    # --- Madgrades + offering history + instructors ---------------------------
    instructors: dict[str, dict] = {}
    if uwcm_dir and (uwcm_dir / "course").exists():
        grade_data = uwcm.read_courses(uwcm_dir / "course", codes)
        recent_names: Counter = Counter()
        course_instructors: dict[str, dict[str, str]] = {}
        for code, record in grade_data.items():
            course = by_code.get(code)
            if not course:
                continue
            course["grades"] = {"cumulative": record["cumulative"], "terms": record["terms"]}
            course["keywords"] = record["keywords"][:6]
            course["offering"] = offering_summary(record, course["last_taught"])
            taught: dict[str, dict] = {}
            for term, names in sorted(record["instructors_by_term"].items()):
                if int(term) < 1222:
                    continue
                for name in names:
                    entry = taught.setdefault(name.upper(), {"terms": 0, "last_term": term})
                    entry["terms"] += 1
                    entry["last_term"] = max(entry["last_term"], term)
                    recent_names[name.upper()] += 1
            course_instructors[code] = taught
        if (uwcm_dir / "instructors").exists():
            wanted = set(recent_names)
            instructors = uwcm.read_instructors(uwcm_dir / "instructors", wanted)
        for code, taught in course_instructors.items():
            def rank(item):
                name, entry = item
                info = instructors.get(name) or {}
                rmp = info.get("rmp") or {}
                return (1 if rmp else 0, entry["terms"], entry["last_term"], rmp.get("count") or 0)
            rows = [{"name": name, **entry} for name, entry in sorted(taught.items(), key=rank, reverse=True)]
            by_code[code]["instructors"] = rows[:24]
    for course in courses:
        course.setdefault("offering", offering_summary(None, course["last_taught"]))
        course.setdefault("grades", None)
        course.setdefault("instructors", [])
        course.setdefault("keywords", [])

    # --- programs -------------------------------------------------------------
    credit_of = {course["code"]: course["credits"][0] or 3.0 for course in courses}
    parser = ProgramParser(codes, credit_of)
    programs: list[dict] = []
    parents = {raw["href"]: raw for raw in programs_raw}
    for raw in programs_raw:
        program = parser.parse(raw)
        program["parent_id"] = None
        programs.append(program)
    for raw in options_raw:
        parent = parents.get(raw.get("parent"))
        if parent:
            parent_program = next(p for p in programs if p["url"].endswith(parent["href"]))
            name = clean(raw.get("name") or raw.get("title") or "")
            name = re.sub(r"\s+requirements?$", "", name, flags=re.I)
            if ":" not in name:
                # "Mathematical Emphasis" -> "Economics: Mathematical Emphasis"
                parent_base = parent_program["name"].rsplit(",", 1)[0]
                name = f"{parent_base}: {name}"
            if not re.search(r",\s*B[A-Z]+", name or ""):
                name = f"{name}, {parent_program['degree']}" if parent_program["degree"] else name
            raw = {**raw, "name": name}
        program = parser.parse(raw)
        if parent:
            program["parent_id"] = parent_program["id"]
            program["college"] = program["college"] or parent_program["college"]
            program["degree"] = program["degree"] or parent_program["degree"]
            if not program["blocks"]:
                continue
            # Named options inherit the college requirements of the parent page.
            if not any(b["section"] == "college" for b in program["blocks"]):
                program["blocks"] = [b for b in parent_program["blocks"] if b["section"] == "college"] + program["blocks"]
            # Some named options (common in Engineering) list only the courses
            # specific to the option; the parent's base curriculum still applies.
            own_major = [b for b in program["blocks"] if b["section"] == "major"]
            own_credits = sum(_block_min_credits(b, credit_of) for b in own_major)
            parent_major = [b for b in parent_program["blocks"] if b["section"] == "major" and not b.get("variant_group")]
            if parent_major and own_credits < 30:
                own_keys = {b["name"] for b in own_major}
                inherited = [dict(b, name=b["name"]) for b in parent_major if b["name"] not in own_keys]
                program["blocks"] = [b for b in program["blocks"] if b["section"] == "college"] + inherited + own_major
                program["inherits_parent"] = True
        programs.append(program)

    ids: Counter = Counter()
    for program in programs:
        ids[program["id"]] += 1
        if ids[program["id"]] > 1:
            program["id"] = f"{program['id']}-{ids[program['id']]}"
        program["profile"] = profile_for(program["college"], program["degree"])
        program["has_named_options"] = any(p.get("parent_id") == program["id"] for p in programs)

    # --- prerequisite graph edges --------------------------------------------
    for course in courses:
        course["prereq_codes"] = sorted(courses_in(course["requisites"]))

    aliases = {alias: canonical for alias, canonical in codes.items()}
    aliases.update(duplicate_aliases)
    stats = {
        "courses": len(courses),
        "courses_with_requisites": sum(1 for c in courses if c["requisites"]),
        "courses_with_grades": sum(1 for c in courses if c.get("grades")),
        "courses_with_offering_history": sum(1 for c in courses if c["offering"]["confidence"] in {"history", "published"}),
        "instructors": len(instructors),
        "instructors_with_rmp": sum(1 for i in instructors.values() if i.get("rmp")),
        "programs": len(programs),
        "programs_by_confidence": dict(Counter(p["confidence"] for p in programs)),
        "unresolved_requirement_codes": sorted(parser.unresolved),
    }
    return {
        "meta": {
            "catalog_year": CATALOG_YEAR,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sources": [
                {"name": "UW–Madison Guide 2026–2027", "url": "https://guide.wisc.edu/", "authority": "official",
                 "use": "Programs, requirements, courses, credits, designations, requisites"},
                {"name": "uw-coursemap-data (uwcourses.com)", "url": "https://github.com/twangodev/uw-coursemap-data",
                 "authority": "community", "license": "MIT",
                 "use": "Madgrades grade distributions, term history, instructor lists, RMP aggregates"},
                {"name": "Madgrades", "url": "https://madgrades.com/", "authority": "community",
                 "use": "Original source of grade distributions (via uw-coursemap-data)"},
                {"name": "Rate My Professors", "url": "https://www.ratemyprofessors.com/school/1256", "authority": "community",
                 "use": "Aggregate rating/difficulty only; reviews are linked, not copied"},
            ],
            "stats": stats,
        },
        "courses": courses,
        "aliases": aliases,
        "instructors": instructors,
        "programs": programs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guide", type=Path, default=ROOT / "data" / "raw" / "guide")
    parser.add_argument("--uwcm", type=Path, default=ROOT / "data" / "raw" / "uwcm")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "snapshot" / "badgerplan-2026-27.json.gz")
    args = parser.parse_args()
    snapshot = build(args.guide, args.uwcm if args.uwcm.exists() else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(snapshot["meta"]["stats"], indent=2)[:2000])
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
