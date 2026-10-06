"""Shared test fixtures: one temporary database built from the committed snapshot."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "src", ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import catalog_db  # noqa: E402

_CACHE: dict = {}


def database() -> Path:
    if "db" not in _CACHE:
        folder = Path(tempfile.mkdtemp(prefix="badgerplan-test-"))
        _CACHE["db"] = catalog_db.initialize_database(folder / "test.db", force=True)
    return _CACHE["db"]


def catalog():
    if "catalog" not in _CACHE:
        connection = catalog_db.connect(database())
        _CACHE["catalog"] = (connection, catalog_db.load_courses(connection), catalog_db.load_aliases(connection))
    return _CACHE["catalog"]


def program(program_id: str) -> dict:
    connection, _, _ = catalog()
    return catalog_db.load_program(connection, program_id)
