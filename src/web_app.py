"""BadgerPlan web server (Starlette).

    python -m uvicorn web_app:app --app-dir src --port 8501

Everything the browser needs is served from the local SQLite catalog; no
third-party API keys are required at runtime.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path
import threading
import base64
import binascii
from io import BytesIO

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

import catalog_db as db
from analysis import compare_programs, rank_second_majors
from degree_rules import PROFILES, degree_rules, gened_rules
from ingest.designations import TAG_LABELS
from planner import PlanRequest, generate_plan, validate_plan
from transcript import parse_transcript

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "web" / "static"


class CatalogState:
    """In-memory catalog loaded once from SQLite (read-only at runtime)."""

    def __init__(self, db_path: Path = db.DEFAULT_DB_PATH):
        db.initialize_database(db_path)
        self.connection = db.connect(db_path)
        self.lock = threading.Lock()
        self.courses = db.load_courses(self.connection)
        self.aliases = db.load_aliases(self.connection)
        self.program_index = db.list_programs(self.connection)
        self._programs: dict[str, dict] = {}
        self.meta = db.meta(db_path)

    def program(self, program_id: str) -> dict:
        if program_id not in self._programs:
            with self.lock:
                loaded = db.load_program(self.connection, program_id)
            if not loaded:
                raise KeyError(f"Unknown program: {program_id}")
            self._programs[program_id] = loaded
        return self._programs[program_id]

    def all_programs(self) -> list[dict]:
        return [self.program(p["id"]) for p in self.program_index]

    def credits_of(self, code: str) -> float:
        info = self.courses.get(code)
        return float(info["credits"][0] or 3) if info else 3.0


STATE: CatalogState | None = None


def state() -> CatalogState:
    global STATE
    if STATE is None:
        STATE = CatalogState()
    return STATE


def error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def discovery_course(row: dict) -> dict:
    credit_label = str(row["credits_min"])
    if row["credits_min"] != row["credits_max"]:
        credit_label = f'{row["credits_min"]}-{row["credits_max"]}'
    grade_label = f' · historical GPA {row["avg_gpa"]:.2f}' if row.get("avg_gpa") else ""
    return {
        "id": row["code"],
        "title": f'{row["code"]} — {row["title"]}',
        "meta": f"{credit_label} credits{grade_label}",
        "href": f'/courses/{row["code"]}',
    }


# ----------------------------------------------------------------------------- routes

async def homepage(_: Request) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


async def tokens(_: Request) -> FileResponse:
    return FileResponse(ROOT / "tokens.css", media_type="text/css")


async def health(_: Request) -> JSONResponse:
    s = state()
    return JSONResponse({"status": "ok", "courses": len(s.courses), "programs": len(s.program_index)})


async def meta(_: Request) -> JSONResponse:
    s = state()
    return JSONResponse({
        **{k: v for k, v in s.meta.items() if k in {"catalog_year", "built_at", "stats", "sources"}},
        "tags": TAG_LABELS,
        "profiles": {key: title for key, (title, _) in PROFILES.items()},
    })


async def programs(_: Request) -> JSONResponse:
    return JSONResponse(state().program_index)


async def universal_search(request: Request) -> JSONResponse:
    q = request.query_params.get("q", "").strip()
    if len(q) < 2:
        return JSONResponse({"courses": [], "professors": [], "majors": [], "groups": []})
    s = state()
    with s.lock:
        courses = db.search_courses(s.connection, q, limit=6)
        professors = db.search_instructors(s.connection, q, limit=6)
    needle = q.lower()
    majors = [p for p in s.program_index if needle in f"{p['name']} {p.get('college', '')} {p.get('department', '')}".lower()][:6]
    groups = [
        {"type": "course", "label": "Courses", "results": [
            discovery_course(row) for row in courses]},
        {"type": "professor", "label": "Professors", "results": [
            {"id": row["id"], "title": row["display_name"],
             "meta": f'{row.get("department") or "UW–Madison"} · {row["course_count"]} courses',
             "href": f'/professors/{row["id"]}'} for row in professors]},
        {"type": "major", "label": "Majors", "results": [
            {"id": row["id"], "title": row["name"], "meta": row.get("college", ""),
             "href": f'/majors/{row["id"]}'} for row in majors]},
    ]
    return JSONResponse({"courses": courses, "professors": professors, "majors": majors, "groups": groups})


async def transcript_parse(request: Request) -> JSONResponse:
    """Extract transcript text and conservatively match it to local courses."""
    try:
        payload = await request.json()
        text = payload.get("text", "")
        file_data = payload.get("file_data")
        filename = str(payload.get("filename", ""))
        if file_data:
            if not filename.lower().endswith(".pdf"):
                return error("Only PDF binary uploads are accepted. Text, CSV, and JSON files are read in your browser.")
            try:
                raw = base64.b64decode(file_data, validate=True)
            except (ValueError, binascii.Error):
                return error("The uploaded PDF could not be read.")
            if len(raw) > 12 * 1024 * 1024:
                return error("Transcript PDF is larger than the 12 MB limit.")
            try:
                from pypdf import PdfReader
            except ImportError:
                return error("PDF transcript support is not installed. Paste transcript text or upload TXT/CSV for now.", 503)
            try:
                reader = PdfReader(BytesIO(raw))
                if reader.is_encrypted:
                    return error("Password-protected transcripts are not supported. Export an unlocked copy or paste the text.")
                text = "\n".join((page.extract_text() or "") for page in reader.pages[:80])
            except Exception:
                return error("The PDF could not be parsed. If it is a scan, copy/paste its text instead.")
            if not text.strip():
                return error("No selectable text was found in this PDF. Scanned transcripts need OCR before import.")
        s = state()
        result = parse_transcript(text, s.courses, s.aliases)
        return JSONResponse(result)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return error(str(exc))


async def program_detail(request: Request) -> JSONResponse:
    try:
        program = state().program(request.path_params["program_id"])
    except KeyError as exc:
        return error(str(exc), 404)
    rules = degree_rules(program["profile"])
    return JSONResponse({**program, "degree_rules": rules})


async def course_search(request: Request) -> JSONResponse:
    q = request.query_params.get("q", "")
    tag = request.query_params.get("tag") or None
    limit = min(int(request.query_params.get("limit", 30)), 100)
    def number(name):
        value = request.query_params.get(name)
        return float(value) if value not in (None, "") else None
    tags = request.query_params.getlist("tag") or ([tag] if tag else [])
    filters = {
        "department": request.query_params.get("department") or None,
        "credits": number("credits"),
        "level_min": number("level_min"),
        "level_max": number("level_max"),
        "tags": tags,
        "requisites": request.query_params.get("requisites") or None,
        "prerequisite_count_min": number("prerequisite_count_min"),
        "prerequisite_count_max": number("prerequisite_count_max"),
        "gpa_min": number("gpa_min"),
        "gpa_max": number("gpa_max"),
        "grade_count_min": number("grade_count_min"),
        "instructor": request.query_params.get("instructor") or None,
        "season": request.query_params.get("season") or None,
        "frequency": request.query_params.get("frequency") or None,
        "sort": request.query_params.get("sort") or None,
        "program_ids": request.query_params.getlist("program"),
    }
    s = state()
    with s.lock:
        rows = db.search_courses(s.connection, q, limit=limit, tag=tag, filters=filters)
    return JSONResponse(rows)


async def easiest_course_search(request: Request) -> JSONResponse:
    q = request.query_params.get("q", "")
    def number(name):
        value = request.query_params.get(name)
        return float(value) if value not in (None, "") else None
    filters = {
        "department": request.query_params.get("department") or None,
        "credits": number("credits"),
        "level_min": number("level_min") if request.query_params.get("level_min") else 100,
        "level_max": number("level_max") if request.query_params.get("level_max") else 699,
        "tags": request.query_params.getlist("tag"),
        "requisites": request.query_params.get("requisites") or None,
        "prerequisite_count_min": number("prerequisite_count_min"),
        "prerequisite_count_max": number("prerequisite_count_max"),
        "gpa_min": number("gpa_min"),
        "season": request.query_params.get("season") or None,
        "frequency": request.query_params.get("frequency") or None,
        "program_ids": request.query_params.getlist("program"),
    }
    s = state()
    with s.lock:
        rows = db.easiest_courses(s.connection, query=q, limit=min(int(request.query_params.get("limit", 60)), 100), filters=filters)
    return JSONResponse(rows)


async def departments(_: Request) -> JSONResponse:
    s = state()
    with s.lock:
        rows = db.list_departments(s.connection)
    return JSONResponse(rows)


async def instructors(request: Request) -> JSONResponse:
    s = state()
    with s.lock:
        rows = db.search_instructors(s.connection, request.query_params.get("q", ""), min(int(request.query_params.get("limit", 30)), 100))
    return JSONResponse(rows)


async def instructor(request: Request) -> JSONResponse:
    s = state()
    with s.lock:
        detail = db.instructor_detail(s.connection, request.path_params["instructor_id"])
    return JSONResponse(detail) if detail else error("Instructor not found", 404)


async def course_detail(request: Request) -> JSONResponse:
    s = state()
    code = request.path_params["code"].replace("_", " ").replace("+", " ")
    with s.lock:
        detail = db.course_detail(s.connection, code)
    if not detail:
        return error(f"Course {code} not found", 404)
    return JSONResponse(detail)


async def gened_preview(request: Request) -> JSONResponse:
    season = request.query_params.get("season", "Fall")
    year = int(request.query_params.get("year", 2026))
    return JSONResponse(gened_rules(season, year))


_SECOND_MAJOR_CACHE: dict[str, list] = {}


async def second_majors(request: Request) -> JSONResponse:
    s = state()
    program_id = request.path_params["program_id"]
    try:
        primary = s.program(program_id)
    except KeyError as exc:
        return error(str(exc), 404)
    if program_id not in _SECOND_MAJOR_CACHE:
        _SECOND_MAJOR_CACHE[program_id] = rank_second_majors(primary, s.all_programs(), s.credits_of)
    return JSONResponse(_SECOND_MAJOR_CACHE[program_id])


async def compare_majors(request: Request) -> JSONResponse:
    s = state()
    try:
        primary = s.program(request.path_params["program_id"])
        secondary = s.program(request.path_params["second_id"])
    except KeyError as exc:
        return error(str(exc), 404)
    return JSONResponse(compare_programs(primary, secondary, s.credits_of))


async def _request_and_programs(payload: dict):
    s = state()
    request = PlanRequest.from_payload(payload)
    loaded = [s.program(pid) for pid in request.program_ids]
    return s, request, loaded


async def plan_generate(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
        s, plan_request, loaded = await _request_and_programs(payload)
        result = generate_plan(s.courses, loaded, plan_request, s.aliases)
        return JSONResponse(result)
    except KeyError as exc:
        return error(str(exc), 404)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return error(str(exc))


async def plan_validate(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
        s, plan_request, loaded = await _request_and_programs(payload)
        result = validate_plan(s.courses, loaded, plan_request, payload.get("plan") or {}, s.aliases)
        return JSONResponse(result)
    except KeyError as exc:
        return error(str(exc), 404)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return error(str(exc))


async def plans_list(_: Request) -> JSONResponse:
    s = state()
    with s.lock:
        return JSONResponse(db.list_plans(s.connection))


async def plans_create(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return error("Invalid JSON")
    if not isinstance(payload, dict) or not payload.get("settings"):
        return error("A plan needs settings and terms")
    s = state()
    with s.lock:
        plan_id = db.save_plan(s.connection, payload)
    return JSONResponse({"id": plan_id, "saved": True})


async def plans_item(request: Request) -> JSONResponse:
    s = state()
    plan_id = request.path_params["plan_id"]
    if request.method == "DELETE":
        with s.lock:
            ok = db.delete_plan(s.connection, plan_id)
        return JSONResponse({"deleted": ok}, status_code=200 if ok else 404)
    with s.lock:
        plan = db.get_plan(s.connection, plan_id)
    return JSONResponse(plan) if plan else error("Plan not found", 404)


@asynccontextmanager
async def lifespan(_app):
    state()  # load catalog at startup
    yield


routes = [
    Route("/", homepage),
    Route("/tokens.css", tokens),
    Route("/api/health", health),
    Route("/api/meta", meta),
    Route("/api/search", universal_search),
    Route("/api/transcript/parse", transcript_parse, methods=["POST"]),
    Route("/api/departments", departments),
    Route("/api/instructors", instructors),
    Route("/api/instructors/{instructor_id:path}", instructor),
    Route("/api/programs", programs),
    Route("/api/programs/{program_id}", program_detail),
    Route("/api/programs/{program_id}/second-majors", second_majors),
    Route("/api/programs/{program_id}/compare/{second_id}", compare_majors),
    Route("/api/courses", course_search),
    Route("/api/discovery/easiest", easiest_course_search),
    Route("/api/courses/{code:path}", course_detail),
    Route("/api/gened", gened_preview),
    Route("/api/plan/generate", plan_generate, methods=["POST"]),
    Route("/api/plan/validate", plan_validate, methods=["POST"]),
    Route("/api/plans", plans_list, methods=["GET"]),
    Route("/api/plans", plans_create, methods=["POST"]),
    Route("/api/plans/{plan_id}", plans_item, methods=["GET", "DELETE"]),
    Mount("/static", StaticFiles(directory=STATIC_DIR), name="static"),
    Route("/{path:path}", homepage),
]

app = Starlette(debug=False, routes=routes, lifespan=lifespan)
