"""SQLite catalog for BadgerPlan.

The database is generated from the committed snapshot
(``data/snapshot/badgerplan-2026-27.json.gz``) by ``scripts/init_db.py``.  It
stores the UW catalog in normalized tables so it can be queried directly
(e.g. "which majors require COMP SCI 400?", "what does MATH 222 unlock?") and
is the only data source the web app reads at runtime.

Tables
    meta                  key/value build info
    sources               provenance of every dataset
    courses               one row per course (canonical cross-listed code)
    course_aliases        every spelling -> canonical code
    course_tags           designation tags (comm_a, ethnic, level_i, ge_ha ...)
    course_prereqs        flattened prerequisite edges (for graph queries)
    grade_distributions   Madgrades distributions (cumulative + recent terms)
    instructors           instructor directory + RMP aggregates
    course_instructors    who taught what, how often, most recently
    programs              majors / named options with degree + college
    requirement_blocks    one requirement inside a program
    requirement_slots     slot inside a block (one course or an OR-group)
    requirement_options   AND-bundles of courses inside a slot
    saved_plans           student plans (JSON payload)
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "badgerplan.db"
DEFAULT_SNAPSHOT = ROOT / "data" / "snapshot" / "badgerplan-2026-27.json.gz"
SCHEMA_VERSION = "2"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    authority TEXT NOT NULL,
    license TEXT,
    use TEXT
);

CREATE TABLE IF NOT EXISTS courses (
    code TEXT PRIMARY KEY,
    subjects TEXT NOT NULL,              -- JSON list
    number TEXT NOT NULL,
    title TEXT NOT NULL,
    credits_min REAL NOT NULL,
    credits_max REAL NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    requisite_text TEXT NOT NULL DEFAULT '',
    requisite_tree TEXT,                 -- JSON (see requisites.py)
    exclusions TEXT NOT NULL DEFAULT '[]',
    concurrent INTEGER NOT NULL DEFAULT 0,
    breadth_choice TEXT NOT NULL DEFAULT '[]',
    language_level INTEGER,
    repeatable TEXT,
    last_taught TEXT,
    offered_seasons TEXT NOT NULL DEFAULT '[]',
    offering_confidence TEXT NOT NULL DEFAULT 'unknown',
    offering_frequency TEXT NOT NULL DEFAULT 'unknown',
    offering_counts TEXT NOT NULL DEFAULT '{}',
    avg_gpa REAL,
    grade_count INTEGER,
    keywords TEXT NOT NULL DEFAULT '[]',
    guide_url TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_courses_number ON courses(number);

CREATE TABLE IF NOT EXISTS course_aliases (
    alias TEXT PRIMARY KEY,
    code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS course_tags (
    code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (code, tag)
);
CREATE INDEX IF NOT EXISTS idx_course_tags_tag ON course_tags(tag);

CREATE TABLE IF NOT EXISTS course_prereqs (
    code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
    prereq_code TEXT NOT NULL,
    PRIMARY KEY (code, prereq_code)
);
CREATE INDEX IF NOT EXISTS idx_course_prereqs_prereq ON course_prereqs(prereq_code);

CREATE TABLE IF NOT EXISTS grade_distributions (
    code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
    term TEXT NOT NULL,                  -- UW term code or 'cumulative'
    label TEXT NOT NULL,
    a INTEGER, ab INTEGER, b INTEGER, bc INTEGER, c INTEGER, d INTEGER, f INTEGER,
    other INTEGER, total INTEGER, gpa REAL,
    instructors TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (code, term)
);

CREATE TABLE IF NOT EXISTS instructors (
    name TEXT PRIMARY KEY,               -- upper-case key as used by Madgrades
    display_name TEXT NOT NULL,
    department TEXT,
    position TEXT,
    rmp_rating REAL,
    rmp_difficulty REAL,
    rmp_count INTEGER,
    rmp_would_take_again REAL,
    rmp_id INTEGER,
    avg_gpa REAL
);

CREATE TABLE IF NOT EXISTS course_instructors (
    code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
    instructor TEXT NOT NULL,
    terms INTEGER NOT NULL,
    last_term TEXT NOT NULL,
    rank INTEGER NOT NULL,
    PRIMARY KEY (code, instructor)
);

CREATE TABLE IF NOT EXISTS programs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    degree TEXT NOT NULL,
    college TEXT NOT NULL,
    department TEXT,
    profile TEXT NOT NULL,               -- school/college rule profile (degree_rules.py)
    parent_id TEXT,
    has_named_options INTEGER NOT NULL DEFAULT 0,
    confidence TEXT NOT NULL,
    guide_url TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '[]',
    sample_plan TEXT NOT NULL DEFAULT '[]',
    variants TEXT NOT NULL DEFAULT '[]',
    catalog_year TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_blocks (
    id INTEGER PRIMARY KEY,
    program_id TEXT NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    block_key TEXT NOT NULL,
    section TEXT NOT NULL,               -- major | college
    name TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '[]',
    rule TEXT NOT NULL,                  -- all | choose | credits | pattern | text | recommended
    min_count INTEGER,
    min_credits REAL,
    pattern TEXT,                        -- JSON for rule = pattern
    variant_group TEXT,
    variant TEXT,
    confidence TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_blocks_program ON requirement_blocks(program_id);

CREATE TABLE IF NOT EXISTS requirement_slots (
    id INTEGER PRIMARY KEY,
    block_id INTEGER NOT NULL REFERENCES requirement_blocks(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    label TEXT NOT NULL,
    credits_min REAL,
    credits_max REAL
);
CREATE INDEX IF NOT EXISTS idx_slots_block ON requirement_slots(block_id);

CREATE TABLE IF NOT EXISTS requirement_options (
    slot_id INTEGER NOT NULL REFERENCES requirement_slots(id) ON DELETE CASCADE,
    option_index INTEGER NOT NULL,
    course_code TEXT NOT NULL,
    PRIMARY KEY (slot_id, option_index, course_code)
);
CREATE INDEX IF NOT EXISTS idx_options_course ON requirement_options(course_code);

CREATE TABLE IF NOT EXISTS saved_plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(db_path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def is_initialized(db_path: str | Path = DEFAULT_DB_PATH) -> bool:
    path = Path(db_path)
    if not path.exists():
        return False
    try:
        with closing(connect(path)) as connection:
            row = connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            return bool(row) and row[0] == SCHEMA_VERSION
    except sqlite3.DatabaseError:
        return False


def load_snapshot(path: str | Path = DEFAULT_SNAPSHOT) -> dict:
    with gzip.open(Path(path), "rt", encoding="utf-8") as handle:
        return json.load(handle)


def initialize_database(
    db_path: str | Path = DEFAULT_DB_PATH,
    snapshot_path: str | Path = DEFAULT_SNAPSHOT,
    *,
    force: bool = False,
) -> Path:
    """Create the database from the snapshot (idempotent unless ``force``)."""

    db_path = Path(db_path)
    if not force and is_initialized(db_path):
        return db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = load_snapshot(snapshot_path)
    saved: list[tuple] = []
    if db_path.exists():
        try:
            with closing(connect(db_path)) as old:
                saved = old.execute("SELECT id, name, payload, created_at, updated_at FROM saved_plans").fetchall()
        except sqlite3.DatabaseError:
            saved = []
        db_path.unlink()
    with closing(connect(db_path)) as connection, connection:
        connection.executescript(SCHEMA)
        _load(connection, snapshot)
        connection.executemany(
            "INSERT OR REPLACE INTO saved_plans(id, name, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            [tuple(row) for row in saved],
        )
    return db_path


def _j(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(connection: sqlite3.Connection, snapshot: dict) -> None:
    meta = snapshot["meta"]
    connection.executemany(
        "INSERT INTO meta(key, value) VALUES (?, ?)",
        [
            ("schema_version", SCHEMA_VERSION),
            ("catalog_year", meta["catalog_year"]),
            ("built_at", meta["built_at"]),
            ("loaded_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
            ("stats", _j(meta.get("stats", {}))),
        ],
    )
    connection.executemany(
        "INSERT INTO sources(name, url, authority, license, use) VALUES (?, ?, ?, ?, ?)",
        [(s["name"], s["url"], s["authority"], s.get("license"), s.get("use")) for s in meta["sources"]],
    )

    course_rows, tag_rows, prereq_rows, grade_rows, ci_rows = [], [], [], [], []
    for course in snapshot["courses"]:
        grades = course.get("grades") or {}
        cumulative = grades.get("cumulative") or {}
        offering = course.get("offering") or {}
        course_rows.append((
            course["code"], _j(course["subjects"]), course["number"], course["title"],
            course["credits"][0], course["credits"][1], course["description"],
            course["requisite_text"], _j(course["requisites"]) if course["requisites"] else None,
            _j(course["exclusions"]), int(bool(course["concurrent"])), _j(course["breadth_choice"]),
            course["language_level"], course["repeatable"], course["last_taught"],
            _j(offering.get("seasons", [])), offering.get("confidence", "unknown"),
            offering.get("frequency", "unknown"), _j(offering.get("counts", {})),
            cumulative.get("gpa"), cumulative.get("total"), _j(course.get("keywords", [])), course["guide_url"],
        ))
        tag_rows.extend((course["code"], tag) for tag in course["tags"])
        prereq_rows.extend((course["code"], code) for code in course.get("prereq_codes", []))
        if cumulative:
            grade_rows.append((course["code"], "cumulative", "All terms", *(cumulative.get(k) for k in ("a", "ab", "b", "bc", "c", "d", "f", "other", "total", "gpa")), "[]"))
        for term in grades.get("terms") or []:
            grade_rows.append((course["code"], term["term"], term["label"], *(term.get(k) for k in ("a", "ab", "b", "bc", "c", "d", "f", "other", "total", "gpa")), _j(term.get("instructors", []))))
        for rank, row in enumerate(course.get("instructors") or []):
            ci_rows.append((course["code"], row["name"], row.get("terms", 1), row["last_term"], rank))

    connection.executemany(f"INSERT INTO courses VALUES ({','.join('?' * 23)})", course_rows)
    connection.executemany("INSERT OR IGNORE INTO course_tags VALUES (?, ?)", tag_rows)
    connection.executemany("INSERT OR IGNORE INTO course_prereqs VALUES (?, ?)", prereq_rows)
    connection.executemany(f"INSERT OR REPLACE INTO grade_distributions VALUES ({','.join('?' * 14)})", grade_rows)
    known = {row[0] for row in course_rows}
    connection.executemany(
        "INSERT OR IGNORE INTO course_aliases VALUES (?, ?)",
        [(alias, code) for alias, code in snapshot["aliases"].items() if code in known],
    )
    connection.executemany(
        "INSERT INTO instructors VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (key, info["name"], info.get("department"), info.get("position"),
             *( (info.get("rmp") or {}).get(k) for k in ("rating", "difficulty", "count", "would_take_again", "id")),
             (info.get("cumulative") or {}).get("gpa"))
            for key, info in snapshot["instructors"].items()
        ],
    )
    connection.executemany("INSERT OR IGNORE INTO course_instructors VALUES (?, ?, ?, ?, ?)", ci_rows)

    catalog_year = meta["catalog_year"]
    for program in snapshot["programs"]:
        connection.execute(
            "INSERT INTO programs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (program["id"], program["name"], program["degree"], program["college"], program["department"],
             program["profile"], program.get("parent_id"), int(program.get("has_named_options", False)),
             program["confidence"], program["url"], _j(program.get("notes", [])[:6]),
             _j(program.get("sample_plan", [])), _j(program.get("variants", [])), catalog_year),
        )
        for position, block in enumerate(program["blocks"]):
            pattern = None
            notes = []
            for note in block.get("notes", []):
                if note.startswith("PATTERN:"):
                    pattern = note[len("PATTERN:"):]
                else:
                    notes.append(note)
            block_id = connection.execute(
                """INSERT INTO requirement_blocks(program_id, position, block_key, section, name, path, rule,
                       min_count, min_credits, pattern, variant_group, variant, confidence, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (program["id"], position, block["key"], block["section"], block["name"], _j(block["path"]),
                 block["rule"], block.get("count"), block.get("credits"), pattern, block.get("variant_group"),
                 block.get("variant"), block["confidence"], _j(notes)),
            ).lastrowid
            for slot_position, slot in enumerate(block["slots"]):
                credits = slot.get("credits") or [None, None]
                slot_id = connection.execute(
                    "INSERT INTO requirement_slots(block_id, position, label, credits_min, credits_max) VALUES (?, ?, ?, ?, ?)",
                    (block_id, slot_position, slot["label"][:200], credits[0], credits[1]),
                ).lastrowid
                connection.executemany(
                    "INSERT OR IGNORE INTO requirement_options VALUES (?, ?, ?)",
                    [(slot_id, index, code) for index, bundle in enumerate(slot["options"]) for code in bundle],
                )


