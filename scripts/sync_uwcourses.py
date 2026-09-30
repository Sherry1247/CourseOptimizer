"""Import the public UW Courses Parquet snapshot into the local SQLite catalog.

The snapshot is a derived source, not an official UW publication.  Each imported
row is labeled accordingly; program requirements must still come from UW Guide.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from catalog_db import DEFAULT_DB_PATH, connect, initialize_database  # noqa: E402
from planner import guide_url  # noqa: E402


PARQUET_API = "https://huggingface.co/api/datasets/twangodev/uwcourses/parquet/courses_current/train"
COURSE_PATTERN = re.compile(r"\b[A-Z](?:[A-Z ]{0,12}[A-Z])?\s+\d{1,3}\b")


def fetch_parquet_urls() -> list[str]:
    response = requests.get(PARQUET_API, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("UW Courses dataset API did not return Parquet URLs")
    return payload


def normalize_value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return value


def extract_prerequisite_codes(ast_json: object) -> set[str]:
    value = normalize_value(ast_json)
    if not value:
        return set()
    try:
        tree = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return set()
    codes: set[str] = set()
    for node in tree.get("nodes", []):
        course = node.get("course")
        if isinstance(course, str):
            codes.update(COURSE_PATTERN.findall(course.upper()))
        elif isinstance(course, dict):
            text = " ".join(str(part) for part in course.values())
            codes.update(COURSE_PATTERN.findall(text.upper()))
    return {" ".join(code.split()) for code in codes}


def sync(db_path: Path, limit: int | None = None) -> int:
    initialize_database(db_path)
    frames = [pd.read_parquet(url) for url in fetch_parquet_urls()]
    data = pd.concat(frames, ignore_index=True)
    if limit:
        data = data.head(limit)

    now = datetime.now(timezone.utc).isoformat()
    with closing(connect(db_path)) as connection, connection:
        derived_source = connection.execute(
            "SELECT id FROM sources WHERE name = 'UW Courses open dataset'"
        ).fetchone()[0]
        catalog_id = connection.execute(
            "SELECT id FROM catalog_versions ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]

        imported = 0
        for row in data.to_dict(orient="records"):
            code = normalize_value(row.get("course_id"))
            title = normalize_value(row.get("title"))
            if not code or not title:
                continue
            code = " ".join(str(code).upper().split())
            credits_min = float(normalize_value(row.get("credits_min")) or 0)
            credits_max = float(normalize_value(row.get("credits_max")) or credits_min)
            description = str(normalize_value(row.get("description")) or "")
            requirements_text = str(normalize_value(row.get("requirements_text")) or "")
            existing = connection.execute(
                "SELECT id FROM courses WHERE code = ? AND catalog_version_id = ?",
                (code, catalog_id),
            ).fetchone()
            if existing:
                course_id = existing[0]
                connection.execute(
                    """
                    UPDATE courses SET title=?, description=?, credits_min=?, credits_max=?,
                        requirements_text=?, guide_url=?, source_id=?, data_status=?
                    WHERE id=?
                    """,
                    (
                        title,
                        description,
                        credits_min,
                        credits_max,
                        requirements_text,
                        guide_url(code),
                        derived_source,
                        "derived-uwcourses-snapshot",
                        course_id,
                    ),
                )
            else:
                course_id = connection.execute(
                    """
                    INSERT INTO courses(
                        code, title, description, credits_min, credits_max,
                        requirements_text, guide_url, catalog_version_id, source_id, data_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        code,
                        title,
                        description,
                        credits_min,
                        credits_max,
                        requirements_text,
                        guide_url(code),
                        catalog_id,
                        derived_source,
                        "derived-uwcourses-snapshot",
                    ),
                ).lastrowid
            connection.execute("DELETE FROM prerequisites WHERE course_id = ?", (course_id,))
            for prerequisite in extract_prerequisite_codes(row.get("llm_requirements_ast_json")):
                if prerequisite != code:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO prerequisites(
                            course_id, prerequisite_code, group_key, evidence_text
                        ) VALUES (?, ?, 'derived', ?)
                        """,
                        (course_id, prerequisite, requirements_text),
                    )
            imported += 1

        connection.execute(
            "UPDATE sources SET accessed_at = ? WHERE id = ?", (now, derived_source)
        )
    return imported


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    imported = sync(args.db, args.limit)
    print(f"Imported {imported} UW Courses records into {args.db}")


if __name__ == "__main__":
    main()
