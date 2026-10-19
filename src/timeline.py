"""Enrollment timeline: appointment windows, add/drop deadlines and term dates.

Inputs are the Registrar's published appointment windows
(``data/academic_dates.json``) and the session dates saved from Course Search &
Enroll (``enroll.EnrollStore``). Every event names its source; dates that are
estimates say so.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from enroll import EnrollStore, term_code, term_name

ROOT = Path(__file__).resolve().parents[1]
DATES_FILE = ROOT / "data" / "academic_dates.json"
STANDINGS = ["Freshman", "Sophomore", "Junior", "Senior"]
PLURAL = {"Freshman": "Freshmen", "Sophomore": "Sophomores", "Junior": "Juniors", "Senior": "Seniors"}


def load_dates(path: Path = DATES_FILE) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"appointments": {}, "sources": {}, "standing_thresholds": {}}


def standing_for(credits: float, thresholds: dict | None = None) -> str:
    thresholds = thresholds or {"Sophomore": 24, "Junior": 54, "Senior": 86}
    standing = "Freshman"
    for name in STANDINGS[1:]:
        if credits >= thresholds.get(name, 10 ** 6):
            standing = name
    return standing


def next_standing(standing: str) -> str:
    """Enrollment appointments use projected standing for the term being enrolled."""
    index = STANDINGS.index(standing) if standing in STANDINGS else 0
    return STANDINGS[min(index + 1, len(STANDINGS) - 1)]


def build_timeline(store: EnrollStore, dates: dict, standing: str | None = None,
                   today: date | None = None, include_past: bool = False) -> dict:
    today = today or date.today()
    sources = dates.get("sources", {})
    events: list[dict] = []
    terms = []
    known_codes = set(store.terms) | set(dates.get("appointments", {}))
    for code in sorted(known_codes):
        name = term_name(code)
        snapshot = store.terms.get(code) or {}
        term = snapshot.get("term") or {"code": code, "name": name}
        terms.append({"code": code, "name": name, "classes_begin": term.get("classes_begin"),
                      "classes_end": term.get("classes_end")})
        appointment = (dates.get("appointments") or {}).get(code)
        if appointment:
            if appointment.get("published"):
                for window in appointment.get("windows", []):
                    mine = standing is not None and window["group"] == standing
                    events.append({
                        "date": window["start"], "end": window["end"], "term": code, "kind": "enroll",
                        "title": f"{name} enrollment opens · {PLURAL.get(window['group'], window['group'])}",
                        "detail": appointment.get("note", ""), "mine": mine, "estimate": False,
                        "source": sources.get("appointments"),
                    })
            elif appointment.get("estimate"):
                window = appointment["estimate"]
                events.append({
                    "date": window["start"], "end": window["end"], "term": code, "kind": "enroll",
                    "title": f"{name} priority enrollment (expected)", "detail": appointment.get("note", ""),
                    "mine": True, "estimate": True, "source": sources.get("appointments"),
                })
        if term.get("classes_begin"):
            events.append({"date": term["classes_begin"], "term": code, "kind": "term", "title": f"{name} classes begin",
                           "detail": "", "mine": True, "estimate": False, "source": sources.get("deadlines")})
        regular = (snapshot.get("sessions") or {}).get("A1")
        if regular:
            for key, title, detail in (
                ("drop_no_dr", "Last day to drop without a DR", "Dropping by this date leaves no record on your transcript (regular-session courses)."),
                ("add", "Last day to add a course", "Regular 15-week courses. Shorter sessions have their own dates in Enroll."),
                ("edit", "Last day to edit a course", "Course edits such as variable credits or pass/fail; confirm the rule for your section in Enroll."),
                ("drop", "Last day to drop a course", "After this date a course can only be dropped with a dean's approval. Drops after the first deadline show DR."),
            ):
                if regular.get(key):
                    events.append({"date": regular[key], "term": code, "kind": "deadline", "title": f"{name}: {title}",
                                   "detail": detail, "mine": True, "estimate": False, "source": sources.get("deadlines")})
        if term.get("classes_end"):
            events.append({"date": term["classes_end"], "term": code, "kind": "term", "title": f"{name} last day of classes",
                           "detail": "Final exams follow; each section's exam time is in Enroll.", "mine": True,
                           "estimate": False, "source": sources.get("deadlines")})
    if not include_past:
        events = [e for e in events if (e.get("end") or e["date"]) >= today.isoformat()]
    events.sort(key=lambda e: (e["date"], e["kind"] != "enroll"))
    return {"today": today.isoformat(), "standing": standing, "terms": terms, "events": events,
            "thresholds": dates.get("standing_thresholds", {}), "sources": sources}


def current_and_next_term(today: date | None = None) -> tuple[tuple[str, int], tuple[str, int]]:
    today = today or date.today()
    if today.month >= 9:
        return ("Fall", today.year), ("Spring", today.year + 1)
    if today.month >= 6:
        return ("Summer", today.year), ("Fall", today.year)
    return ("Spring", today.year), ("Fall", today.year)


def term_code_for(season: str, year: int) -> str:
    return term_code(season, year)
