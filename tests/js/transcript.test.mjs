// node --test tests/js
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseTranscriptText, combineMatches, mergePrior, standingFrom, fromTermCode } from "../../web/static/transcript.js";

const SAMPLE = `Test Credits
Advanced Placement Exam  MATH 221 5.00 T
Fall 2025-2026
COMP SCI 200 Programming I 3.00 A 12.00
PSYCH 202 Introduction to Psychology 4.00 W
Spring 2025-2026
COMP SCI 300 Programming II 3.00 BC 7.50   STAT 240 Data Science Modeling I 4.00 A 16.00
2026 Fall
COMP SCI 400 Programming III 3.00
Transfer Credit from Madison College
ECON 101 Principles of Microeconomics 4.00 T`;
const NOW = { season: "Fall", year: 2026 };
const CATALOG = { "MATH 221": 5, "COMP SCI 200": 3, "PSYCH 202": 4, "COMP SCI 300": 3, "STAT 240": 4, "COMP SCI 400": 3, "ECON 101": 4 };
const resolve = rows => rows.map(r => { const g = r.guesses.find(x => x in CATALOG); return g ? { code: g, title: "", credits_min: CATALOG[g] } : null; });

test("reads terms, grades, credits and two courses on one line", () => {
  const { rows } = parseTranscriptText(SAMPLE);
  const byCode = Object.fromEntries(rows.map(r => [r.guesses.find(g => g in CATALOG), r]));
  assert.deepEqual(byCode["COMP SCI 200"].term, { season: "Fall", year: 2025 });
  assert.equal(byCode["COMP SCI 300"].grade, "BC");
  assert.equal(byCode["STAT 240"].grade, "A");
  assert.deepEqual(byCode["STAT 240"].term, { season: "Spring", year: 2026 });
  assert.deepEqual(byCode["COMP SCI 400"].term, { season: "Fall", year: 2026 });
  assert.equal(byCode["MATH 221"].section, "test");
  assert.equal(byCode["ECON 101"].section, "transfer");
});

test("classifies statuses and drops terms for test and transfer credit", () => {
  const { rows } = parseTranscriptText(SAMPLE);
  const list = combineMatches(rows, resolve(rows), NOW);
  const get = code => list.find(r => r.code === code);
  assert.equal(get("COMP SCI 400").status, "in-progress");
  assert.equal(get("PSYCH 202").include, false);
  assert.equal(get("MATH 221").status, "ap");
  assert.equal(get("MATH 221").term, null);
  assert.equal(get("ECON 101").status, "transfer");
  assert.equal(get("COMP SCI 200").status, "completed");
});

test("standing uses earned credits; in-progress counts toward projected standing", () => {
  const { rows } = parseTranscriptText(SAMPLE);
  const list = combineMatches(rows, resolve(rows), NOW);
  const st = standingFrom(list);
  assert.equal(st.earned, 5 + 3 + 3 + 4 + 4);
  assert.equal(st.inProgress, 3);
  assert.equal(st.standing, "Freshman");
  assert.equal(standingFrom([{ credits: 50 }, { credits: 6, status: "in-progress" }]).projected, "Junior");
});

test("re-importing upgrades in-progress courses instead of duplicating them", () => {
  const before = [{ code: "COMP SCI 400", status: "in-progress", credits: 3, term: "Fall 2026" }];
  const merged = mergePrior(before, [{ code: "COMP SCI 400", status: "completed", credits: 3, term: "Fall 2026", grade: "A" },
    { code: "MATH 340", status: "in-progress", credits: 3, term: "Spring 2027" }]);
  assert.equal(merged.prior.length, 2);
  assert.equal(merged.updated, 1);
  assert.equal(merged.added, 1);
  assert.equal(merged.prior[0].grade, "A");
});

test("term codes", () => {
  assert.deepEqual(fromTermCode("1262"), { season: "Fall", year: 2025 });
  assert.deepEqual(fromTermCode("1274"), { season: "Spring", year: 2027 });
});
