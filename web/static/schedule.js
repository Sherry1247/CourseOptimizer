// Weekly timetable builder for one term: picks one enrollment package per
// course (a lecture with its discussion or lab) so that no meetings overlap.
// Plain functions with no DOM access, so they can be tested in Node.

const DAY_LETTERS = ["M", "T", "W", "R", "F", "S", "U"];
export const DAY_NAMES = { M: "Mon", T: "Tue", W: "Wed", R: "Thu", F: "Fri", S: "Sat", U: "Sun" };

export function meetingDays(days) {
  return [...String(days || "")].filter(d => DAY_LETTERS.includes(d));
}

export function fmtTime(min) {
  if (min == null) return "";
  const h = Math.floor(min / 60), m = min % 60;
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")}${h < 12 ? "a" : "p"}`;
}

function blocks(pkg) {
  const out = [];
  for (const m of pkg.meetings || []) {
    if (m.start == null || m.end == null) continue;
    for (const d of meetingDays(m.days)) out.push({ d, s: m.start, e: m.end });
  }
  return out;
}

function clash(a, b) {
  for (const x of a) for (const y of b) if (x.d === y.d && x.s < y.e && y.s < x.e) return true;
  return false;
}

function allowed(pkg, prefs) {
  if (prefs.openOnly && pkg.status && pkg.status !== "OPEN" && pkg.status !== "WAITLISTED") return false;
  const b = blocks(pkg);
  if (prefs.noBefore != null && b.some(x => x.s < prefs.noBefore)) return false;
  if (prefs.noAfter != null && b.some(x => x.e > prefs.noAfter)) return false;
  if (prefs.freeDays?.length && b.some(x => prefs.freeDays.includes(x.d))) return false;
  return true;
}

function stats(picks) {
  const byDay = {};
  for (const p of picks) for (const b of blocks(p.pkg)) (byDay[b.d] ||= []).push(b);
  let gaps = 0, earliest = Infinity, latest = 0;
  for (const list of Object.values(byDay)) {
    list.sort((a, b) => a.s - b.s);
    for (let i = 1; i < list.length; i++) gaps += Math.max(0, list[i].s - list[i - 1].e - 10);
    earliest = Math.min(earliest, list[0].s);
    latest = Math.max(latest, ...list.map(x => x.e));
  }
  const days = Object.keys(byDay);
  return { days: DAY_LETTERS.filter(d => days.includes(d)), gaps, earliest: earliest === Infinity ? null : earliest, latest: latest || null };
}

function score(picks, prefs) {
  const s = stats(picks);
  let total = s.gaps / 6 + s.days.length * (prefs.compact ? 40 : 12);
  for (const p of picks) {
    for (const b of blocks(p.pkg)) {
      if (b.s < 540) total += 18;          // before 9:00
      if (b.e > 1050) total += 8;          // after 5:30
    }
    if (p.pkg.status === "CLOSED") total += 400;
    else if (p.pkg.status === "WAITLISTED") total += 120;
    if (prefs.instructorGpa && p.instructorGpa) total -= (p.instructorGpa - 3) * 20;
  }
  return Math.round(total);
}

/**
 * courses: [{code, packages:[...]}]; prefs: {openOnly, noBefore, noAfter, freeDays, compact, max}
 * Returns {options, blocked, missing} where blocked explains why nothing fits.
 */
export function buildSchedules(courses, prefs = {}) {
  const max = prefs.max || 6;
  const usable = courses.filter(c => c.packages?.length);
  const missing = courses.filter(c => !c.packages?.length).map(c => c.code);
  const choices = usable.map(c => ({ code: c.code, list: c.packages.filter(p => allowed(p, prefs)).map(pkg => ({ pkg, b: blocks(pkg) })) }));
  const empty = choices.filter(c => !c.list.length);
  if (empty.length) {
    return { options: [], missing, blocked: empty.map(c => ({ codes: [c.code], reason: prefs.openOnly ? "every section is full or outside your time limits" : "no section fits your time limits" })) };
  }
  choices.sort((a, b) => a.list.length - b.list.length);
  const found = [];
  let visited = 0;
  const stack = [];
  (function dfs(i) {
    if (visited++ > 60000 || found.length > 600) return;
    if (i === choices.length) { const picks = stack.map((p, k) => ({ code: choices[k].code, pkg: p.pkg })); found.push({ picks, score: score(picks, prefs) }); return; }
    for (const option of choices[i].list) {
      if (stack.some(p => clash(p.b, option.b))) continue;
      stack.push(option);
      dfs(i + 1);
      stack.pop();
    }
  })(0);
  if (!found.length) return { options: [], missing, blocked: explainConflicts(choices) };
  found.sort((a, b) => a.score - b.score);
  const seen = new Set();
  const options = [];
  for (const f of found) {
    const key = f.picks.map(p => p.pkg.classNumber).join("-");
    if (seen.has(key)) continue;
    seen.add(key);
    options.push({ ...f, stats: stats(f.picks) });
    if (options.length >= max) break;
  }
  return { options, missing, blocked: [] };
}

function explainConflicts(choices) {
  const out = [];
  for (let i = 0; i < choices.length; i++) for (let j = i + 1; j < choices.length; j++) {
    const always = choices[i].list.every(a => choices[j].list.every(b => clash(a.b, b.b)));
    if (always) out.push({ codes: [choices[i].code, choices[j].code], reason: "always overlap" });
  }
  return out.length ? out : [{ codes: choices.map(c => c.code), reason: "cannot all fit together; try removing one course or relaxing your limits" }];
}