# --------------------------------------------------------------------------- reads

def meta(db_path: str | Path = DEFAULT_DB_PATH) -> dict:
    with closing(connect(db_path)) as connection:
        rows = dict(connection.execute("SELECT key, value FROM meta").fetchall())
        rows["stats"] = json.loads(rows.get("stats", "{}"))
        rows["sources"] = [dict(row) for row in connection.execute("SELECT name, url, authority, license, use FROM sources")]
        return rows


def load_courses(connection: sqlite3.Connection) -> dict[str, dict]:
    tags: dict[str, list[str]] = {}
    for code, tag in connection.execute("SELECT code, tag FROM course_tags"):
        tags.setdefault(code, []).append(tag)
    courses = {}
    for row in connection.execute("SELECT * FROM courses"):
        courses[row["code"]] = {
            "code": row["code"],
            "subjects": json.loads(row["subjects"]),
            "number": row["number"],
            "title": row["title"],
            "credits": [row["credits_min"], row["credits_max"]],
            "requisites": json.loads(row["requisite_tree"]) if row["requisite_tree"] else None,
            "requisite_text": row["requisite_text"],
            "exclusions": json.loads(row["exclusions"]),
            "concurrent": bool(row["concurrent"]),
            "tags": tags.get(row["code"], []),
            "breadth_choice": json.loads(row["breadth_choice"]),
            "seasons": json.loads(row["offered_seasons"]),
            "offering_confidence": row["offering_confidence"],
            "offering_frequency": row["offering_frequency"],
            "avg_gpa": row["avg_gpa"],
            "grade_count": row["grade_count"],
            "last_taught": row["last_taught"],
            "repeatable": row["repeatable"],
        }
    return courses


