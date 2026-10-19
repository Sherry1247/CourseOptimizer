import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildSchedules, compatiblePackages, scheduleIcs } from "../../web/static/schedule.js";

const DATA = JSON.parse(readFileSync(new URL("../fixtures/enroll/packages_1274_sample.json", import.meta.url)));
const pick = codes => codes.map(code => DATA.find(d => d.code === code));
const overlaps = picks => {
  const blocks = picks.flatMap(p => p.pkg.meetings.flatMap(m => [...m.days].map(d => ({ d, s: m.start, e: m.end }))));
  return blocks.some((a, i) => blocks.some((b, j) => i < j && a.d === b.d && a.s < b.e && b.s < a.e));
};

test("finds conflict-free timetables from real Spring 2027 sections", () => {
  const result = buildSchedules(pick(["COMP SCI 400", "COMP SCI 577", "MATH 340", "STAT 340", "COMP SCI 540"]), { openOnly: true });
  assert.ok(result.options.length > 0);
  for (const option of result.options) assert.equal(overlaps(option.picks), false);
  const scores = result.options.map(o => o.score);
  assert.deepEqual(scores, [...scores].sort((a, b) => a - b));
});

test("respects time limits and explains when nothing fits", () => {
  const result = buildSchedules(pick(["MATH 340"]), { noBefore: 600, freeDays: ["F"] });
  assert.equal(result.options.length, 0);
  assert.equal(result.blocked[0].codes[0], "MATH 340");
});

test("swap list only offers sections that still fit", () => {
  const courses = pick(["COMP SCI 577", "MATH 340"]);
  const { options } = buildSchedules(courses);
  const picks = options[0].picks;
  for (const alt of compatiblePackages(courses[0], picks)) {
    assert.equal(overlaps([{ pkg: alt }, picks.find(p => p.code === "MATH 340")]), false);
  }
});

test("calendar export repeats weekly until the last day of classes", () => {
  const { options } = buildSchedules(pick(["COMP SCI 400"]));
  const ics = scheduleIcs(options[0].picks, { classes_begin: "2027-01-19", classes_end: "2027-04-30" });
  assert.match(ics, /RRULE:FREQ=WEEKLY;BYDAY=[A-Z,]+;UNTIL=20270501T055959Z/);
  assert.match(ics, /SUMMARY:COMP SCI 400 final exam/);
});
