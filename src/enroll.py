"""Course Search & Enroll (public.enroll.wisc.edu) term data.

Two sources, used in this order:

1. Snapshots in ``data/enroll/<term>.json.gz`` written by ``scripts/fetch_enroll.py``:
   the term's dates, add/drop deadlines per session, the list of courses with
   at least one published section, and (optionally) every enrollment package.
2. Live requests to the public Enroll API for one course at a time, cached in
   ``data/enroll/cache/``. Live requests only work where the machine can reach
   public.enroll.wisc.edu; set ``BADGERPLAN_OFFLINE=1`` to turn them off.

Meeting times in Enroll are milliseconds after midnight UTC shifted by a fixed
six hours (they do not follow daylight saving), so 61200000 is 11:00 a.m.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "enroll"
CACHE_DIR = DATA_DIR / "cache"
API = "https://public.enroll.wisc.edu/api/search/v1"
TZ = ZoneInfo("America/Chicago")
TIME_SHIFT_MIN = 360
SEASON_DIGIT = {"Fall": "2", "Spring": "4", "Summer": "6"}
DIGIT_SEASON = {v: k for k, v in SEASON_DIGIT.items()}
CACHE_TTL = 6 * 3600


# ----------------------------------------------------------------------------- terms

def term_code(season: str, year: int) -> str:
    """UW term codes: 1 + two-digit academic-year end + season digit.

    Fall 2026 belongs to academic year 2026-27, so it is 1272; Spring 2027 is
    1274 and Summer 2027 is 1276.
    """
    academic_year = year + 1 if season == "Fall" else year
    return f"1{academic_year % 100:02d}{SEASON_DIGIT[season]}"


def term_name(code: str) -> str:
    season = DIGIT_SEASON.get(code[-1], "Term")
    academic_year = 2000 + int(code[1:3])
    year = academic_year - 1 if season == "Fall" else academic_year
    return f"{season} {year}"


def course_keys(code: str) -> list[str]:
    """'COMP SCI/MATH 240' -> ['COMP SCI 240', 'MATH 240']."""
    code = " ".join(code.upper().split())
    subjects, _, number = code.rpartition(" ")
    return [f"{s.strip()} {number}" for s in subjects.split("/") if s.strip()]


def local_date(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, TZ).date().isoformat()


def clock(ms: int | None) -> int | None:
    """Enroll meeting time (ms) -> minutes after local midnight."""
    if ms is None:
        return None
    return round(ms / 60000) - TIME_SHIFT_MIN


# ----------------------------------------------------------------------------- parsing

def parse_session(raw: dict) -> dict:
    return {
        "code": raw.get("sessionCode"),
        "name": raw.get("sessionDescription"),
        "begin": local_date(raw.get("beginDate")),
        "end": local_date(raw.get("endDate")),
        "add": local_date(raw.get("addDate")),
        "drop_no_dr": local_date(raw.get("drwDate")),
        "drop": local_date(raw.get("dropDate")),
        "edit": local_date(raw.get("editCourseDeadlineDate")),
    }


def parse_term(raw: dict) -> dict:
    return {
        "code": raw.get("termCode"),
        "name": term_name(raw.get("termCode", "0000")),
        "begin": local_date(raw.get("beginDate")),
        "end": local_date(raw.get("endDate")),
        "classes_begin": local_date(raw.get("instructionBeginDate")),
        "classes_end": local_date(raw.get("instructionEndDate")),
    }


def _instructor(entry: dict) -> str:
    name = entry.get("name") or {}
    return " ".join(part for part in (name.get("first"), name.get("last")) if part)


def parse_package(raw: dict) -> dict:
    """One enrollment package (a lecture with its discussion/lab) -> compact form."""
    status = raw.get("packageEnrollmentStatus") or {}
    meetings, exams = [], []
    for meeting in raw.get("classMeetings") or []:
        if meeting.get("meetingType") == "EXAM":
            if meeting.get("examDate"):
                exams.append({"date": meeting["examDate"], "start": clock(meeting.get("meetingTimeStart")),
                              "end": clock(meeting.get("meetingTimeEnd"))})
            continue
        if meeting.get("meetingType") != "CLASS" or not meeting.get("meetingDays"):
            continue
        building = meeting.get("building") or {}
        meetings.append({"days": meeting["meetingDays"], "start": clock(meeting.get("meetingTimeStart")),
                         "end": clock(meeting.get("meetingTimeEnd")), "building": building.get("buildingName"),
                         "room": meeting.get("room")})
    sections = []
    for section in raw.get("sections") or []:
        sections.append({"type": section.get("type"), "number": section.get("sectionNumber"),
                         "classNumber": (section.get("classUniqueId") or {}).get("classNumber"),
                         "instructors": [_instructor(i) for i in section.get("instructors") or [] if _instructor(i)]})
    first = (raw.get("sections") or [{}])[0]
    return {
        "classNumber": raw.get("enrollmentClassNumber"),
        "status": status.get("status"),
        "seats": status.get("availableSeats"),
        "waitlist": status.get("waitlistTotal"),
        "online": bool(raw.get("onlineOnly")),
        "session": first.get("sessionCode"),
        "sections": sections,
        "meetings": meetings,
        "exams": exams,
    }


# ----------------------------------------------------------------------------- store

class EnrollStore:
    """Read-only view over saved term snapshots, plus optional live lookups."""

    def __init__(self, data_dir: Path = DATA_DIR, live: bool | None = None):
        self.data_dir = data_dir
        self.cache_dir = data_dir / "cache"
        self.live = (os.environ.get("BADGERPLAN_OFFLINE") != "1") if live is None else live
        self.terms: dict[str, dict] = {}
        self._offered: dict[str, set[str]] = {}
        self._lock = threading.Lock()
        self._offline_until = 0.0
        self.reload()

    def reload(self) -> None:
        self.terms.clear()
        self._offered.clear()
        if not self.data_dir.exists():
            return
        for path in sorted(self.data_dir.glob("*.json.gz")):
            try:
                with gzip.open(path, "rt", encoding="utf-8") as handle:
                    snapshot = json.load(handle)
            except (OSError, ValueError):
                continue
            code = snapshot.get("term", {}).get("code") or path.name.split(".")[0]
            self.terms[code] = snapshot
            if snapshot.get("offered"):
                keys = set()
                for course in snapshot["offered"]:
                    keys.update(course_keys(course))
                self._offered[code] = keys

    # --- terms and deadlines
    def term_summary(self) -> list[dict]:
        rows = []
        for code, snapshot in sorted(self.terms.items()):
            term = dict(snapshot.get("term") or {"code": code, "name": term_name(code)})
            term["regular_session"] = (snapshot.get("sessions") or {}).get("A1")
            term["offered_courses"] = len(snapshot.get("offered") or [])
            term["sections_saved"] = len(snapshot.get("courses") or {})
            term["fetched_at"] = snapshot.get("fetched_at")
            rows.append(term)
        return rows

    def session(self, term: str, session_code: str) -> dict | None:
        return ((self.terms.get(term) or {}).get("sessions") or {}).get(session_code)

    # --- offerings
    def has_offerings(self, season: str, year: int) -> bool:
        return term_code(season, year) in self._offered

    def offered(self, season: str, year: int, code: str) -> bool | None:
        """True/False when the term's schedule is known, None when it is not."""
        keys = self._offered.get(term_code(season, year))
        if keys is None:
            return None
        return any(key in keys for key in course_keys(code))

    # --- sections
    def packages(self, term: str, code: str) -> dict | None:
        snapshot = self.terms.get(term) or {}
        for key in [code, *course_keys(code)]:
            saved = (snapshot.get("courses") or {}).get(key)
            if saved:
                return {**saved, "source": "snapshot", "fetched_at": snapshot.get("fetched_at")}
        cached = self._read_cache(term, code)
        if cached and time.time() - cached.get("_saved", 0) < CACHE_TTL:
            return {**cached, "source": "cache"}
        if self.live and time.time() >= self._offline_until:
            try:
                fresh = fetch_course(term, code)
            except (OSError, ValueError, urllib.error.URLError):
                # Unreachable network: stop trying for a while instead of
                # making every request wait for a timeout.
                self._offline_until = time.time() + 600
                fresh = None
            if fresh is not None:
                self._write_cache(term, code, fresh)
                return {**fresh, "source": "live"}
        if cached:
            return {**cached, "source": "cache", "stale": True}
        return None

    def _cache_path(self, term: str, code: str) -> Path:
        return self.cache_dir / term / (re.sub(r"[^A-Z0-9]+", "_", code.upper()).strip("_") + ".json")

    def _read_cache(self, term: str, code: str) -> dict | None:
        path = self._cache_path(term, code)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_cache(self, term: str, code: str, data: dict) -> None:
        path = self._cache_path(term, code)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({**data, "_saved": time.time()}), encoding="utf-8")
            except OSError:
                pass


