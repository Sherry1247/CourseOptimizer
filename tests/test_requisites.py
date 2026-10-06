import unittest

import helpers  # noqa: F401  (sets sys.path)
from ingest.codes import CodeIndex, term_code_to_label
from requisites import cheapest_path, coreqs_in, courses_in, describe, evaluate, parse_requisite

CODES = CodeIndex([
    "MATH 211", "MATH 213", "MATH 221", "MATH 222", "MATH 112", "MATH 113", "MATH 114",
    "ECON 101", "ECON 111", "ECON 205", "ECON 311", "A A E 101", "STAT 240",
    "COMP SCI 300", "COMP SCI 302", "E C E/COMP SCI 252", "COMP SCI/MATH 240",
    "GEN BUS 360", "GEN BUS 400", "M H R 300", "OTM 300", "ECON/FINANCE 300", "MARKETNG 300",
    "MUSIC 121", "MUSIC 171", "MUSIC 172", "SPANISH 204", "SPANISH 311", "ESL 118",
])


class CodeIndexTests(unittest.TestCase):
    def test_cross_listed_aliases(self):
        self.assertEqual(CODES.resolve("MATH 240"), "COMP SCI/MATH 240")
        self.assertEqual(CODES.resolve("COMPSCI 240"), "COMP SCI/MATH 240")
        self.assertEqual(CODES.resolve("ECE 252"), "E C E/COMP SCI 252")
        self.assertEqual(CODES.resolve_ref(["COMPSCI", "ECE"], 252), "E C E/COMP SCI 252")

    def test_term_codes(self):
        self.assertEqual(term_code_to_label("1262"), ("Fall", 2025))
        self.assertEqual(term_code_to_label("1264"), ("Spring", 2026))
        self.assertEqual(term_code_to_label("1266"), ("Summer", 2026))


class ParseTests(unittest.TestCase):
    def test_shorthand_numbers_inherit_subject(self):
        tree = parse_requisite("(MATH 211, 213, or 221) and STAT 240", CODES)["tree"]
        self.assertEqual(describe(tree), "(MATH 211 or MATH 213 or MATH 221) and STAT 240")

    def test_retired_course_stays_a_course_leaf(self):
        tree = parse_requisite("MATH 217 or 221. MATH 211 or 213 does not fulfill the requisite.", CODES)["tree"]
        self.assertEqual(courses_in(tree), {"MATH 217", "MATH 221"})

    def test_historical_note_is_not_a_requirement(self):
        tree = parse_requisite("A A E 101 (215 prior to Fall 2024), ECON 101, or 111", CODES)["tree"]
        self.assertEqual(describe(tree), "A A E 101 or ECON 101 or ECON 111")

    def test_not_open_clause_mid_sentence(self):
        result = parse_requisite(
            "GEN BUS 360 and (M H R 300, OTM 300, FINANCE/ECON 300, and MARKETNG 300, or concurrent enrollment); "
            "not open to students with credit for GEN BUS 400", CODES)
        self.assertEqual(result["exclusions"], ["GEN BUS 400"])
        self.assertIn("GEN BUS 360", courses_in(result["tree"]))
        self.assertTrue(result["concurrent"])

    def test_corequisite_leaf(self):
        tree = parse_requisite("MUSIC 121 and 171 and concurrent enrollment in MUSIC 172", CODES)["tree"]
        self.assertEqual(coreqs_in(tree), {"MUSIC 172"})
        self.assertFalse(evaluate(tree, lambda c: c in {"MUSIC 121", "MUSIC 171"}))
        self.assertTrue(evaluate(tree, lambda c: c in {"MUSIC 121", "MUSIC 171"}, coreq_ok=lambda c: c == "MUSIC 172"))

    def test_esl_gate_is_ignored(self):
        result = parse_requisite("Students required to take the MSN ESLAT cannot enroll until the ESL 118 requirement is satisfied", CODES)
        self.assertIsNone(result["tree"])


class EvaluateTests(unittest.TestCase):
    def test_graduate_standing_never_blocks_or_satisfies(self):
        tree = parse_requisite("E C E/COMP SCI 252 and (COMP SCI 300 or 302) or graduate/professional standing", CODES)["tree"]
        self.assertFalse(evaluate(tree, lambda c: c == "E C E/COMP SCI 252"))
        self.assertTrue(evaluate(tree, lambda c: c in {"E C E/COMP SCI 252", "COMP SCI 300"}))

    def test_placement_callable(self):
        tree = parse_requisite("MATH 114 or (MATH 112 and 113) or placement into MATH 221", CODES)["tree"]
        self.assertTrue(evaluate(tree, lambda c: False, assume_placement=lambda code: code == "MATH 221"))
        self.assertFalse(evaluate(tree, lambda c: False, assume_placement=False))

    def test_standing_uses_credits(self):
        tree = {"standing": "junior"}
        self.assertFalse(evaluate(tree, lambda c: False, credits_earned=40))
        self.assertTrue(evaluate(tree, lambda c: False, credits_earned=60))

    def test_cheapest_path_skips_non_course_routes(self):
        tree = {"op": "or", "args": [{"course": "MATH 222"}, {"op": "and", "args": [
            {"cond": "other", "text": "Visiting International"}, {"cond": "declared", "text": "Pre-Masters"}]}]}
        cost, chosen = cheapest_path(tree, lambda c: 1.0, lambda c: False)
        self.assertEqual(chosen, ["MATH 222"])

    def test_cheapest_path_prefers_satisfied_branch(self):
        tree = parse_requisite("SPANISH 204 or SPANISH 311", CODES)["tree"]
        cost, chosen = cheapest_path(tree, lambda c: 1.0, lambda c: c == "SPANISH 311")
        self.assertEqual((cost, chosen), (0.0, []))


if __name__ == "__main__":
    unittest.main()
