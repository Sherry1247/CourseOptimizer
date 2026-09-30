"""SQLite catalog and plan persistence for CourseOptimizer.

The schema keeps provenance and catalog year next to academic rules.  The pilot
seed is intentionally small; the same tables can accept a full UW Guide import.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from planner import Catalog, Course, guide_url


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "courseoptimizer.db"
SEED_PATH = ROOT / "src" / "uw_madison_data.json"


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    authority TEXT NOT NULL CHECK(authority IN ('official', 'derived', 'community')),
    terms_url TEXT,
    accessed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_versions (
    id INTEGER PRIMARY KEY,
    academic_year TEXT NOT NULL UNIQUE,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    status TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    credits_min REAL NOT NULL,
    credits_max REAL NOT NULL,
    requirements_text TEXT NOT NULL DEFAULT '',
    guide_url TEXT NOT NULL,
    catalog_version_id INTEGER NOT NULL REFERENCES catalog_versions(id),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    data_status TEXT NOT NULL DEFAULT 'pilot',
    UNIQUE(code, catalog_version_id)
);

CREATE TABLE IF NOT EXISTS course_offerings (
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    season TEXT NOT NULL CHECK(season IN ('Fall', 'Spring', 'Summer')),
    PRIMARY KEY(course_id, season)
);

CREATE TABLE IF NOT EXISTS prerequisites (
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    prerequisite_code TEXT NOT NULL,
    group_key TEXT NOT NULL DEFAULT 'all',
    concurrent_allowed INTEGER NOT NULL DEFAULT 0,
    evidence_text TEXT,
    PRIMARY KEY(course_id, prerequisite_code, group_key)
);

CREATE TABLE IF NOT EXISTS programs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    degree TEXT NOT NULL,
    school TEXT NOT NULL,
    guide_url TEXT NOT NULL,
    total_degree_credits INTEGER NOT NULL DEFAULT 120,
    catalog_version_id INTEGER NOT NULL REFERENCES catalog_versions(id),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    coverage_status TEXT NOT NULL DEFAULT 'pilot',
    UNIQUE(name, degree, catalog_version_id)
);

CREATE TABLE IF NOT EXISTS requirement_blocks (
    id INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    rule_type TEXT NOT NULL CHECK(rule_type IN ('all_of', 'choose_n', 'min_credits', 'designation')),
    min_courses INTEGER,
    min_credits REAL,
    notes TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    source_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_options (
    block_id INTEGER NOT NULL REFERENCES requirement_blocks(id) ON DELETE CASCADE,
    course_code TEXT NOT NULL,
    option_group TEXT,
    PRIMARY KEY(block_id, course_code)
);

CREATE TABLE IF NOT EXISTS external_signals (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL,
    sample_size INTEGER,
    observed_at TEXT,
    source_url TEXT NOT NULL,
    UNIQUE(course_id, provider, metric, observed_at)
);

CREATE TABLE IF NOT EXISTS saved_plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    student_type TEXT NOT NULL,
    graduation_year INTEGER NOT NULL,
    primary_major TEXT NOT NULL,
    second_major TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_items (
    plan_id TEXT NOT NULL REFERENCES saved_plans(id) ON DELETE CASCADE,
    term_label TEXT NOT NULL,
    position INTEGER NOT NULL,
    course_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    PRIMARY KEY(plan_id, term_label, course_code)
);

CREATE INDEX IF NOT EXISTS idx_courses_code ON courses(code);
CREATE INDEX IF NOT EXISTS idx_programs_name ON programs(name);
CREATE INDEX IF NOT EXISTS idx_plan_items_plan ON plan_items(plan_id);
"""


PROGRAM_GUIDES = {
    "Computer Sciences": (
        "BS",
        "College of Letters & Science",
        "https://guide.wisc.edu/undergraduate/letters-science/computer-sciences/computer-sciences-bs/",
    ),
    "Data Science": (
        "BS",
        "College of Letters & Science",
        "https://guide.wisc.edu/undergraduate/letters-science/statistics/data-science-bs/",
    ),
    "Economics": (
        "BS",
        "College of Letters & Science",
        "https://guide.wisc.edu/undergraduate/letters-science/economics/economics-bs/",
    ),
    "Mathematics": (
        "BS",
        "College of Letters & Science",
        "https://guide.wisc.edu/undergraduate/letters-science/mathematics/mathematics-bs/",
    ),
}


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(db_path)) as connection, connection:
        connection.executescript(SCHEMA)
        existing = connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        if existing == 0:
            _seed_pilot(connection)
    return db_path