def load_aliases(connection: sqlite3.Connection) -> dict[str, str]:
    return dict(connection.execute("SELECT alias, code FROM course_aliases").fetchall())


def list_programs(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        """SELECT p.id, p.name, p.degree, p.college, p.department, p.profile, p.parent_id,
                  p.has_named_options, p.confidence, p.guide_url, p.variants,
                  (SELECT COUNT(*) FROM requirement_blocks b WHERE b.program_id = p.id AND b.section = 'major') AS blocks
           FROM programs p ORDER BY p.name"""
    ).fetchall()
    return [
        {**dict(row), "variants": json.loads(row["variants"]), "has_named_options": bool(row["has_named_options"])}
        for row in rows
    ]


def load_program(connection: sqlite3.Connection, program_id: str) -> dict | None:
    row = connection.execute("SELECT * FROM programs WHERE id = ?", (program_id,)).fetchone()
    if not row:
        return None
    program = dict(row)
    for key in ("notes", "sample_plan", "variants"):
        program[key] = json.loads(program[key])
    program["has_named_options"] = bool(program["has_named_options"])
    blocks = []
    block_rows = connection.execute(
        "SELECT * FROM requirement_blocks WHERE program_id = ? ORDER BY position", (program_id,)
    ).fetchall()
    for block in block_rows:
        slots = []
        for slot in connection.execute(
            "SELECT * FROM requirement_slots WHERE block_id = ? ORDER BY position", (block["id"],)
        ).fetchall():
            bundles: dict[int, list[str]] = {}
            for option in connection.execute(
                "SELECT option_index, course_code FROM requirement_options WHERE slot_id = ? ORDER BY option_index, rowid",
                (slot["id"],),
            ):
                bundles.setdefault(option["option_index"], []).append(option["course_code"])
            slots.append({
                "label": slot["label"],
                "credits": [slot["credits_min"], slot["credits_max"]] if slot["credits_min"] is not None else None,
                "options": [bundles[index] for index in sorted(bundles)],
            })
        blocks.append({
            "id": block["id"],
            "key": block["block_key"],
            "section": block["section"],
            "name": block["name"],
            "path": json.loads(block["path"]),
            "rule": block["rule"],
            "count": block["min_count"],
            "credits": block["min_credits"],
            "pattern": json.loads(block["pattern"]) if block["pattern"] else None,
            "variant_group": block["variant_group"],
            "variant": block["variant"],
            "confidence": block["confidence"],
            "notes": json.loads(block["notes"]),
            "slots": slots,
        })
    program["blocks"] = blocks
    program["named_options"] = [
        dict(r) for r in connection.execute("SELECT id, name FROM programs WHERE parent_id = ? ORDER BY name", (program_id,))
    ]
    return program


