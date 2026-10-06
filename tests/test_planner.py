import unittest

import helpers
from planner import PlanRequest, generate_plan, term_sequence, validate_plan
from requisites import evaluate


def plan_for(programs, **payload):
    _, courses, aliases = helpers.catalog()
    loaded = [helpers.program(p) for p in programs]
    request = PlanRequest.from_payload({"programs": programs, **payload})
    return generate_plan(courses, loaded, request, aliases), request, loaded


class TermSequenceTests(unittest.TestCase):
    def test_four_years(self):
        terms = term_sequence("Fall", 2026, "Spring", 2030, include_summer=False)
        self.assertEqual([t.label for t in terms][:3], ["Fall 2026", "Spring 2027", "Fall 2027"])
        self.assertEqual(len(terms), 8)

    def test_summers_and_spring_start(self):
        terms = term_sequence("Spring", 2027, "Fall", 2028, include_summer=True)
        self.assertEqual([t.label for t in terms], ["Spring 2027", "Summer 2027", "Fall 2027", "Spring 2028", "Summer 2028", "Fall 2028"])

    def test_invalid_timeline(self):
        with self.assertRaises(ValueError):
            PlanRequest.from_payload({"programs": ["computer-sciences-bs"], "startYear": 2026, "gradYear": 2026, "gradSeason": "Spring"})


class DoubleMajorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result, cls.request, cls.programs = plan_for(["computer-sciences-bs", "data-science-bs"],
                                                         startYear=2026, gradYear=2030)

    def test_every_requirement_met(self):
        audit = self.result["audit"]
        for program in audit["programs"]:
            self.assertEqual(program["summary"]["percent"], 100, program["name"])
        self.assertGreaterEqual(audit["credits"]["planned"], 120)
        self.assertFalse(self.result["unscheduled"])

    def test_courses_are_shared_between_majors(self):
        shared = set(self.result["audit"]["shared_courses"])
        self.assertGreaterEqual(len(shared), 5)
        self.assertIn("COMP SCI 300", shared)

    def test_prerequisites_come_first(self):
        _, courses, _ = helpers.catalog()
        seen: set[str] = set()
        for term in self.result["terms"]:
            this_term = {c["code"] for c in term["courses"]}
            for card in term["courses"]:
                info = courses.get(card["code"])
                if not info:
                    continue
                ok = evaluate(info["requisites"], lambda c: c in seen, credits_earned=999,
                              assume_placement=lambda code: (code or "").startswith("MATH"),
                              coreq_ok=lambda c: c in this_term)
                self.assertIsNot(ok, False, f"{card['code']} in {term['label']}")
            seen |= this_term

    def test_no_validation_errors(self):
        errors = [i for items in self.result["issues"].values() for i in items if i["level"] == "error"]
        self.assertEqual(errors, [])

    def test_moving_a_course_early_is_flagged(self):
        _, courses, aliases = helpers.catalog()
        terms = [dict(t, courses=list(t["courses"])) for t in self.result["terms"]]
        late = next(c for c in terms[-3]["courses"] + terms[-4]["courses"] if c["code"].startswith("COMP SCI 5"))
        for t in terms:
            t["courses"] = [c for c in t["courses"] if c["code"] != late["code"]]
        terms[0]["courses"].append(late)
        result = validate_plan(courses, self.programs, self.request, {"terms": terms}, aliases)
        self.assertTrue(any(i["level"] == "error" for i in result["issues"].get(late["code"], [])))


class StudentTypeTests(unittest.TestCase):
    def test_prior_credit_is_not_rescheduled(self):
        result, _, _ = plan_for(["economics-bs"], prior=[{"code": "ECON 101", "status": "ap"}, {"code": "MATH 221", "status": "ap"}])
        planned = {c["code"] for t in result["terms"] for c in t["courses"]}
        self.assertNotIn("ECON 101", planned)
        self.assertNotIn("MATH 221", planned)

    def test_transfer_short_timeline(self):
        result, _, _ = plan_for(["economics-bs"], studentType="transfer", startSeason="Fall", startYear=2026,
                                gradSeason="Spring", gradYear=2028, genericCredits=50,
                                firstCollegeSeason="Fall", firstCollegeYear=2024,
                                prior=[{"code": "ECON 101", "status": "transfer"}, {"code": "MATH 221", "status": "transfer"}])
        self.assertEqual(len(result["terms"]), 4)
        self.assertEqual(result["rules"]["gened"], "Legacy Gen Ed")  # first college term before Summer 2026
        self.assertEqual(result["audit"]["programs"][0]["summary"]["percent"], 100)

    def test_first_year_gets_core_gened(self):
        result, _, _ = plan_for(["economics-bs"], startYear=2026)
        self.assertEqual(result["rules"]["gened"], "Core GenEd")

    def test_corequisites_share_a_term(self):
        result, _, _ = plan_for(["music-ba"])
        term_of = {c["code"]: i for i, t in enumerate(result["terms"]) for c in t["courses"]}
        self.assertEqual(term_of.get("MUSIC 122"), term_of.get("MUSIC 172"))

    def test_language_sequence_is_expanded(self):
        result, _, _ = plan_for(["spanish-ba"])
        planned = {c["code"] for t in result["terms"] for c in t["courses"]}
        self.assertIn("SPANISH 226", planned)
        self.assertEqual(result["audit"]["programs"][0]["summary"]["percent"], 100)


if __name__ == "__main__":
    unittest.main()