def _seed_pilot(connection: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))

    official_id = connection.execute(
        "INSERT INTO sources(name, url, authority, accessed_at) VALUES (?, ?, ?, ?)",
        ("UW–Madison Guide", "https://guide.wisc.edu/", "official", now),
    ).lastrowid
    connection.execute(
        "INSERT INTO sources(name, url, authority, terms_url, accessed_at) VALUES (?, ?, ?, ?, ?)",
        (
            "UW Courses open dataset",
            "https://huggingface.co/datasets/twangodev/uwcourses",
            "derived",
            "https://github.com/twangodev/uwcourses/blob/main/LICENSE",
            now,
        ),
    )
    connection.execute(
        "INSERT INTO sources(name, url, authority, accessed_at) VALUES (?, ?, ?, ?)",
        ("Madgrades API", "https://api.madgrades.com/", "community", now),
    )
    catalog_id = connection.execute(
        "INSERT INTO catalog_versions(academic_year, source_id, status, imported_at) VALUES (?, ?, ?, ?)",
        (raw["metadata"].get("academic_year", "2024-2025"), official_id, "pilot", now),
    ).lastrowid

    course_ids: dict[str, int] = {}
    for item in raw["courses"]:
        code = " ".join(item["full_code"].upper().split())
        course_id = connection.execute(
            """
            INSERT INTO courses(
                code, title, description, credits_min, credits_max,
                requirements_text, guide_url, catalog_version_id, source_id, data_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                item["name"],
                item.get("description", ""),
                item["credits"],
                item["credits"],
                ", ".join(item.get("prerequisites", [])),
                guide_url(code),
                catalog_id,
                official_id,
                "pilot-needs-verification",
            ),
        ).lastrowid
        course_ids[code] = course_id
        for season in item.get("semesters", ["Fall", "Spring"]):
            connection.execute(
                "INSERT INTO course_offerings(course_id, season) VALUES (?, ?)",
                (course_id, season),
            )
        for metric, key in (("average_gpa", "avg_gpa"), ("a_rate", "grade_a_rate")):
            if item.get(key) is not None:
                connection.execute(
                    """
                    INSERT INTO external_signals(
                        course_id, provider, metric, value, observed_at, source_url
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        course_id,
                        "hackathon_demo",
                        metric,
                        item[key],
                        raw["metadata"].get("last_updated"),
                        "https://api.madgrades.com/",
                    ),
                )

    for item in raw["courses"]:
        code = " ".join(item["full_code"].upper().split())
        for prerequisite in item.get("prerequisites", []):
            connection.execute(
                """
                INSERT INTO prerequisites(
                    course_id, prerequisite_code, evidence_text
                ) VALUES (?, ?, ?)
                """,
                (course_ids[code], prerequisite, f"Pilot structured requisite for {code}"),
            )

    for name, major in raw["majors"].items():
        degree, school, source_url = PROGRAM_GUIDES.get(
            name,
            ("BA/BS", "University of Wisconsin–Madison", "https://guide.wisc.edu/undergraduate/"),
        )
        program_id = connection.execute(
            """
            INSERT INTO programs(
                name, degree, school, guide_url, total_degree_credits,
                catalog_version_id, source_id, coverage_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                degree,
                school,
                source_url,
                major.get("total_credits", 120),
                catalog_id,
                official_id,
                "pilot-core-only",
            ),
        ).lastrowid
        block_id = connection.execute(
            """
            INSERT INTO requirement_blocks(
                program_id, name, rule_type, min_courses, notes, sort_order, source_url
            ) VALUES (?, ?, 'all_of', ?, ?, 1, ?)
            """,
            (
                program_id,
                "Core courses (pilot coverage)",
                len(major.get("required_courses", [])),
                major.get("notes", ""),
                source_url,
            ),
        ).lastrowid
        for course_code in major.get("required_courses", []):
            connection.execute(
                "INSERT INTO requirement_options(block_id, course_code) VALUES (?, ?)",
                (block_id, course_code),
            )


def load_catalog(db_path: str | Path = DEFAULT_DB_PATH) -> Catalog:
    initialize_database(db_path)
    with closing(connect(db_path)) as connection:
        course_rows = connection.execute(
            """
            SELECT c.*, GROUP_CONCAT(o.season) AS seasons
            FROM courses c
            LEFT JOIN course_offerings o ON o.course_id = c.id
            GROUP BY c.id
            ORDER BY c.code
            """
        ).fetchall()
        prerequisite_rows = connection.execute(
            "SELECT c.code, p.prerequisite_code FROM prerequisites p JOIN courses c ON c.id = p.course_id"
        ).fetchall()
        prereqs: dict[str, list[str]] = {}
        for row in prerequisite_rows:
            prereqs.setdefault(row["code"], []).append(row["prerequisite_code"])

        signal_rows = connection.execute(
            "SELECT c.code, s.metric, s.value FROM external_signals s JOIN courses c ON c.id = s.course_id"
        ).fetchall()
        signals: dict[str, dict[str, float]] = {}
        for row in signal_rows:
            signals.setdefault(row["code"], {})[row["metric"]] = row["value"]

        courses = {
            row["code"]: Course(
                code=row["code"],
                name=row["title"],
                credits=int(row["credits_max"]),
                prerequisites=tuple(prereqs.get(row["code"], [])),
                semesters=tuple(row["seasons"].split(",")) if row["seasons"] else (),
                description=row["description"],
                avg_gpa=signals.get(row["code"], {}).get("average_gpa"),
                grade_a_rate=signals.get(row["code"], {}).get("a_rate"),
            )
            for row in course_rows
        }

        program_rows = connection.execute(
            """
            SELECT p.name, p.degree, p.school, p.guide_url, p.coverage_status,
                   ro.course_code, cv.academic_year
            FROM programs p
            JOIN catalog_versions cv ON cv.id = p.catalog_version_id
            LEFT JOIN requirement_blocks rb ON rb.program_id = p.id AND rb.rule_type = 'all_of'
            LEFT JOIN requirement_options ro ON ro.block_id = rb.id
            ORDER BY p.name, ro.course_code
            """
        ).fetchall()
        majors: dict[str, dict] = {}
        for row in program_rows:
            major = majors.setdefault(
                row["name"],
                {
                    "required_courses": [],
                    "degree": row["degree"],
                    "school": row["school"],
                    "guide_url": row["guide_url"],
                    "coverage_status": row["coverage_status"],
                    "academic_year": row["academic_year"],
                },
            )
            if row["course_code"]:
                major["required_courses"].append(row["course_code"])

        version = connection.execute(
            "SELECT academic_year, status, imported_at FROM catalog_versions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return Catalog(
            courses=courses,
            majors=majors,
            metadata=dict(version),
            double_major_rules={"overlap_allowed": True, "max_overlap_credits": 15},
        )


def catalog_payload(db_path: str | Path = DEFAULT_DB_PATH) -> dict:
    catalog = load_catalog(db_path)
    return {
        "metadata": catalog.metadata,
        "programs": [
            {"name": name, **{key: value for key, value in details.items() if key != "required_courses"}}
            for name, details in catalog.majors.items()
        ],
        "courses": [
            {
                "code": course.code,
                "title": course.name,
                "credits": course.credits,
                "description": course.description,
                "prerequisites": list(course.prerequisites),
                "semesters": list(course.semesters),
                "avgGpa": course.avg_gpa,
                "aRate": course.grade_a_rate,
                "guideUrl": guide_url(course.code),
                "madgradesUrl": f"https://madgrades.com/search?q={course.code.replace(' ', '+')}",
            }
            for course in catalog.courses.values()
        ],
    }


def save_plan(payload: dict, db_path: str | Path = DEFAULT_DB_PATH) -> str:
    initialize_database(db_path)
    plan_id = payload.get("id") or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with closing(connect(db_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO saved_plans(
                id, name, student_type, graduation_year, primary_major,
                second_major, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, student_type=excluded.student_type,
                graduation_year=excluded.graduation_year,
                primary_major=excluded.primary_major, second_major=excluded.second_major,
                updated_at=excluded.updated_at
            """,
            (
                plan_id,
                payload.get("name", "My UW Plan"),
                payload.get("studentType", "first-year"),
                int(payload["graduationYear"]),
                payload["primaryMajor"],
                payload.get("secondMajor") or None,
                now,
                now,
            ),
        )
        connection.execute("DELETE FROM plan_items WHERE plan_id = ?", (plan_id,))
        for term in payload.get("terms", []):
            for position, course_code in enumerate(term.get("courses", [])):
                connection.execute(
                    """
                    INSERT INTO plan_items(plan_id, term_label, position, course_code)
                    VALUES (?, ?, ?, ?)
                    """,
                    (plan_id, term["label"], position, course_code),
                )
    return plan_id
