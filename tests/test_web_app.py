import unittest

import helpers

try:
    from starlette.testclient import TestClient
except ImportError:  # httpx missing
    TestClient = None


@unittest.skipIf(TestClient is None, "starlette TestClient requires httpx")
class WebAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import web_app
        web_app.STATE = web_app.CatalogState(helpers.database())
        cls.client = TestClient(web_app.app)

    def test_health_and_meta(self):
        self.assertEqual(self.client.get("/api/health").json()["status"], "ok")
        meta = self.client.get("/api/meta").json()
        self.assertEqual(meta["catalog_year"], "2026-2027")
        self.assertIn("comm_a", meta["tags"])

    def test_programs_and_course(self):
        programs = self.client.get("/api/programs").json()
        self.assertGreater(len(programs), 250)
        course = self.client.get("/api/courses/COMP%20SCI%20577").json()
        self.assertEqual(course["code"], "COMP SCI 577")
        self.assertEqual(self.client.get("/api/courses/NOPE%20999").status_code, 404)

    def test_generate_and_validate(self):
        body = {"programs": ["statistics-bs"], "startYear": 2026, "gradYear": 2030}
        plan = self.client.post("/api/plan/generate", json=body).json()
        self.assertEqual(len(plan["terms"]), 8)
        check = self.client.post("/api/plan/validate", json={**body, "plan": {"terms": plan["terms"]}}).json()
        self.assertIn("audit", check)

    def test_bad_request(self):
        self.assertEqual(self.client.post("/api/plan/generate", json={"programs": []}).status_code, 400)

    def test_second_majors(self):
        rows = self.client.get("/api/programs/economics-bs/second-majors").json()
        self.assertTrue(rows)
        self.assertNotIn("Economics", rows[0]["name"].split(",")[0])

    def test_discovery_and_comparison_apis(self):
        search = self.client.get("/api/search", params={"q": "machine learning"}).json()
        self.assertTrue(search["courses"])
        self.assertIn("professors", search)
        self.assertIn("majors", search)
        self.assertEqual(search["groups"][0]["type"], "course")
        self.assertIn("href", search["groups"][0]["results"][0])

        courses = self.client.get(
            "/api/courses",
            params={"department": "COMP SCI", "gpa_min": 3.0, "program": "computer-sciences-ba"},
        ).json()
        self.assertTrue(courses)
        self.assertTrue(all("COMP SCI" in row["subjects"] for row in courses))

        easiest = self.client.get("/api/discovery/easiest", params={"credits": 3, "limit": 8}).json()
        self.assertTrue(easiest)
        self.assertIn("evidence", easiest[0])

        comparison = self.client.get("/api/programs/computer-sciences-ba/compare/economics-ba").json()
        self.assertEqual(comparison["secondary"]["id"], "economics-ba")
        self.assertIn("additional_credits", comparison)
        self.assertIn("unique_requirements", comparison)

    def test_spa_deep_links(self):
        for path in ("/plan", "/explore/courses", "/courses/COMP%20SCI%20400"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("BadgerPlan", response.text)

    def test_transcript_review_is_conservative(self):
        response = self.client.post("/api/transcript/parse", json={
            "text": "Fall 2025\nCOMP SCI 300 Programming II 3.00 A\nMATH 221 Calculus 5.00 W\nNOT A COURSE 999 3.00 A"
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        by_code = {row["code"]: row for row in body["matches"]}
        self.assertTrue(by_code["COMP SCI 300"]["include"])
        self.assertFalse(by_code["MATH 221"]["include"])
        self.assertNotIn("NOT A COURSE 999", by_code)


if __name__ == "__main__":
    unittest.main()
