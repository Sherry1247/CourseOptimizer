// Transcript reader that runs in the browser. Grades and names never leave the
// page: only short course-code guesses are sent to /api/catalog/resolve.

const SEASONS = ["Spring", "Summer", "Fall"];
const SEASON_ORDER = { Spring: 0, Summer: 1, Fall: 2 };
const PASSING = new Set(["A", "AB", "B", "BC", "C", "D", "S", "CR", "P", "T"]);
const NO_CREDIT = new Set(["F", "U", "W", "DR", "NR", "I", "IN", "NW", "N", "Q", "X", "AU", "AUD"]);
const GRADES = new Set([...PASSING, ...NO_CREDIT]);
const IN_PROGRESS = /\b(IP|IN PROGRESS|ENROLLED|CURRENTLY ENROLLED|NOT YET GRADED|PENDING)\b/;
const TERM_PATTERNS = [
  // "Fall 2025-2026" (Student Center course history): Fall is the first year, Spring/Summer the second.
  { re: /\b(FALL|SPRING|SUMMER)\s+(20\d\d)\s*[-–]\s*(20\d\d)\b/, read: m => termOf(m[1], m[1] === "FALL" ? +m[2] : +m[3]) },
  { re: /\b(FALL|SPRING|SUMMER)\s+(?:TERM\s+|SEMESTER\s+)?(20\d\d)\b/, read: m => termOf(m[1], +m[2]) },
  { re: /\b(20\d\d)\s+(FALL|SPRING|SPRNG|SUMMER|SUMMR)\b/, read: m => termOf(m[2], +m[1]) },
  { re: /\b(FA|SP|SU)\s?'?(\d\d)\b/, read: m => termOf({ FA: "FALL", SP: "SPRING", SU: "SUMMER" }[m[1]], 2000 + +m[2]) },
  // UW term codes, e.g. 1262 = Fall 2025, 1264 = Spring 2026.
  { re: /\bTERM\s*:?\s*(1\d{2}[246])\b/, read: m => fromTermCode(m[1]) },
];

function termOf(word, year) {
  const w = word.toUpperCase();
  const season = w.startsWith("FA") ? "Fall" : w.startsWith("SP") ? "Spring" : "Summer";
  return year >= 1990 && year <= 2100 ? { season, year } : null;
}

export function fromTermCode(code) {
  const season = { 2: "Fall", 4: "Spring", 6: "Summer" }[code[3]];
  const academicYear = 2000 + Number(code.slice(1, 3));
  return season ? { season, year: season === "Fall" ? academicYear - 1 : academicYear } : null;
}

export function termKey(t) { return t ? t.year * 3 + SEASON_ORDER[t.season] : -1; }
export function termLabel(t) { return t ? `${t.season} ${t.year}` : ""; }
export function parseTermLabel(label) {
  const m = /^(Fall|Spring|Summer) (\d{4})$/.exec(label || "");
  return m ? { season: m[1], year: Number(m[2]) } : null;
}

/** The term whose classes are running or about to run on `today`. */
export function currentTerm(today = new Date()) {
  const m = today.getMonth() + 1, y = today.getFullYear();
  if (m >= 9) return { season: "Fall", year: y };
  if (m >= 6) return { season: "Summer", year: y };
  return { season: "Spring", year: y };
}

function normalize(text) {
  return text.normalize("NFKC").replace(/ /g, " ").toUpperCase();
}

/** Split one line into course segments: each starts at "<SUBJECT WORDS> <3-digit number>". */
function courseSegments(line) {
  const tokens = line.match(/[A-Z][A-Z&\-]*|\d+(?:\.\d+)?[A-Z]?|[^\sA-Z\d]+/g) || [];
  const segments = [];
  for (let i = 0; i < tokens.length; i++) {
    if (!/^\d{3}[A-Z]?$/.test(tokens[i])) continue;
    const words = [];
    for (let j = i - 1; j >= 0 && words.length < 4; j--) {
      if (/^[A-Z][A-Z&\-]*$/.test(tokens[j]) || tokens[j] === "/") words.unshift(tokens[j]);
      else break;
    }
    if (!words.length || words.every(w => w === "/")) continue;
    const subject = words.filter(w => w !== "/");
    const guesses = [];
    for (let width = Math.min(4, subject.length); width >= 1; width--) guesses.push(`${subject.slice(-width).join(" ")} ${tokens[i]}`);
    segments.push({ start: i, guesses, number: tokens[i] });
  }
  return { tokens, segments };
}

function readSegment(tokens, from, to) {
  const tail = tokens.slice(from + 1, to);
  let grade = null, credits = null;
  const numbers = [];
  tail.forEach((tok, k) => {
    if (/^\d+(\.\d+)?$/.test(tok)) numbers.push({ value: Number(tok), k, decimal: tok.includes(".") });
  });
  // Credits: the first decimal number between 0.5 and 12, else the first small integer after the title.
  const credit = numbers.find(n => n.decimal && n.value >= 0.5 && n.value <= 12) || numbers.find(n => n.value >= 1 && n.value <= 6 && n.k > 0);
  if (credit) credits = credit.value;
  // Grade: a grade token that sits next to the numbers (title words come first).
  const gradeIdx = tail.map((t, k) => (GRADES.has(t) ? k : -1)).filter(k => k >= 0);
  const nearNumber = gradeIdx.filter(k => numbers.some(n => Math.abs(n.k - k) <= 2));
  const pick = nearNumber.length ? nearNumber[nearNumber.length - 1] : (gradeIdx.length && gradeIdx[gradeIdx.length - 1] === tail.length - 1 ? gradeIdx[gradeIdx.length - 1] : -1);
  if (pick >= 0) grade = tail[pick];
  return { grade, credits };
}

/**
 * Read transcript text line by line.
 * Returns rows {line, term, section, guesses, grade, credits, inProgressMarker}.
 */
export function parseTranscriptText(text) {
  const rows = [];
  const unmatched = [];
  let term = null, section = "uw";
  for (const raw of String(text).split(/\r?\n/)) {
    const line = normalize(raw).replace(/\s+/g, " ").trim();
    if (!line) continue;
    for (const p of TERM_PATTERNS) {
      const m = p.re.exec(line);
      if (m) { const t = p.read(m); if (t) { term = t; section = "uw"; } break; }
    }
    if (/\bTRANSFER(RED)?\b|\bCREDIT FROM\b|\bOTHER INSTITUTION/.test(line)) section = "transfer";
    if (/\b(TEST CREDITS?|ADVANCED PLACEMENT|AP EXAM|AP CREDIT|INTERNATIONAL BACCALAUREATE|IB EXAM|CLEP|RETRO|PLACEMENT CREDIT)\b/.test(line)) section = "test";
    const { tokens, segments } = courseSegments(line);
    if (!segments.length) { if (/\d{3}/.test(line) && unmatched.length < 30) unmatched.push(raw.trim().slice(0, 200)); continue; }
    segments.forEach((seg, n) => {
      const following = segments[n + 1];
      const next = following ? following.start - (following.guesses[0].split(" ").length - 1) : tokens.length;
      const { grade, credits } = readSegment(tokens, seg.start, next);
      rows.push({ line: raw.trim().slice(0, 200), term, section, guesses: seg.guesses, grade, credits,
        inProgressMarker: IN_PROGRESS.test(line) });
    });
  }
  return { rows, unmatched };
}

/** Decide each matched row's status. `now` is the current term {season, year}. */
export function classify(row, now) {
  const termIsCurrentOrLater = row.term && termKey(row.term) >= termKey(now);
  if (row.section === "test") return { status: "ap", include: true, note: "Test credit (AP, IB, placement)" };
  if (row.section === "transfer" || row.grade === "T") return { status: "transfer", include: true, note: "Transfer credit" };
  if (row.grade && PASSING.has(row.grade)) return { status: "completed", include: true, note: `Grade ${row.grade}` };
  if (row.grade && NO_CREDIT.has(row.grade)) return { status: "completed", include: false, note: `No credit earned (${row.grade})` };
  if (row.inProgressMarker || termIsCurrentOrLater) return { status: "in-progress", include: true, note: "In progress" };
  return { status: "completed", include: true, note: "No grade found, check this row", review: true };
}

/**
 * Combine parsed rows with catalog matches (same order as rows).
 * Repeated courses keep the latest attempt that earned credit.
 */
export function combineMatches(rows, matches, now) {
  const byCode = new Map();
  rows.forEach((row, i) => {
    const hit = matches[i];
    if (!hit) return;
    const verdict = classify(row, now);
    const credits = row.credits ?? hit.credits_min ?? hit.credits_max ?? 3;
    const atUW = verdict.status === "completed" || verdict.status === "in-progress";
    const entry = { code: hit.code, title: hit.title, credits, catalogCredits: hit.credits_min, term: atUW && row.term ? termLabel(row.term) : null,
      grade: row.grade, evidence: row.line, ...verdict };
    const prev = byCode.get(hit.code);
    const better = !prev
      || (entry.include && !prev.include)
      || (entry.include === prev.include && termKey(parseTermLabel(entry.term)) > termKey(parseTermLabel(prev.term)));
    if (better) byCode.set(hit.code, { ...entry, attempts: (prev?.attempts || 1) + (prev ? 1 : 0) });
    else prev.attempts = (prev.attempts || 1) + 1;
  });
  return [...byCode.values()].sort((a, b) => termKey(parseTermLabel(a.term)) - termKey(parseTermLabel(b.term)) || a.code.localeCompare(b.code));
}

/** Merge imported rows into existing prior credit. Returns {prior, added, updated, unchanged}. */
export function mergePrior(existing, imported) {
  const prior = existing.map(p => ({ ...p }));
  let added = 0, updated = 0, unchanged = 0;
  for (const row of imported) {
    const item = { code: row.code, status: row.status, credits: row.credits, term: row.term || null, grade: row.grade || null, source: "transcript" };
    const i = prior.findIndex(p => p.code === row.code);
    if (i < 0) { prior.push(item); added++; continue; }
    const old = prior[i];
    const changed = old.status !== item.status || (item.term && old.term !== item.term) || (item.grade && old.grade !== item.grade);
    if (changed) { prior[i] = { ...old, ...item }; updated++; } else unchanged++;
  }
  return { prior, added, updated, unchanged };
}

/** Earned and projected credits, plus class standing from L&S thresholds. */
export function standingFrom(prior, genericCredits = 0, thresholds = { Sophomore: 24, Junior: 54, Senior: 86 }) {
  let earned = Number(genericCredits || 0), inProgress = 0;
  for (const p of prior) {
    const c = Number(p.credits || 0);
    if (p.status === "in-progress") inProgress += c;
    else if (p.include !== false) earned += c;
  }
  const level = credits => (credits >= thresholds.Senior ? "Senior" : credits >= thresholds.Junior ? "Junior" : credits >= thresholds.Sophomore ? "Sophomore" : "Freshman");
  return { earned, inProgress, standing: level(earned), projected: level(earned + inProgress) };
}

// ------------------------------------------------------------------ PDF text
let pdfjs = null;
async function loadPdfjs() {
  if (!pdfjs) {
    pdfjs = await import("/static/vendor/pdfjs/pdf.min.mjs");
    pdfjs.GlobalWorkerOptions.workerSrc = "/static/vendor/pdfjs/pdf.worker.min.mjs";
  }
  return pdfjs;
}

/** Text of a PDF in reading order; two-column pages are read left column first. */
export async function pdfText(arrayBuffer) {
  const lib = await loadPdfjs();
  const doc = await lib.getDocument({ data: arrayBuffer, isEvalSupported: false }).promise;
  const out = [];
  for (let n = 1; n <= doc.numPages; n++) {
    const page = await doc.getPage(n);
    const width = page.getViewport({ scale: 1 }).width;
    const items = (await page.getTextContent()).items.filter(it => it.str && it.str.trim());
    // Two-column transcripts put course codes at the start of both halves of the page.
    // A wide one-column table has credits and grades on the right, but no codes there.
    const codeStart = it => /^[A-Z][A-Z&/ -]{1,20}\s\d{3}\b/.test(it.str.trim().toUpperCase());
    const rightCodes = items.filter(it => codeStart(it) && it.transform[4] > width * 0.42);
    const leftCodes = items.filter(it => codeStart(it) && it.transform[4] < width * 0.3);
    const split = rightCodes.length >= 3 && leftCodes.length >= 3 ? Math.min(...rightCodes.map(it => it.transform[4])) - 4 : null;
    const columns = split ? [items.filter(it => it.transform[4] < split), items.filter(it => it.transform[4] >= split)] : [items];
    for (const col of columns) {
      const lines = new Map();
      for (const it of col) {
        const y = Math.round(it.transform[5] / 3) * 3;
        if (!lines.has(y)) lines.set(y, []);
        lines.get(y).push(it);
      }
      [...lines.entries()].sort((a, b) => b[0] - a[0]).forEach(([, parts]) => {
        out.push(parts.sort((a, b) => a.transform[4] - b.transform[4]).map(p => p.str).join(" "));
      });
    }
  }
  return out.join("\n");
}

export const _internals = { courseSegments, readSegment, SEASONS };