# ----------------------------------------------------------------------------- live API

def _request(url: str, body: dict | None = None, timeout: float = 8) -> object:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "BadgerPlan (student planner; https://github.com/Sherry1247/CourseOptimer)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def search(term: str, query: str = "*", page: int = 1, page_size: int = 50) -> dict:
    return _request(API, {"selectedTerm": term, "queryString": query, "filters": [], "page": page,
                          "pageSize": page_size, "sortOrder": "SCORE" if query != "*" else "SUBJECT"},
                    timeout=40 if page_size > 50 else 8)


def aggregate() -> dict:
    return _request(API + "/aggregate", timeout=30)


def find_course(term: str, code: str) -> dict | None:
    wanted = set(course_keys(code))
    hits = (search(term, code, page_size=10) or {}).get("hits") or []
    for hit in hits:
        designation = " ".join((hit.get("courseDesignation") or "").split())
        if set(course_keys(designation)) & wanted:
            return hit
    return None


def fetch_course(term: str, code: str) -> dict | None:
    hit = find_course(term, code)
    if not hit:
        return {"code": code, "title": None, "credits": None, "packages": [], "offered": False,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    raw = _request(f"{API}/enrollmentPackages/{term}/{hit['subject']['subjectCode']}/{hit['courseId']}")
    return compact_course(code, hit, raw)


def compact_course(code: str, hit: dict, raw_packages: list) -> dict:
    return {
        "code": code,
        "title": hit.get("title"),
        "credits": hit.get("creditRange"),
        "offered": True,
        "packages": [parse_package(p) for p in raw_packages or [] if p.get("published", True)],
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