def course_detail(connection: sqlite3.Connection, code: str) -> dict | None:
    row = connection.execute("SELECT * FROM courses WHERE code = ?", (code,)).fetchone()
    if not row:
        alias = connection.execute("SELECT code FROM course_aliases WHERE alias = ?", (code,)).fetchone()
        if not alias:
            return None
        row = connection.execute("SELECT * FROM courses WHERE code = ?", (alias[0],)).fetchone()
    code = row["code"]
    detail = dict(row)
    for key in ("subjects", "exclusions", "breadth_choice", "offered_seasons", "offering_counts", "keywords"):
        detail[key] = json.loads(detail[key])
    detail["requisite_tree"] = json.loads(detail["requisite_tree"]) if detail["requisite_tree"] else None
    detail["tags"] = [r[0] for r in connection.execute("SELECT tag FROM course_tags WHERE code = ?", (code,))]
    detail["grades"] = [
        {**dict(r), "instructors": json.loads(r["instructors"])}
        for r in connection.execute(
            "SELECT * FROM grade_distributions WHERE code = ? ORDER BY CASE term WHEN 'cumulative' THEN 0 ELSE 1 END, term DESC",
            (code,),
        )
    ]
    detail["instructors"] = [
        dict(r) for r in connection.execute(
            """SELECT ci.instructor AS name, ci.terms, ci.last_term, i.display_name, i.department, i.position,
                      i.rmp_rating, i.rmp_difficulty, i.rmp_count, i.rmp_would_take_again, i.rmp_id, i.avg_gpa
               FROM course_instructors ci LEFT JOIN instructors i ON i.name = ci.instructor
               WHERE ci.code = ? ORDER BY ci.rank LIMIT 12""",
            (code,),
        )
    ]
    detail["unlocks"] = [r[0] for r in connection.execute(
        "SELECT code FROM course_prereqs WHERE prereq_code = ? ORDER BY code LIMIT 60", (code,))]
    detail["required_by"] = [
        dict(r) for r in connection.execute(
            """SELECT DISTINCT p.id, p.name, b.name AS block
               FROM requirement_options o
               JOIN requirement_slots s ON s.id = o.slot_id
               JOIN requirement_blocks b ON b.id = s.block_id
               JOIN programs p ON p.id = b.program_id
               WHERE o.course_code = ? AND b.section = 'major' AND b.rule != 'recommended'
               ORDER BY p.name LIMIT 60""",
            (code,),
        )
    ]
    return detail


