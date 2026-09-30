from contextlib import closing
import sqlite3
import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from catalog_db import catalog_payload, initialize_database, load_catalog, save_plan  # noqa: E402


class CatalogDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "catalog.db"
        initialize_database(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_stores_sources_programs_courses_and_requisites(self):
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertGreater(connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0], 0)
            self.assertGreater(connection.execute("SELECT COUNT(*) FROM programs").fetchone()[0], 0)
            self.assertGreater(connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0], 0)
            self.assertGreater(connection.execute("SELECT COUNT(*) FROM prerequisites").fetchone()[0], 0)

    def test_database_is_the_catalog_source(self):
        catalog = load_catalog(self.db_path)
        payload = catalog_payload(self.db_path)
        self.assertIn("Computer Sciences", catalog.majors)
        self.assertEqual(len(catalog.courses), len(payload["courses"]))

    def test_plan_can_be_saved_with_dragged_term_assignments(self):
        plan_id = save_plan(
            {
                "name": "Transfer CS plan",
                "studentType": "transfer",
                "graduationYear": 2029,
                "primaryMajor": "Computer Sciences",
                "secondMajor": "Mathematics",
                "terms": [{"label": "Fall 2026", "courses": ["COMP SCI 200"]}],
            },
            self.db_path,
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM saved_plans WHERE id = ?", (plan_id,)).fetchone()[0])
            self.assertEqual("COMP SCI 200", connection.execute("SELECT course_code FROM plan_items WHERE plan_id = ?", (plan_id,)).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
