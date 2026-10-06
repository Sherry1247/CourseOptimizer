"""Read the open uw-coursemap-data export (the data behind uwcourses.com).

Source: https://github.com/twangodev/uw-coursemap-data (MIT license).  Each
course file carries Madgrades grade distributions per term (with the list of
instructors that term) and each instructor file carries Rate My Professors
aggregates.  BadgerPlan keeps only aggregates -- never review text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .codes import CodeIndex, term_code_to_label

GRADE_KEYS = ("a", "ab", "b", "bc", "c", "d", "f")
GRADE_POINTS = {"a": 4.0, "ab": 3.5, "b": 3.0, "bc": 2.5, "c": 2.0, "d": 1.0, "f": 0.0}
EXTRA_KEYS = ("satisfactory", "unsatisfactory", "credit", "no_credit", "passed", "incomplete", "no_work", "not_reported", "other")
RECENT_TERMS = 10  # keep the ten most recent terms per course


def gpa(dist: dict) -> float | None:
    graded = sum(dist.get(key, 0) or 0 for key in GRADE_KEYS)
    if not graded:
        return None
    points = sum((dist.get(key, 0) or 0) * GRADE_POINTS[key] for key in GRADE_KEYS)
    return round(points / graded, 3)


def compact_distribution(dist: dict | None) -> dict | None:
    if not dist:
        return None
    out = {key: int(dist.get(key) or 0) for key in GRADE_KEYS}
    out["other"] = int(sum(dist.get(key) or 0 for key in EXTRA_KEYS))
    out["total"] = int(dist.get("total") or sum(out.values()))
    out["gpa"] = gpa(dist)
    return out


def iter_json(folder: Path) -> Iterator[dict]:
    for path in sorted(folder.glob("*.json")):
        try:
            yield json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue


def read_courses(folder: Path, codes: CodeIndex) -> dict[str, dict]:
    """Return {canonical_code: {...grade/offering data...}}."""

    result: dict[str, dict] = {}
    for data in iter_json(folder):
        ref = data.get("course_reference") or {}
        code = codes.resolve_ref(ref.get("subjects") or [], ref.get("course_number"))
        if not code:
            continue
        term_data = data.get("term_data") or {}
        terms = sorted(term_data, reverse=True)
        season_counts = {"Fall": 0, "Spring": 0, "Summer": 0}
        recent_seasons: set[str] = set()
        latest_terms = terms[:6]
        term_rows = []
        instructors_by_term: dict[str, list[str]] = {}
        for term in terms:
            season, year = term_code_to_label(term)
            if season in season_counts and int(term) >= 1212:
                season_counts[season] += 1
            if term in latest_terms and season in season_counts:
                recent_seasons.add(season)
            payload = term_data[term] or {}
            grades = payload.get("grade_data") or {}
            instructors = [name for name in (grades.get("instructors") or []) if name]
            enrollment = payload.get("enrollment_data") or {}
            if isinstance(enrollment.get("instructors"), dict):
                instructors.extend(name for name in enrollment["instructors"] if name not in instructors)
            instructors_by_term[term] = instructors
            if grades and len(term_rows) < RECENT_TERMS:
                dist = compact_distribution(grades)
                if dist and dist["total"]:
                    term_rows.append({"term": term, "label": f"{season} {year}", **dist, "instructors": instructors[:25]})
        typically = None
        for payload in term_data.values():
            enrollment = (payload or {}).get("enrollment_data") or {}
            if enrollment.get("typically_offered"):
                typically = enrollment["typically_offered"]
        existing = result.get(code)
        record = {
            "cumulative": compact_distribution(data.get("cumulative_grade_data")),
            "terms": term_rows,
            "season_counts": season_counts,
            "recent_seasons": sorted(recent_seasons),
            "typically_offered": typically,
            "instructors_by_term": instructors_by_term,
            "keywords": data.get("keywords") or [],
        }
        if existing is None or (record["cumulative"] or {}).get("total", 0) > (existing["cumulative"] or {}).get("total", 0):
            result[code] = record
    return result


def read_instructors(folder: Path, wanted: set[str]) -> dict[str, dict]:
    """Return {INSTRUCTOR NAME: {...}} for instructors that taught a catalog course."""

    result: dict[str, dict] = {}
    for path in sorted(folder.glob("*.json")):
        name_key = path.stem.replace("_", " ")
        if name_key not in wanted:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rmp = data.get("rmp_data") or {}
        name = data.get("name") or name_key
        result[name.upper()] = {
            "name": name.title(),
            "department": data.get("department"),
            "position": data.get("position"),
            "rmp": {
                "rating": _round(rmp.get("average_rating")),
                "difficulty": _round(rmp.get("average_difficulty")),
                "count": rmp.get("num_ratings"),
                "would_take_again": _round(rmp.get("would_take_again_percent")),
                "id": rmp.get("legacy_id"),
            } if rmp and rmp.get("num_ratings") else None,
            "cumulative": compact_distribution(data.get("cumulative_grade_data")),
        }
    return result


def _round(value):
    return None if value is None or value < 0 else round(float(value), 1)
