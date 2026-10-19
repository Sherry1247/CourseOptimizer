"""Course Search & Enroll parsing, term codes, the offered-course check and the timeline."""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import enroll  # noqa: E402
import timeline  # noqa: E402
from transcript import resolve_candidates  # noqa: E402

# One real Spring 2027 MATH 340 package (lecture + discussion), trimmed.
RAW_PACKAGE = {
    "enrollmentClassNumber": 61850,
    "packageEnrollmentStatus": {"availableSeats": 30, "waitlistTotal": 0, "status": "OPEN"},
    "onlineOnly": False,
    "published": True,
    "classMeetings": [
        {"meetingType": "CLASS", "meetingTimeStart": 57300000, "meetingTimeEnd": 60300000, "meetingDays": "M",
         "building": {"buildingName": "Van Vleck Hall"}, "room": "B129"},
        {"meetingType": "CLASS", "meetingTimeStart": 55800000, "meetingTimeEnd": 60300000, "meetingDays": "TR",
         "building": {"buildingName": "Soils Building"}, "room": "270"},
        {"meetingType": "EXAM", "meetingTimeStart": 49500000, "meetingTimeEnd": 56700000, "meetingDays": None,
         "examDate": 1809234000000},
    ],
    "sections": [
        {"classUniqueId": {"classNumber": 49051}, "type": "LEC", "sectionNumber": "003", "sessionCode": "A1",
         "instructors": [{"name": {"first": "Autumn", "last": "Kent"}}]},
        {"classUniqueId": {"classNumber": 61850}, "type": "DIS", "sectionNumber": "345", "sessionCode": "A1", "instructors": []},
    ],
}


class TermCodeTests(unittest.TestCase):
    def test_codes_follow_academic_year(self):
        self.assertEqual(enroll.term_code("Fall", 2026), "1272")
        self.assertEqual(enroll.term_code("Spring", 2027), "1274")
        self.assertEqual(enroll.term_code("Summer", 2027), "1276")
        self.assertEqual(enroll.term_name("1272"), "Fall 2026")
        self.assertEqual(enroll.term_name("1274"), "Spring 2027")

    def test_cross_listed_keys(self):
        self.assertEqual(enroll.course_keys("COMP SCI/MATH 240"), ["COMP SCI 240", "MATH 240"])
        self.assertEqual(enroll.course_keys("comp  sci 400"), ["COMP SCI 400"])


class ParsingTests(unittest.TestCase):
    def test_package_times_are_local_minutes(self):
        pkg = enroll.parse_package(RAW_PACKAGE)
        self.assertEqual(pkg["classNumber"], 61850)
        self.assertEqual(pkg["status"], "OPEN")
        self.assertEqual(pkg["seats"], 30)
        # 57300000 ms is 15:55 in the shifted clock, i.e. 9:55 a.m.
        self.assertEqual(pkg["meetings"][0], {"days": "M", "start": 595, "end": 645, "building": "Van Vleck Hall", "room": "B129"})
        self.assertEqual(pkg["meetings"][1]["start"], 570)  # 9:30 a.m. lecture
        self.assertEqual([s["type"] for s in pkg["sections"]], ["LEC", "DIS"])
        self.assertEqual(pkg["sections"][0]["instructors"], ["Autumn Kent"])
        self.assertEqual(pkg["exams"][0]["start"], 465)  # 7:45 a.m.

    def test_session_dates_in_madison_time(self):
        session = enroll.parse_session({"sessionCode": "A1", "beginDate": 1800338400000, "addDate": 1801288799999,
                                        "drwDate": 1801115999999, "dropDate": 1808197199999, "endDate": 1809147599999})
        self.assertEqual(session["begin"], "2027-01-19")
        self.assertEqual(session["drop_no_dr"], "2027-01-27")
        self.assertEqual(session["add"], "2027-01-29")
        self.assertEqual(session["drop"], "2027-04-19")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name)
        snapshot = {"term": {"code": "1274", "name": "Spring 2027", "classes_begin": "2027-01-19", "classes_end": "2027-04-30"},
                    "sessions": {"A1": {"code": "A1", "add": "2027-01-29", "drop_no_dr": "2027-01-27", "drop": "2027-04-19", "edit": "2027-02-12"}},
                    "offered": ["COMP SCI 400", "MATH 240"], "courses": {"COMP SCI 400": {"code": "COMP SCI 400", "packages": []}}}
        with gzip.open(folder / "1274.json.gz", "wt", encoding="utf-8") as handle:
            json.dump(snapshot, handle)
        self.store = enroll.EnrollStore(folder, live=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_offered_is_three_valued(self):
        self.assertTrue(self.store.offered("Spring", 2027, "COMP SCI 400"))
        self.assertTrue(self.store.offered("Spring", 2027, "COMP SCI/MATH 240"))
        self.assertFalse(self.store.offered("Spring", 2027, "COMP SCI 577"))
        self.assertIsNone(self.store.offered("Fall", 2027, "COMP SCI 400"))

    def test_packages_from_snapshot_and_offline_miss(self):
        self.assertEqual(self.store.packages("1274", "COMP SCI 400")["source"], "snapshot")
        self.assertIsNone(self.store.packages("1274", "COMP SCI 577"))

    def test_timeline_marks_the_students_window(self):
        dates = {"appointments": {"1274": {"published": True, "windows": [
            {"group": "Senior", "start": "2026-11-10", "end": "2026-11-12"},
            {"group": "Sophomore", "start": "2026-11-17", "end": "2026-11-20"}]}}, "sources": {}}
        result = timeline.build_timeline(self.store, dates, standing="Sophomore", today=date(2026, 10, 18))
        enroll_events = [e for e in result["events"] if e["kind"] == "enroll"]
        self.assertEqual([e["mine"] for e in enroll_events], [False, True])
        self.assertEqual(enroll_events[1]["title"], "Spring 2027 enrollment opens · Sophomores")
        titles = [e["title"] for e in result["events"]]
        self.assertIn("Spring 2027: Last day to drop without a DR", titles)
        later = timeline.build_timeline(self.store, dates, standing="Sophomore", today=date(2027, 2, 1))
        self.assertNotIn("Spring 2027: Last day to add a course", [e["title"] for e in later["events"]])

    def test_standing_thresholds(self):
        self.assertEqual(timeline.standing_for(23), "Freshman")
        self.assertEqual(timeline.standing_for(24), "Sophomore")
        self.assertEqual(timeline.standing_for(54), "Junior")
        self.assertEqual(timeline.standing_for(86), "Senior")


class ResolveTests(unittest.TestCase):
    def test_longest_guess_that_matches_wins(self):
        courses = {"COMP SCI 400": {"title": "Programming III", "credits": [3, 3]},
                   "COMP SCI/E C E 252": {"title": "Intro to Computer Engineering", "credits": [3, 3]}}
        aliases = {"COMPSCI 252": "COMP SCI/E C E 252"}
        result = resolve_candidates([["PROGRAMMING III COMP SCI 400", "III COMP SCI 400", "COMP SCI 400", "SCI 400"],
                                     ["COMPSCI 252"], ["NOPE 101"]], courses, aliases)
        self.assertEqual(result[0]["code"], "COMP SCI 400")
        self.assertEqual(result[1]["code"], "COMP SCI/E C E 252")
        self.assertIsNone(result[2])


if __name__ == "__main__":
    unittest.main()