/** Packages of one course that fit around the other picks (for "swap section"). */
export function compatiblePackages(course, picks, prefs = {}) {
  const others = picks.filter(p => p.code !== course.code).flatMap(p => blocks(p.pkg));
  return (course.packages || []).filter(p => allowed(p, prefs) && !clash(blocks(p), others));
}

// ------------------------------------------------------------------ calendar export
const ICS_DAY = { M: "MO", T: "TU", W: "WE", R: "TH", F: "FR", S: "SA", U: "SU" };
const JS_DAY = { M: 1, T: 2, W: 3, R: 4, F: 5, S: 6, U: 0 };

function icsDate(isoDate, minutes) {
  const [y, m, d] = isoDate.split("-");
  const h = String(Math.floor(minutes / 60)).padStart(2, "0"), mi = String(minutes % 60).padStart(2, "0");
  return `${y}${m}${d}T${h}${mi}00`;
}

function firstOnOrAfter(isoDate, letters) {
  const date = new Date(`${isoDate}T12:00:00`);
  for (let k = 0; k < 7; k++) {
    if (letters.some(l => JS_DAY[l] === date.getDay())) return date.toISOString().slice(0, 10);
    date.setDate(date.getDate() + 1);
  }
  return isoDate;
}

function esc(text) { return String(text || "").replace(/[\\;,]/g, m => `\\${m}`).replace(/\n/g, "\\n"); }

const VTIMEZONE = [
  "BEGIN:VTIMEZONE", "TZID:America/Chicago",
  "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0600", "TZOFFSETTO:-0500", "TZNAME:CDT", "DTSTART:19700308T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
  "BEGIN:STANDARD", "TZOFFSETFROM:-0500", "TZOFFSETTO:-0600", "TZNAME:CST", "DTSTART:19701101T020000", "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD",
  "END:VTIMEZONE",
];

/** picks: [{code, title, pkg}], term: {name, classes_begin, classes_end}, extra: [{date, title, detail}] */
export function scheduleIcs(picks, term, extra = []) {
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//BadgerPlan//Schedule//EN", "CALSCALE:GREGORIAN", ...VTIMEZONE];
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
  let n = 0;
  for (const p of picks) {
    for (const m of p.pkg.meetings || []) {
      const letters = meetingDays(m.days);
      if (!letters.length || m.start == null || !term.classes_begin) continue;
      const first = firstOnOrAfter(term.classes_begin, letters);
      const end = new Date(`${term.classes_end}T12:00:00Z`);
      end.setUTCDate(end.getUTCDate() + 1);
      const until = end.toISOString().slice(0, 10).replace(/-/g, "") + "T055959Z";  // end of the last class day, Madison time
      const kinds = (p.pkg.sections || []).map(s => s.type).join("/");
      lines.push("BEGIN:VEVENT", `UID:bp-${p.pkg.classNumber}-${n++}@badgerplan`, `DTSTAMP:${stamp}`,
        `DTSTART;TZID=America/Chicago:${icsDate(first, m.start)}`, `DTEND;TZID=America/Chicago:${icsDate(first, m.end)}`,
        `RRULE:FREQ=WEEKLY;BYDAY=${letters.map(l => ICS_DAY[l]).join(",")};UNTIL=${until}`,
        `SUMMARY:${esc(`${p.code} ${kinds}`)}`, `LOCATION:${esc([m.room, m.building].filter(Boolean).join(" "))}`,
        `DESCRIPTION:${esc(`${p.title || ""}\nClass number ${p.pkg.classNumber}`)}`, "END:VEVENT");
    }
    for (const exam of p.pkg.exams || []) {
      if (!exam.date || exam.start == null) continue;
      const day = new Date(exam.date).toLocaleDateString("en-CA", { timeZone: "America/Chicago" });
      lines.push("BEGIN:VEVENT", `UID:bp-exam-${p.pkg.classNumber}-${n++}@badgerplan`, `DTSTAMP:${stamp}`,
        `DTSTART;TZID=America/Chicago:${icsDate(day, exam.start)}`, `DTEND;TZID=America/Chicago:${icsDate(day, exam.end ?? exam.start + 120)}`,
        `SUMMARY:${esc(`${p.code} final exam`)}`, "END:VEVENT");
    }
  }
  lines.push(...deadlineEvents(extra, stamp));
  lines.push("END:VCALENDAR");
  return lines.join("\r\n");
}

/** All-day events for deadlines: [{date, end?, title, detail}] */
export function deadlineEvents(events, stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z") {
  const lines = [];
  events.forEach((e, k) => {
    const start = e.date.replace(/-/g, "");
    const endDate = new Date(`${e.end || e.date}T12:00:00`);
    endDate.setDate(endDate.getDate() + 1);
    lines.push("BEGIN:VEVENT", `UID:bp-date-${start}-${k}@badgerplan`, `DTSTAMP:${stamp}`, `DTSTART;VALUE=DATE:${start}`,
      `DTEND;VALUE=DATE:${endDate.toISOString().slice(0, 10).replace(/-/g, "")}`, `SUMMARY:${esc(e.title)}`,
      `DESCRIPTION:${esc(e.detail || "")}`, "END:VEVENT");
  });
  return lines;
}

export function deadlinesIcs(events) {
  return ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//BadgerPlan//Dates//EN", ...deadlineEvents(events), "END:VCALENDAR"].join("\r\n");
}
