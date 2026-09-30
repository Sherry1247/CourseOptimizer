import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from planner import Catalog, Course, generate_plan, prerequisite_depth  # noqa: E402


class PlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.from_json(ROOT / "src" / "uw_madison_data.json")

    def test_catalog_references_are_consistent(self):
        self.assertEqual([], self.catalog.validate())

    def test_prerequisite_is_always_in_an_earlier_term(self):
        result = generate_plan(
            self.catalog,
            ["Computer Sciences"],
            start_term="Fall",
            start_year=2026,
            years=4,
            max_credits_per_term=15,
        )
        positions = {
            course.code: term_index
            for term_index, term in enumerate(result.terms)
            for course in term.courses
        }
        for term in result.terms:
            for course in term.courses:
                for prerequisite in course.prerequisites:
                    self.assertLess(positions[prerequisite], positions[course.code])

    def test_completed_course_unlocks_dependent_course(self):
        result = generate_plan(
            self.catalog,
            ["Computer Sciences"],
            completed_courses=["COMP SCI 200"],
            start_term="Fall",
            start_year=2026,
            years=1,
        )
        first_term_codes = {course.code for course in result.terms[0].courses}
        self.assertIn("COMP SCI 300", first_term_codes)
        self.assertNotIn("COMP SCI 200", first_term_codes)

    def test_double_major_uses_union_and_reports_intersection(self):
        result = generate_plan(
            self.catalog,
            ["Computer Sciences", "Mathematics"],
            years=4,
        )
        cs = set(self.catalog.majors["Computer Sciences"]["required_courses"])
        math = set(self.catalog.majors["Mathematics"]["required_courses"])
        self.assertEqual(cs | math, set(result.required_courses))
        self.assertEqual(cs & math, set(result.overlap_courses))

    def test_credit_limit_is_respected(self):
        result = generate_plan(
            self.catalog,
            ["Economics"],
            years=5,
            max_credits_per_term=6,
        )
        self.assertTrue(all(term.credits <= 6 for term in result.terms))

    def test_term_offering_is_respected(self):
        result = generate_plan(
            self.catalog,
            ["Mathematics"],
            completed_courses=["MATH 221"],
            start_term="Fall",
            start_year=2026,
            years=2,
        )
        math_222_term = next(
            term for term in result.terms if any(c.code == "MATH 222" for c in term.courses)
        )
        self.assertEqual("Spring", math_222_term.term)

    def test_missing_requirement_is_reported(self):
        catalog = Catalog(
            courses={"A 100": Course("A 100", "Intro", 3)},
            majors={"Example": {"required_courses": ["A 100", "A 200"]}},
        )
        result = generate_plan(catalog, ["Example"])
        self.assertEqual({"A 200"}, set(result.missing_catalog_courses))

    def test_non_requirement_prerequisite_is_added_to_plan(self):
        catalog = Catalog(
            courses={
                "A 100": Course("A 100", "Foundation", 3),
                "A 200": Course("A 200", "Required", 3, prerequisites=("A 100",)),
            },
            majors={"Example": {"required_courses": ["A 200"]}},
        )
        result = generate_plan(catalog, ["Example"], years=1)
        self.assertEqual({"A 100"}, set(result.supporting_courses))
        self.assertEqual("A 100", result.terms[0].courses[0].code)
        self.assertEqual("A 200", result.terms[1].courses[0].code)

    def test_prerequisite_depth(self):
        self.assertEqual(0, prerequisite_depth("COMP SCI 200", self.catalog.courses))
        self.assertEqual(2, prerequisite_depth("COMP SCI 400", self.catalog.courses))


if __name__ == "__main__":
    unittest.main()