def search_courses(
    connection: sqlite3.Connection,
    query: str,
    limit: int = 30,
    tag: str | None = None,
    *,
    filters: dict | None = None,
) -> list[dict]:
    """Search the catalog using only fields present in the local snapshot.

    ``tag`` remains for the original frontend/API.  New discovery controls use
    ``filters`` so adding a facet does not require another parallel query path.
    """

    filters = filters or {}
    query = " ".join(query.upper().split())
    params: list = []
    where = []
    if query:
        like = f"%{query}%"
        where.append(
            "(c.code LIKE ? OR UPPER(c.title) LIKE ? OR UPPER(c.description) LIKE ? "
            "OR UPPER(c.keywords) LIKE ? "
            "OR c.code IN (SELECT code FROM course_aliases WHERE UPPER(alias) LIKE ?) "
            "OR c.code IN (SELECT ci.code FROM course_instructors ci WHERE UPPER(ci.instructor) LIKE ?))"
        )
        params += [like, like, like, like, like.replace(" ", ""), like]
    tags = filters.get("tags") or ([tag] if tag else [])
    for selected_tag in tags:
        where.append("c.code IN (SELECT code FROM course_tags WHERE tag = ?)")
        params.append(selected_tag)
    if filters.get("department"):
        where.append("c.subjects LIKE ?")
        params.append(f'%"{filters["department"].upper()}"%')
    if filters.get("credits") is not None:
        where.append("c.credits_min <= ? AND c.credits_max >= ?")
        params += [filters["credits"], filters["credits"]]
    if filters.get("level_min") is not None:
        where.append("CAST(c.number AS INTEGER) >= ?")
        params.append(filters["level_min"])
    if filters.get("level_max") is not None:
        where.append("CAST(c.number AS INTEGER) <= ?")
        params.append(filters["level_max"])
    if filters.get("requisites") == "none":
        where.append("(c.requisite_tree IS NULL OR c.requisite_tree IN ('', 'null', '{}'))")
    elif filters.get("requisites") == "listed":
        where.append("c.requisite_tree IS NOT NULL AND c.requisite_tree NOT IN ('', 'null', '{}')")
    if filters.get("prerequisite_count_min") is not None:
        where.append("(SELECT COUNT(*) FROM course_prereqs cp WHERE cp.code = c.code) >= ?")
        params.append(filters["prerequisite_count_min"])
    if filters.get("prerequisite_count_max") is not None:
        where.append("(SELECT COUNT(*) FROM course_prereqs cp WHERE cp.code = c.code) <= ?")
        params.append(filters["prerequisite_count_max"])
    if filters.get("gpa_min") is not None:
        where.append("c.avg_gpa >= ?")
        params.append(filters["gpa_min"])
    if filters.get("gpa_max") is not None:
        where.append("c.avg_gpa <= ?")
        params.append(filters["gpa_max"])
    if filters.get("grade_count_min") is not None:
        where.append("c.grade_count >= ?")
        params.append(filters["grade_count_min"])
    if filters.get("instructor"):
        where.append("c.code IN (SELECT ci.code FROM course_instructors ci WHERE UPPER(ci.instructor) LIKE ?)")
        params.append(f'%{filters["instructor"].upper()}%')
    if filters.get("season"):
        where.append("c.offered_seasons LIKE ?")
        params.append(f'%"{filters["season"]}"%')
    if filters.get("frequency"):
        where.append("c.offering_frequency = ?")
        params.append(filters["frequency"])
    if filters.get("easy_eligible"):
        where += [
            "CAST(c.number AS INTEGER) < 700",
            "c.grade_count >= 100",
            "c.avg_gpa IS NOT NULL",
            "LOWER(c.title) NOT LIKE '%independent study%'",
            "LOWER(c.title) NOT LIKE '%thesis%'",
            "LOWER(c.title) NOT LIKE '%dissertation%'",
            "LOWER(c.title) NOT LIKE '%internship%'",
            "LOWER(c.title) NOT LIKE '%clinical rotation%'",
            "LOWER(c.title) NOT LIKE '%special topics%'",
            "(SELECT COUNT(*) FROM grade_distributions gt WHERE gt.code = c.code AND gt.term != 'cumulative') >= 3",
        ]
    order = {
        "gpa_desc": "c.avg_gpa DESC, c.grade_count DESC, c.code",
        "gpa_asc": "c.avg_gpa ASC, c.grade_count DESC, c.code",
        "frequency": "CASE c.offering_frequency WHEN 'every semester' THEN 0 WHEN 'yearly' THEN 1 ELSE 2 END, c.code",
    }.get(filters.get("sort"), "CASE WHEN c.code LIKE ? THEN 0 ELSE 1 END, c.grade_count IS NULL, c.grade_count DESC")
    sql = (
        "SELECT c.code, c.subjects, c.number, c.title, c.credits_min, c.credits_max, c.avg_gpa, c.grade_count, "
        "c.offered_seasons, c.offering_frequency, c.offering_confidence, c.last_taught, c.requisite_tree, "
        "(SELECT COUNT(*) FROM course_prereqs cp WHERE cp.code = c.code) AS prerequisite_count, "
        "(SELECT COUNT(*) FROM grade_distributions gt WHERE gt.code = c.code AND gt.term != 'cumulative') AS observed_terms, "
        "(SELECT gd.d + gd.f FROM grade_distributions gd WHERE gd.code = c.code AND gd.term = 'cumulative') AS df_count "
        "FROM courses c"
        + (" WHERE " + " AND ".join(where) if where else "")
        + f" ORDER BY {order} LIMIT ?"
    )
    if "?" in order:
        params.append(f"{query}%")
    params.append(limit)
    rows = []
    for row in connection.execute(sql, params):
        item = dict(row)
        for key in ("subjects", "offered_seasons"):
            item[key] = json.loads(item[key])
        item["requisite_tree"] = json.loads(item["requisite_tree"]) if item["requisite_tree"] else None
        total = item.get("grade_count") or 0
        item["df_rate"] = round(100 * (item.get("df_count") or 0) / total, 1) if total else None
        rows.append(item)

    program_ids = filters.get("program_ids") or []
    if program_ids and rows:
        placeholders = ",".join("?" for _ in program_ids)
        for item in rows:
            item["requirement_matches"] = [dict(match) for match in connection.execute(
                f"""SELECT DISTINCT p.id AS program_id, p.name AS program_name, b.id AS block_id, b.name AS block_name
                    FROM requirement_options o
                    JOIN requirement_slots s ON s.id = o.slot_id
                    JOIN requirement_blocks b ON b.id = s.block_id
                    JOIN programs p ON p.id = b.program_id
                    WHERE o.course_code = ? AND p.id IN ({placeholders}) AND b.rule != 'recommended'
                    ORDER BY p.name, b.position""",
                [item["code"], *program_ids],
            )]
    return rows


