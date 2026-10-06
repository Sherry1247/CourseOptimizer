from pathlib import Path
import unittest

import helpers  # noqa: F401
from ingest.codes import CodeIndex
from ingest.designations import parse_designations
from ingest.guide_parser import ProgramParser, parse_rule
import scrape_uw_guide

FIXTURE = Path(__file__).parent / "fixtures" / "economics-bs.html"


class RuleTests(unittest.TestCase):
    def test_choose_phrases(self):
        self.assertEqual(parse_rule("Complete two:"), ("choose", 2, None))
        self.assertEqual(parse_rule("Mathematics (complete one):")[:2], ("choose", 1))
        self.assertEqual(parse_rule("300-level ART HIST (three required)")[:2], ("choose", 3))
        self.assertEqual(parse_rule("at least one course from three of these five areas:")[:2], ("choose", 3))

    def test_credit_phrases(self):
        self.assertEqual(parse_rule("Complete 9 credits from the following:"), ("credits", None, 9.0))
        self.assertEqual(parse_rule("Two credits minimum required."), ("credits", None, 2.0))

    def test_all_phrases(self):
        self.assertEqual(parse_rule("Complete both:")[0], "all")


def _row(code, codes=None, cls="", comment=0, area=0, hours=""):
    return [cls, code, codes if codes is not None else ([code] if not comment else []), "", hours, comment, area, 0]


class ProgramParserTests(unittest.TestCase):
    def setUp(self):
        self.codes = CodeIndex(["MATH 221", "MATH 222", "MATH 340", "MATH 341", "COMP SCI 300", "COMP SCI 400",
                                "COMP SCI 537", "COMP SCI 564", "COMP SCI 540"])
        self.parser = ProgramParser(self.codes, {"MATH 221": 5, "MATH 222": 4})

    def parse(self, items):
        return self.parser.parse({"href": "/undergraduate/x/test-bs/", "name": "Test, BS",
                                  "crumbs": ["Home", "UG", "College of Letters & Science", "Test"], "items": items})

    def test_all_choose_and_or_rows(self):
        program = self.parse([
            ["h", 2, "Requirements for the Major"],
            ["h", 3, "Calculus"],
            ["c", [_row("MATH 221"), _row("MATH 222"), ["listsum", "", [], "", "9", 0, 0, 0]]],
            ["h", 3, "Linear Algebra"],
            ["t", "Complete one course from the list below. Only one counts."],
            ["c", [_row("MATH 340"), _row("or MATH 341", ["MATH 341"], cls="orclass")]],
            ["h", 3, "Systems"],
            ["c", [_row("Complete two:", comment=1, area=1), _row("COMP SCI 537"), _row("COMP SCI 564"), _row("COMP SCI 540")]],
        ])
        blocks = {b["name"]: b for b in program["blocks"]}
        self.assertEqual(blocks["Calculus"]["rule"], "all")
        self.assertEqual(len(blocks["Calculus"]["slots"]), 2)
        self.assertEqual(blocks["Linear Algebra"]["slots"][0]["options"], [["MATH 340"], ["MATH 341"]])
        self.assertEqual((blocks["Systems"]["rule"], blocks["Systems"]["count"]), ("choose", 2))
        self.assertEqual(program["degree"], "BS")

    def test_sibling_emphasis_become_variants(self):
        program = self.parse([
            ["h", 2, "Requirements for the Major"],
            ["h", 3, "Latin Emphasis"], ["c", [_row("MATH 221")]],
            ["h", 3, "Greek Emphasis"], ["c", [_row("MATH 222")]],
        ])
        self.assertEqual({v["name"] for v in program["variants"]}, {"Latin Emphasis", "Greek Emphasis"})


class DesignationTests(unittest.TestCase):
    def test_tags(self):
        result = parse_designations([
            "Core GenEd - Natural Science & Wellness + Lab", "Breadth - Humanities or Social Science",
            "Comm QR - Communication B", "Level - Intermediate", "L&S Credit - L&S Liberal Arts and Science",
            "Ethnic St - Ethnic Studies", "Frgn Lang - 2nd semester language",
        ])
        self.assertTrue({"ge_nswl", "ge_nsw", "hum", "ss", "comm_b", "level_i", "las", "ethnic", "lang"} <= set(result["tags"]))
        self.assertEqual(result["breadth_choice"], ["hum", "ss"])
        self.assertEqual(result["language_level"], 2)


class ScraperTests(unittest.TestCase):
    def test_extract_program_fixture(self):
        raw = scrape_uw_guide.extract_program(FIXTURE.read_text(encoding="utf-8"), "/undergraduate/letters-science/economics/economics-bs/")
        self.assertEqual(raw["title"], "Economics, BS")
        kinds = {item[0] for item in raw["items"]}
        self.assertTrue({"h", "t", "c", "g"} <= kinds)
        self.assertTrue(raw["plan"])

    def test_extract_course_block(self):
        html = """<div class="courseblock"><p class="courseblocktitle"><strong><span class="courseblockcode">COMP&nbsp;SCI&nbsp;400</span> — PROGRAMMING III</strong></p>
        <p class="courseblockcredits">3 credits.</p><p class="courseblockdesc">Data structures.</p>
        <p class="courseblockextra"><span class="cbextra-label"><strong>Requisites: </strong></span><span class="cbextra-data"><a class="bubblelink code" title="COMP&nbsp;SCI&nbsp;300">COMP SCI 300</a> or graduate/professional standing</span></p>
        <p class="courseblockextra"><span class="cbextra-label"><strong>Course Designation: </strong></span><span class="cbextra-data">Breadth - Natural Science<br> Level - Intermediate</span></p></div>"""
        [course] = scrape_uw_guide.extract_courses(html, "/courses/comp_sci/")
        self.assertEqual(course["code"], "COMP SCI 400")
        self.assertEqual(course["title"], "PROGRAMMING III")
        self.assertEqual(course["x"]["reqCodes"], ["COMP SCI 300"])
        self.assertEqual(course["x"]["Course Designation"], ["Breadth - Natural Science", "Level - Intermediate"])


if __name__ == "__main__":
    unittest.main()
