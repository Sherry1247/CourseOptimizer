import unittest

import helpers
import catalog_db


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = catalog_db.connect(helpers.database())

    def test_counts(self):
        count = lambda table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        self.assertGreater(count("courses"), 8000)
        self.assertGreater(count("programs"), 250)
        self.assertGreater(count("course_prereqs"), 5000)
        self.assertGreater(count("grade_distributions"), 20000)

    def test_course_detail(self):
        detail = catalog_db.course_detail(self.connection, "COMP SCI 400")
        self.assertEqual(detail["title"], "Programming III")
        self.assertIn("COMP SCI 300", str(detail["requisite_tree"]))
        self.assertTrue(detail["grades"])
        self.assertTrue(any(program["id"] == "computer-sciences-bs" for program in detail["required_by"]))

    def test_alias_lookup(self):
        detail = catalog_db.course_detail(self.connection, "MATH 240")
        self.assertEqual(detail["code"], "COMP SCI/MATH 240")

    def test_search(self):
        rows = catalog_db.search_courses(self.connection, "calculus", limit=5)
        self.assertTrue(rows)
        rows = catalog_db.search_courses(self.connection, "", limit=5, tag="comm_a")
        self.assertTrue(all(r["code"] for r in rows))

    def test_faceted_and_easiest_course_search(self):
        rows = catalog_db.search_courses(
            self.connection,
            "",
            limit=10,
            filters={"department": "COMP SCI", "gpa_min": 3.0, "grade_count_min": 100},
        )
        self.assertTrue(rows)
        self.assertTrue(all("COMP SCI" in row["subjects"] for row in rows))
        self.assertTrue(all(row["avg_gpa"] >= 3.0 and row["grade_count"] >= 100 for row in rows))

        easiest = catalog_db.easiest_courses(self.connection, limit=10, filters={"credits": 3})
        self.assertTrue(easiest)
        self.assertTrue(all(row["credits_min"] <= 3 <= row["credits_max"] for row in easiest))
        self.assertTrue(all(row["grade_count"] >= 100 and row["observed_terms"] >= 3 for row in easiest))
        self.assertIn("peer_percentile", easiest[0])

    def test_instructor_discovery(self):
        rows = catalog_db.search_instructors(self.connection, "Zhu", limit=10)
        self.assertTrue(rows)
        detail = catalog_db.instructor_detail(self.connection, rows[0]["id"])
        self.assertTrue(detail["courses"])

    def test_program_blocks(self):
        program = catalog_db.load_program(self.connection, "computer-sciences-bs")
        names = [b["name"] for b in program["blocks"]]
        self.assertIn("Basic Computer Sciences", names)
        self.assertEqual(program["profile"], "LS_BS")

    def test_plan_round_trip(self):
        plan_id = catalog_db.save_plan(self.connection, {"name": "Test", "settings": {"programs": ["x"]}, "terms": []})
        self.assertEqual(catalog_db.get_plan(self.connection, plan_id)["name"], "Test")
        self.assertTrue(catalog_db.delete_plan(self.connection, plan_id))


if __name__ == "__main__":
    unittest.main()