def easiest_courses(connection: sqlite3.Connection, *, query: str = "", limit: int = 60, filters: dict | None = None) -> list[dict]:
    """Evidence-led high-outcome discovery, not a synthetic difficulty score."""

    merged = {**(filters or {}), "easy_eligible": True, "sort": "gpa_desc"}
    cohort = search_courses(connection, query, limit=2000, filters=merged)
    groups: dict[tuple[str, int], list[float]] = {}
    for row in cohort:
        subject = (row.get("subjects") or [""])[0]
        band = (int(row.get("number") or 0) // 100) * 100
        groups.setdefault((subject, band), []).append(row["avg_gpa"])
    for row in cohort:
        subject = (row.get("subjects") or [""])[0]
        band = (int(row.get("number") or 0) // 100) * 100
        peers = sorted(groups.get((subject, band), []))
        below = sum(1 for value in peers if value < row["avg_gpa"])
        row["peer_percentile"] = round(100 * below / max(1, len(peers)))
        row["peer_group"] = f"{subject or 'UW'} {band}–{band + 99} level"
        row["evidence"] = {
            "historical_gpa": row["avg_gpa"],
            "grade_count": row.get("grade_count") or 0,
            "df_rate": row.get("df_rate"),
            "observed_terms": row.get("observed_terms") or 0,
            "prerequisite_count": row.get("prerequisite_count") or 0,
            "offering_frequency": row.get("offering_frequency"),
        }
    cohort.sort(key=lambda row: (-row["peer_percentile"], -row["grade_count"], row["code"]))
    return cohort[:limit]


def list_departments(connection: sqlite3.Connection) -> list[dict]:
    counts: dict[str, int] = {}
    for row in connection.execute("SELECT subjects FROM courses"):
        for subject in json.loads(row[0]):
            counts[subject] = counts.get(subject, 0) + 1
    return [{"id": key, "name": key, "courses": counts[key]} for key in sorted(counts)]


def search_instructors(connection: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    like = f"%{' '.join(query.upper().split())}%"
    return [dict(row) for row in connection.execute(
        """SELECT i.name AS id, i.display_name, i.department, i.position, i.rmp_rating, i.rmp_difficulty,
                  i.rmp_count, i.rmp_would_take_again, i.avg_gpa,
                  (SELECT COUNT(*) FROM course_instructors ci WHERE ci.instructor = i.name) AS course_count
           FROM instructors i WHERE UPPER(i.name) LIKE ? OR UPPER(i.display_name) LIKE ?
           ORDER BY CASE WHEN UPPER(i.name) LIKE ? THEN 0 ELSE 1 END, i.rmp_count DESC, i.display_name LIMIT ?""",
        (like, like, like.lstrip("%"), limit),
    )]


def instructor_detail(connection: sqlite3.Connection, instructor_id: str) -> dict | None:
    key = instructor_id.replace("_", " ").upper()
    row = connection.execute("SELECT * FROM instructors WHERE name = ?", (key,)).fetchone()
    if not row:
        return None
    detail = dict(row)
    detail["id"] = detail.pop("name")
    detail["courses"] = [dict(course) for course in connection.execute(
        """SELECT c.code, c.title, c.credits_min, c.credits_max, c.avg_gpa, c.grade_count,
                  ci.terms, ci.last_term, c.offered_seasons
           FROM course_instructors ci JOIN courses c ON c.code = ci.code
           WHERE ci.instructor = ? ORDER BY ci.last_term DESC, ci.terms DESC, c.code LIMIT 80""",
        (key,),
    )]
    for course in detail["courses"]:
        course["offered_seasons"] = json.loads(course["offered_seasons"])
    return detail


# --------------------------------------------------------------------------- plans

def save_plan(connection: sqlite3.Connection, payload: dict) -> str:
    plan_id = payload.get("id") or uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {**payload, "id": plan_id}
    with connection:
        connection.execute(
            """INSERT INTO saved_plans(id, name, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name = excluded.name, payload = excluded.payload, updated_at = excluded.updated_at""",
            (plan_id, payload.get("name") or "My UW plan", _j(payload), now, now),
        )
    return plan_id


def list_plans(connection: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in connection.execute("SELECT id, name, updated_at FROM saved_plans ORDER BY updated_at DESC")]


def get_plan(connection: sqlite3.Connection, plan_id: str) -> dict | None:
    row = connection.execute("SELECT payload FROM saved_plans WHERE id = ?", (plan_id,)).fetchone()
    return json.loads(row[0]) if row else None


def delete_plan(connection: sqlite3.Connection, plan_id: str) -> bool:
    with connection:
        return connection.execute("DELETE FROM saved_plans WHERE id = ?", (plan_id,)).rowcount > 0
