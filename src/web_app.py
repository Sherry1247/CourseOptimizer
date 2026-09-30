"""Professional local web app for CourseOptimizer."""

from __future__ import annotations

import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from catalog_db import catalog_payload, initialize_database, load_catalog, save_plan
from planner import generate_plan


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "web" / "static"
initialize_database()


async def homepage(_: Request) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "courseoptimizer"})


async def get_catalog(_: Request) -> JSONResponse:
    return JSONResponse(catalog_payload())


async def create_plan(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
        majors = [payload["primaryMajor"]]
        if payload.get("secondMajor"):
            majors.append(payload["secondMajor"])
        start_year = int(payload["startYear"])
        graduation_year = int(payload["graduationYear"])
        years = max(1, min(8, graduation_year - start_year))
        result = generate_plan(
            load_catalog(),
            majors,
            payload.get("completedCourses", []),
            start_term=payload.get("startTerm", "Fall"),
            start_year=start_year,
            years=years,
            max_credits_per_term=int(payload.get("maxCredits", 15)),
            priority=payload.get("priority", "balanced"),
        )
        response = {
            "terms": [
                {
                    "label": term.label,
                    "term": term.term,
                    "credits": term.credits,
                    "courses": [course.code for course in term.courses],
                }
                for term in result.terms
            ],
            "requiredCourses": sorted(result.required_courses),
            "supportingCourses": sorted(result.supporting_courses),
            "overlapCourses": sorted(result.overlap_courses),
            "unscheduledCourses": sorted(result.unscheduled_courses),
            "missingCatalogCourses": sorted(result.missing_catalog_courses),
            "warnings": list(result.warnings),
            "catalogCoverage": "pilot-core-only",
        }
        return JSONResponse(response)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return JSONResponse({"error": str(error)}, status_code=400)


async def persist_plan(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
        plan_id = save_plan(payload)
        return JSONResponse({"id": plan_id, "saved": True})
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return JSONResponse({"error": str(error)}, status_code=400)


routes = [
    Route("/", homepage),
    Route("/api/health", health),
    Route("/api/catalog", get_catalog),
    Route("/api/plans/generate", create_plan, methods=["POST"]),
    Route("/api/plans", persist_plan, methods=["POST"]),
]

app = Starlette(debug=False, routes=routes)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

