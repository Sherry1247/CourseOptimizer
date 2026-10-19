// BadgerPlan front end — vanilla ES module, no build step.
import * as TX from "/static/transcript.js";
import * as SCH from "/static/schedule.js";
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (v = "") => String(v).replace(/[&<>'"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c]));
const enc = encodeURIComponent;
const SEASONS = { Spring: 0, Summer: 1, Fall: 2 };
const THIS_YEAR = new Date().getFullYear();
// The next fall that has not started yet: the default first term for a new student.
const NEXT_FALL = new Date().getMonth() >= 8 ? THIS_YEAR + 1 : THIS_YEAR;
const STANDINGS = ["Freshman", "Sophomore", "Junior", "Senior"];
const STANDING_CREDITS = { Freshman: 0, Sophomore: 24, Junior: 54, Senior: 86 };
const STORE_KEY = "badgerplan:v2";

const state = {
  meta: null,
  programs: [],
  programCache: new Map(),
  courseCache: new Map(),
  settings: defaultSettings(),
  plan: null,          // {terms:[{id,season,year,label,courses:[card]}], unscheduled:[card]}
  validation: null,
  planId: null,
  dirty: false,
  transcriptMatches: [],
};

function defaultSettings() {
  return {
    studentType: "first-year",
    yearInSchool: "incoming",
    startSeason: "Fall", startYear: NEXT_FALL,
    gradSeason: "Spring", gradYear: NEXT_FALL + 4,
    firstCollegeSeason: "Fall", firstCollegeYear: THIS_YEAR - 1,
    majors: [],               // [{id, variants:{group:name}}]
    prior: [],                // [{code, status, credits, term?, grade?, source?}]
    genericCredits: 0,
    mathPlacement: "calculus",
    priority: "balanced",
    targetCredits: 15, maxCredits: 17,
    includeSummer: false,
    placeCommA: false, placeQrA: false,
    manualDone: [],
  };
}

// ------------------------------------------------------------------ api
async function api(path, options = {}) {
  const init = { headers: { "Content-Type": "application/json" }, ...options };
  if (init.body && typeof init.body !== "string") init.body = JSON.stringify(init.body);
  const response = await fetch(path, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

async function program(id) {
  if (!state.programCache.has(id)) state.programCache.set(id, await api(`/api/programs/${enc(id)}`));
  return state.programCache.get(id);
}

async function course(code) {
  if (!state.courseCache.has(code)) state.courseCache.set(code, await api(`/api/courses/${enc(code)}`));
  return state.courseCache.get(code);
}

// ------------------------------------------------------------------ boot
document.addEventListener("DOMContentLoaded", init);

// ------------------------------------------------------------------ setup form
function buildYearSelects() {
  const fill = (select, from, to) => { for (let y = from; y <= to; y++) select.add(new Option(y, y)); };
  fill($("#startYear"), THIS_YEAR - 4, THIS_YEAR + 3);
  fill($("#gradYear"), THIS_YEAR, THIS_YEAR + 9);
  fill($("#firstCollegeYear"), THIS_YEAR - 8, THIS_YEAR + 2);
}

function bindSetup() {
  $$("#setupForm .seg[data-student]").forEach(btn => btn.addEventListener("click", () => {
    state.settings.studentType = btn.dataset.student;
    renderSetup();
    markDirty();
  }));
  const fields = ["startSeason", "startYear", "gradSeason", "gradYear", "firstCollegeSeason", "firstCollegeYear",
    "mathPlacement", "priority", "targetCredits", "maxCredits", "genericCredits"];
  fields.forEach(id => $(`#${id}`).addEventListener("change", e => {
    const value = e.target.type === "number" || id.endsWith("Year") ? Number(e.target.value) : e.target.value;
    state.settings[id] = value;
    updateTimelineHint();
    markDirty();
    if (state.plan && ["targetCredits", "maxCredits", "genericCredits", "mathPlacement"].includes(id)) validateSoon();
  }));
  ["includeSummer", "placeCommA", "placeQrA"].forEach(id => $(`#${id}`).addEventListener("change", e => {
    state.settings[id] = e.target.checked;
    markDirty();
    if (state.plan && id !== "includeSummer") validateSoon();
  }));
  $("#yearInSchool").addEventListener("change", e => setYearInSchool(e.target.value));
  $("#addMajor").addEventListener("click", () => addMajorRow());
  $("#setupForm").addEventListener("submit", e => { e.preventDefault(); generate(); });
  bindPriorSearch();
}

function renderSetup() {
  const s = state.settings;
  $("#yearInSchool").value = s.yearInSchool || "incoming";
  $$("#setupForm .seg[data-student]").forEach(btn => {
    const on = btn.dataset.student === s.studentType;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-checked", on);
  });
  const transfer = s.studentType === "transfer";
  $$(".transfer-only").forEach(el => el.classList.toggle("hidden", !transfer));
  $("#priorTitle").textContent = transfer ? "Transfer credit" : "Credit you already have";
  $("#priorHint").textContent = transfer
    ? "Add courses as their UW equivalents (check Transferology / your credit evaluation). Unmatched credit goes in the box below."
    : "AP/IB, placement or dual-enrollment credit that maps to a UW course.";
  for (const id of ["startSeason", "startYear", "gradSeason", "gradYear", "firstCollegeSeason", "firstCollegeYear",
    "mathPlacement", "priority", "targetCredits", "maxCredits", "genericCredits"]) $(`#${id}`).value = s[id];
  $("#includeSummer").checked = s.includeSummer;
  $("#placeCommA").checked = s.placeCommA;
  $("#placeQrA").checked = s.placeQrA;
  renderMajors();
  renderPriorChips();
  updateTimelineHint();
}

function updateTimelineHint() {
  const s = state.settings, w = planWindow();
  const start = w.start.year * 3 + SEASONS[w.start.season];
  const end = s.gradYear * 3 + SEASONS[s.gradSeason];
  if (end <= start) { $("#timelineHint").textContent = `Graduation must be after ${TX.termLabel(w.start)}.`; renderStanding(); return; }
  let regular = 0;
  let season = w.start.season, year = w.start.year;
  for (let guard = 0; guard < 40; guard++) {
    if (season !== "Summer") regular++;
    if (year * 3 + SEASONS[season] >= end) break;
    if (season === "Fall") { season = "Spring"; year++; } else if (season === "Spring") season = "Summer"; else season = "Fall";
  }
  const from = w.current ? `planning from ${TX.termLabel(w.start)}` : `${s.startSeason} ${s.startYear}`;
  $("#timelineHint").textContent = `${regular} fall/spring term${regular === 1 ? "" : "s"} · ${from} → ${s.gradSeason} ${s.gradYear}`;
  $("#compactPlanDates").textContent = `${TX.termLabel(w.start)} → ${s.gradSeason} ${s.gradYear} · ${regular} terms`;
  renderStanding();
}

// ------------------------------------------------------------------ where the student is now
// Terms before the upcoming one are history (from the transcript); the plan covers the rest.
function nextRegularTerm(t) {
  return t.season === "Fall" ? { season: "Spring", year: t.year + 1 } : { season: "Fall", year: t.year };
}
function upcomingTerm() {
  const now = TX.currentTerm();
  return now.season === "Summer" ? { season: "Fall", year: now.year } : nextRegularTerm(now);
}
function planWindow() {
  const s = state.settings;
  const start = { season: s.startSeason, year: s.startYear };
  const now = TX.currentTerm();
  const history = s.prior.filter(p => p.term).map(p => TX.parseTermLabel(p.term)).filter(Boolean);
  const current = TX.termKey(start) <= TX.termKey(now) || history.length > 0;
  if (!current) return { start, current: false, history: [], assumedCredits: 0 };
  let first = upcomingTerm();
  const latest = history.reduce((m, t) => (TX.termKey(t) > TX.termKey(m) ? t : m), history[0] || start);
  if (history.length && TX.termKey(latest) >= TX.termKey(first)) first = nextRegularTerm(latest);
  if (TX.termKey(first) < TX.termKey(start)) first = start;
  const transcriptCredits = TX.standingFrom(s.prior.filter(p => p.term || p.source === "transcript")).earned;
  const assumed = !history.length && s.yearInSchool !== "incoming" ? STANDING_CREDITS[s.yearInSchool] || 0 : 0;
  return { start: first, current: true, history, assumedCredits: transcriptCredits ? 0 : assumed };
}
function standingInfo() {
  const s = state.settings;
  const counted = s.prior.map(p => ({ ...p, include: true }));
  const st = TX.standingFrom(counted, s.genericCredits);
  const fromTranscript = s.prior.some(p => p.source === "transcript" || p.term);
  return { ...st, fromTranscript, chosen: s.yearInSchool || "incoming" };
}
function renderStanding() {
  const info = standingInfo(), w = planWindow(), s = state.settings, hint = $("#standingHint");
  if (!hint) return;
  if (info.fromTranscript) {
    hint.innerHTML = `From your transcript: <b>${info.earned}</b> credits earned${info.inProgress ? ` + ${info.inProgress} in progress` : ""} → <b>${info.projected}</b> standing.${info.projected !== s.yearInSchool && s.yearInSchool !== "incoming" ? ` <button type="button" class="text-action compact" id="useStanding">Use ${info.projected}</button>` : ""}`;
    $("#useStanding")?.addEventListener("click", () => setYearInSchool(info.projected, { keepTerms: true }));
  } else if (s.yearInSchool === "incoming") {
    hint.textContent = "New students enroll at SOAR. Add AP, IB or transfer credit below.";
  } else {
    hint.innerHTML = `Plan starts ${esc(TX.termLabel(w.start))}. Until you import a transcript, about ${STANDING_CREDITS[s.yearInSchool]} earned credits are assumed for ${esc(s.yearInSchool.toLowerCase())} standing. <button type="button" class="text-action compact" id="hintImport">Import transcript</button>`;
    $("#hintImport")?.addEventListener("click", () => openTranscriptDialog());
  }
}
function setYearInSchool(value, options = {}) {
  const s = state.settings;
  s.yearInSchool = value;
  if (!options.keepTerms) {
    const hasHistory = s.prior.some(p => p.term);
    if (value === "incoming") {
      if (TX.termKey({ season: s.startSeason, year: s.startYear }) <= TX.termKey(TX.currentTerm())) { s.startSeason = "Fall"; s.startYear = NEXT_FALL; s.gradSeason = "Spring"; s.gradYear = NEXT_FALL + 4; }
    } else if (!hasHistory) {
      // Estimate when a student in this year started, assuming a fall start and four years.
      const now = TX.currentTerm();
      const fallOfThisYear = now.season === "Fall" ? now.year : now.year - 1;
      const yearsIn = STANDINGS.indexOf(value);
      s.startSeason = "Fall"; s.startYear = fallOfThisYear - yearsIn;
      s.gradSeason = "Spring"; s.gradYear = s.startYear + 4;
    }
  }
  renderSetup();
  markDirty();
  loadTimeline(true);
}

// majors -----------------------------------------------------------------
function addMajorRow(id = "") {
  if (state.settings.majors.length >= 3) return toast("Up to three majors are supported.");
  state.settings.majors.push({ id, variants: {} });
  renderMajors();
  const inputs = $$(".major-item input");
  inputs[inputs.length - 1]?.focus();
}

function renderMajors() {
  const list = $("#majorList");
  list.innerHTML = "";
  state.settings.majors.forEach((major, index) => {
    const item = document.createElement("div");
    item.className = "major-item";
    const info = state.programs.find(p => p.id === major.id);
    item.innerHTML = `
      <div class="row"><span class="tag">${index === 0 ? "First major" : index === 1 ? "Second major" : "Third major"}</span>
        ${state.settings.majors.length > 1 || major.id ? `<button type="button" class="remove" aria-label="Remove major">×</button>` : ""}</div>
      <div class="combo"><input type="search" placeholder="Search 262 majors & named options" value="${esc(info?.name || "")}" aria-label="Major">
        <div class="combo-list hidden" role="listbox"></div></div>
      <div class="variants"></div>
      <div class="meta"></div>`;
    list.appendChild(item);
    const input = $("input", item);
    const results = $(".combo-list", item);
    input.addEventListener("input", () => showProgramOptions(input, results, index));
    input.addEventListener("focus", () => showProgramOptions(input, results, index));
    input.addEventListener("blur", () => setTimeout(() => results.classList.add("hidden"), 180));
    input.addEventListener("keydown", e => comboKeys(e, results));
    $(".remove", item)?.addEventListener("click", () => {
      state.settings.majors.splice(index, 1);
      if (!state.settings.majors.length) state.settings.majors.push({ id: "", variants: {} });
      renderMajors(); markDirty();
    });
    if (info) renderMajorMeta(item, major, info);
  });
  $("#addMajor").classList.toggle("hidden", state.settings.majors.length >= 3 || !state.settings.majors[0]?.id);
  $("#addMajor").textContent = state.settings.majors.length >= 2 ? "+ Add a third major" : "+ Add a second major";
}

async function renderMajorMeta(item, major, info) {
  const conf = { high: "Requirements read from the Guide", medium: "Some requirements inferred — verify in Guide", low: "Complex requirements — verify in Guide", none: "Choose a named option" }[info.confidence] || "";
  $(".meta", item).innerHTML = `${esc(info.college)} · <a href="${esc(info.guide_url)}" target="_blank" rel="noopener">Guide</a> · ${esc(conf)}`;
  const detail = await program(major.id).catch(() => null);
  if (!detail) return;
  const box = $(".variants", item);
  const groups = {};
  (detail.variants || []).forEach(v => (groups[v.group] ||= []).push(v.name));
  let html = "";
  for (const [group, names] of Object.entries(groups)) {
    const chosen = major.variants[group] || names[0];
    html += `<label>${esc(group.replace(" (choose one)", ""))}<select data-group="${esc(group)}">${names.map(n => `<option ${n === chosen ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>`;
  }
  if (detail.named_options?.length) {
    html += `<label>Named option (optional)<select data-named="1"><option value="">— General ${esc(info.name)} —</option>${detail.named_options.map(o => `<option value="${esc(o.id)}">${esc(o.name)}</option>`).join("")}</select></label>`;
  }
  box.innerHTML = html;
  $$("select[data-group]", box).forEach(sel => sel.addEventListener("change", () => {
    major.variants[sel.dataset.group] = sel.value; markDirty();
  }));
  $("select[data-named]", box)?.addEventListener("change", e => {
    if (!e.target.value) return;
    major.id = e.target.value; major.variants = {}; renderMajors(); markDirty();
  });
}

function showProgramOptions(input, results, index) {
  const q = input.value.trim().toLowerCase();
  const taken = new Set(state.settings.majors.map(m => m.id));
  const matches = state.programs.filter(p => (!q || `${p.name} ${p.department || ""} ${p.college}`.toLowerCase().includes(q)) && !taken.has(p.id)).slice(0, 80);
  const groups = {};
  matches.forEach(p => (groups[p.college] ||= []).push(p));
  results.innerHTML = Object.entries(groups).map(([college, items]) =>
    `<div class="combo-group">${esc(college)}</div>` + items.map(p => `<button type="button" class="combo-item" data-id="${esc(p.id)}">${esc(p.name)}<small>${esc(p.department || "")}${p.has_named_options ? " · has named options" : ""}</small></button>`).join("")
  ).join("") || `<div class="combo-item">No match</div>`;
  results.classList.remove("hidden");
  $$(".combo-item[data-id]", results).forEach(btn => btn.addEventListener("mousedown", e => {
    e.preventDefault();
    state.settings.majors[index] = { id: btn.dataset.id, variants: {} };
    results.classList.add("hidden");
    renderMajors();
    markDirty();
    if (index === 0 && $("#view-double").classList.contains("active")) renderDouble();
  }));
}

function comboKeys(e, results) {
  const items = $$(".combo-item[data-id]", results);
  if (!items.length) return;
  const current = items.findIndex(i => i.classList.contains("active"));
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const next = e.key === "ArrowDown" ? Math.min(items.length - 1, current + 1) : Math.max(0, current - 1);
    items.forEach(i => i.classList.remove("active"));
    items[next].classList.add("active");
    items[next].scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter") {
    e.preventDefault();
    (items[current] || items[0]).dispatchEvent(new MouseEvent("mousedown"));
  }
}

// prior credit -----------------------------------------------------------
function bindPriorSearch() {
  const input = $("#priorSearch");
  const results = $("#priorResults");
  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = input.value.trim();
      if (q.length < 2) { results.classList.add("hidden"); return; }
      const rows = await api(`/api/courses?q=${enc(q)}&limit=12`);
      results.innerHTML = rows.map(r => `<button type="button" class="combo-item" data-code="${esc(r.code)}">${esc(r.code)}<small>${esc(r.title)} · ${credits(r)} cr</small></button>`).join("") || `<div class="combo-item">No match</div>`;
      results.classList.remove("hidden");
      $$(".combo-item[data-code]", results).forEach(btn => btn.addEventListener("mousedown", e => {
        e.preventDefault();
        const row = rows.find(r => r.code === btn.dataset.code);
        if (!state.settings.prior.some(p => p.code === row.code)) {
          state.settings.prior.push({ code: row.code, status: state.settings.studentType === "transfer" ? "transfer" : "ap", credits: row.credits_min || row.credits_max || 3 });
        }
        input.value = ""; results.classList.add("hidden");
        renderPriorChips(); markDirty();
        if (state.plan) { syncPriorIntoPlan(); validateSoon(); }
      }));
    }, 180);
  });
  input.addEventListener("keydown", e => comboKeys(e, results));
  input.addEventListener("blur", () => setTimeout(() => results.classList.add("hidden"), 180));
}

function bindTranscriptImport() {
  const dialog = $("#transcriptDialog");
  const fileInput = $("#transcriptFile");
  $("#openTranscript").addEventListener("click", openTranscriptDialog);
  $("#closeTranscript").addEventListener("click", () => dialog.close());
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    const label = $("#transcriptFileName");
    label.classList.toggle("hidden", !file);
    label.textContent = file ? `${file.name} · ${formatBytes(file.size)}` : "";
  });
  $("#parseTranscript").addEventListener("click", parseTranscriptUpload);
  $("#importTranscript").addEventListener("click", importTranscriptMatches);
  $("#toggleTranscriptRows").addEventListener("click", () => {
    const checks = $$("[data-transcript-row]", $("#transcriptRows"));
    const select = checks.every(check => !check.checked);
    checks.forEach(check => { check.checked = select; });
    $("#toggleTranscriptRows").textContent = select ? "Clear all" : "Select all";
    updateTranscriptImportCount();
  });
  $("#transcriptRows").addEventListener("change", updateTranscriptImportCount);
}

function openTranscriptDialog() {
  resetTranscriptDialog();
  $("#transcriptDialog").showModal();
}

function resetTranscriptDialog() {
  state.transcriptMatches = [];
  $("#transcriptFile").value = "";
  $("#transcriptText").value = "";
  $("#transcriptFileName").classList.add("hidden");
  $("#transcriptFeedback").classList.add("hidden");
  $("#transcriptReview").classList.add("hidden");
  $("#importTranscript").classList.add("hidden");
  $("#parseTranscript").classList.remove("hidden");
  $("#parseTranscript").disabled = false;
  $("#parseTranscript").textContent = "Review courses";
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const STATUS_TEXT = { ap: "AP / IB / test", transfer: "Transfer", completed: "Taken at UW", "in-progress": "In progress" };

async function parseTranscriptUpload() {
  const button = $("#parseTranscript");
  const feedback = $("#transcriptFeedback");
  const file = $("#transcriptFile").files?.[0];
  const pasted = $("#transcriptText").value.trim();
  const fail = message => { feedback.textContent = message; feedback.className = "transcript-feedback error"; feedback.focus(); };
  if (!file && !pasted) return fail("Choose a transcript file or paste transcript text first.");
  if (file && file.size > 12 * 1024 * 1024) return fail("That file is larger than the 12 MB limit.");
  button.disabled = true;
  button.textContent = "Reading transcript…";
  feedback.classList.add("hidden");
  try {
    let text = pasted;
    if (file) text += "\n" + (file.name.toLowerCase().endsWith(".pdf") ? await TX.pdfText(await file.arrayBuffer()) : await file.text());
    const { rows, unmatched } = TX.parseTranscriptText(text);
    if (!rows.length) return fail(file?.name.toLowerCase().endsWith(".pdf") && text.trim().length < 40
      ? "This PDF has no readable text (it may be a scan). Copy the course list from Student Center and paste it instead."
      : "No course codes were found. Paste the course-history section, with lines like “COMP SCI 300  Programming II  3.00  A”.");
    const { results } = await api("/api/catalog/resolve", { method: "POST", body: { candidates: rows.map(r => r.guesses) } });
    state.transcriptMatches = TX.combineMatches(rows, results, TX.currentTerm());
    state.transcriptUnmatched = unmatched;
    renderTranscriptReview();
  } catch (error) {
    fail(`Could not read the transcript: ${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "Review courses";
  }
}

function renderTranscriptReview() {
  const rows = $("#transcriptRows"), list = state.transcriptMatches;
  rows.innerHTML = list.map((row, i) => `
    <tr class="${row.include ? "" : "excluded"} ${row.review ? "needs-review" : ""}">
      <td><input type="checkbox" data-transcript-row="${i}" ${row.include ? "checked" : ""} aria-label="Import ${esc(row.code)}"></td>
      <td><strong>${esc(row.code)}</strong><span>${esc(row.title)}</span><small title="${esc(row.evidence)}">${esc(row.note)}${row.attempts > 1 ? ` · taken ${row.attempts} times, latest kept` : ""}</small></td>
      <td>${esc(row.term || "—")}</td>
      <td>${esc(row.grade || (row.status === "in-progress" ? "IP" : "—"))}</td>
      <td>${esc(row.credits)}</td>
      <td><select data-transcript-status="${i}" aria-label="How ${esc(row.code)} counts">${Object.entries(STATUS_TEXT).map(([v, t]) => `<option value="${v}" ${row.status === v ? "selected" : ""}>${t}</option>`).join("")}</select></td>
    </tr>`).join("") || `<tr><td colspan="6">No catalog course codes were found. Try pasting the course-history section.</td></tr>`;
  const counts = { completed: 0, "in-progress": 0, transfer: 0, ap: 0 };
  list.filter(r => r.include).forEach(r => { counts[r.status] = (counts[r.status] || 0) + 1; });
  const terms = new Set(list.filter(r => r.term).map(r => r.term));
  const review = list.filter(r => r.review).length;
  $("#transcriptSummary").textContent = `${list.length} courses across ${terms.size} term${terms.size === 1 ? "" : "s"} · ${counts.completed} completed, ${counts["in-progress"]} in progress, ${counts.transfer + counts.ap} transfer or test credit${review ? ` · ${review} need a look` : ""}`;
  $("#transcriptReview").classList.remove("hidden");
  $("#parseTranscript").classList.add("hidden");
  $("#importTranscript").classList.toggle("hidden", !list.length);
  updateTranscriptImportCount();
}

function updateTranscriptImportCount() {
  $$("[data-transcript-row]", $("#transcriptRows")).forEach(box => { state.transcriptMatches[box.dataset.transcriptRow].include = box.checked; });
  $$("[data-transcript-status]", $("#transcriptRows")).forEach(sel => { state.transcriptMatches[sel.dataset.transcriptStatus].status = sel.value; });
  const selected = state.transcriptMatches.filter(r => r.include).length;
  $("#importTranscript").textContent = `Import ${selected} course${selected === 1 ? "" : "s"}`;
  $("#importTranscript").disabled = selected === 0;
}

function importTranscriptMatches() {
  updateTranscriptImportCount();
  const chosen = state.transcriptMatches.filter(r => r.include);
  const merged = TX.mergePrior(state.settings.prior, chosen);
  state.settings.prior = merged.prior;
  chosen.forEach(row => { if (!state.courseCache.has(row.code)) state.courseCache.set(row.code, { code: row.code, title: row.title, credits_min: row.catalogCredits, credits_max: row.catalogCredits }); });
  // The earliest UW term on the transcript is the first term at UW.
  const uwTerms = state.settings.prior.filter(p => p.term).map(p => TX.parseTermLabel(p.term)).filter(Boolean).sort((a, b) => TX.termKey(a) - TX.termKey(b));
  if (uwTerms.length) {
    const wasIncoming = state.settings.yearInSchool === "incoming";
    state.settings.startSeason = uwTerms[0].season;
    state.settings.startYear = uwTerms[0].year;
    if (wasIncoming || state.settings.gradYear * 3 + SEASONS[state.settings.gradSeason] <= TX.termKey(uwTerms[uwTerms.length - 1])) {
      // A four-year default from the first UW term; the student can change it.
      state.settings.gradSeason = "Spring"; state.settings.gradYear = (uwTerms[0].season === "Fall" ? uwTerms[0].year : uwTerms[0].year - 1) + 4;
    }
  }
  const info = standingInfo();
  if (uwTerms.length) state.settings.yearInSchool = info.projected;
  renderSetup();
  markDirty();
  if (state.plan) { syncPriorIntoPlan(); validateSoon(); }
  loadTimeline(true);
  $("#transcriptDialog").close();
  const parts = [merged.added && `${merged.added} added`, merged.updated && `${merged.updated} updated`, merged.unchanged && `${merged.unchanged} unchanged`].filter(Boolean).join(", ");
  const summary = `${parts || "Nothing new"}. ${info.earned} credits earned → ${info.projected}.`;
  if (state.plan) toast(`${summary} Rebuild the remaining terms?`, { label: "Rebuild", action: generate });
  else toast(summary);
}

function renderPriorChips() {
  const box = $("#priorChips");
  const prior = state.settings.prior;
  const fromTranscript = prior.filter(p => p.term);
  const loose = prior.map((p, i) => ({ p, i })).filter(({ p }) => !p.term);
  box.innerHTML = (fromTranscript.length ? `<div class="prior-summary"><strong>${fromTranscript.length} courses from your transcript</strong><span>${[...new Set(fromTranscript.map(p => p.term))].length} terms · shown on the plan board</span><button type="button" class="text-action compact" data-clear-transcript>Remove</button></div>` : "")
    + loose.map(({ p, i }) => `
    <span class="chip">${esc(p.code)}
      <select data-i="${i}" aria-label="Credit type for ${esc(p.code)}">
        ${Object.entries(STATUS_TEXT).map(([v, t]) => `<option value="${v}" ${p.status === v ? "selected" : ""}>${t}</option>`).join("")}
      </select>
      <button type="button" data-remove="${i}" aria-label="Remove ${esc(p.code)}">×</button></span>`).join("");
  $$("select[data-i]", box).forEach(sel => sel.addEventListener("change", () => { state.settings.prior[sel.dataset.i].status = sel.value; markDirty(); renderStanding(); validateSoon(); }));
  $$("button[data-remove]", box).forEach(btn => btn.addEventListener("click", () => {
    state.settings.prior.splice(Number(btn.dataset.remove), 1);
    renderPriorChips(); markDirty(); renderStanding();
    if (state.plan) { syncPriorIntoPlan(); validateSoon(); }
  }));
  $("[data-clear-transcript]", box)?.addEventListener("click", () => {
    const removed = state.settings.prior.filter(p => p.term);
    state.settings.prior = state.settings.prior.filter(p => !p.term);
    renderSetup(); markDirty(); if (state.plan) { renderBoard(); validateSoon(); }
    toast(`Removed ${removed.length} transcript courses.`, { label: "Undo", action: () => { state.settings.prior.push(...removed); renderSetup(); markDirty(); if (state.plan) { renderBoard(); validateSoon(); } } });
  });
}

function syncPriorIntoPlan() {
  const priorCodes = new Set(state.settings.prior.map(p => p.code));
  state.plan.terms.forEach(t => t.courses = t.courses.filter(c => !priorCodes.has(c.code)));
  renderBoard();
}

// ------------------------------------------------------------------ payload
function payload(extra = {}) {
  const s = state.settings, w = planWindow();
  const majors = s.majors.filter(m => m.id);
  const variants = {};
  majors.forEach(m => { if (Object.keys(m.variants).length) variants[m.id] = m.variants; });
  const placements = {};
  if (s.placeCommA) Object.assign(placements, { comm_a: true, ge_cl: true });
  if (s.placeQrA) Object.assign(placements, { qr_a: true, ge_mqr: true });
  const locked = [];
  state.plan?.terms.forEach(t => t.courses.forEach(c => { if (c.locked) locked.push({ code: c.code, term: t.id }); }));
  // Gen Ed rules follow the first college term; when the plan starts later than that, say so.
  const startedEarlier = TX.termKey(w.start) > TX.termKey({ season: s.startSeason, year: s.startYear });
  const firstCollege = s.studentType === "transfer" ? { season: s.firstCollegeSeason, year: s.firstCollegeYear }
    : startedEarlier ? { season: s.startSeason, year: s.startYear } : null;
  return {
    programs: majors.map(m => m.id), variants,
    studentType: s.studentType,
    startSeason: w.start.season, startYear: w.start.year,
    gradSeason: s.gradSeason, gradYear: s.gradYear,
    firstCollegeSeason: firstCollege?.season || null,
    firstCollegeYear: firstCollege?.year || null,
    includeSummer: s.includeSummer,
    targetCredits: s.targetCredits, maxCredits: s.maxCredits,
    prior: s.prior.filter(p => p.include !== false), genericCredits: Number(s.genericCredits || 0) + w.assumedCredits,
    placements, manualDone: s.manualDone, priority: s.priority, mathPlacement: s.mathPlacement,
    locked, ...extra,
  };
}

// ------------------------------------------------------------------ generate / validate
async function generate() {
  if (!state.settings.majors.some(m => m.id)) return toast("Choose at least one major first.");
  const button = $("#generateBtn");
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span><span>Planning…</span>`;
  try {
    const result = await api("/api/plan/generate", { method: "POST", body: payload() });
    state.plan = { terms: result.terms, unscheduled: result.unscheduled || [] };
    state.validation = result;
    state.planId = state.planId || null;
    markDirty();
    renderBoard();
    renderAudit();
    const shared = result.audit?.shared_courses?.length || 0;
    toast(shared ? `Plan ready — ${shared} course${shared === 1 ? "" : "s"} count for more than one major.` : "Plan ready.");
    showView("plan");
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = `<span>Build my plan</span>`;
  }
}

let validateTimer;
let validateSeq = 0;
function validateSoon(delay = 220) {
  clearTimeout(validateTimer);
  validateTimer = setTimeout(validate, delay);
}

async function validate() {
  if (!state.plan || !state.settings.majors.some(m => m.id)) return;
  const seq = ++validateSeq;
  try {
    const result = await api("/api/plan/validate", { method: "POST", body: payload({ plan: { terms: state.plan.terms } }) });
    if (seq !== validateSeq) return;
    state.validation = { ...result, warnings: result.warnings };
    renderBoard();
    renderAudit();
  } catch (error) {
    toast(error.message);
  }
}

// ------------------------------------------------------------------ board
function sharedSet() { return new Set(state.validation?.audit?.shared_courses || []); }

function renderBoard() {
  const board = $("#board");
  if (!state.plan) return;
  board.classList.remove("empty");
  const v = state.validation || {};
  const issues = v.issues || {};
  const termIssues = v.termIssues || [];
  const shared = sharedSet();
  const years = [];
  state.plan.terms.forEach((term, index) => {
    const academicStart = term.season === "Fall" ? term.year : term.year - 1;
    let group = years.find(y => y.start === academicStart);
    if (!group) years.push(group = { start: academicStart, terms: [] });
    group.terms.push({ term, index });
  });
  const toCard = p => ({ code: p.code, title: state.courseCache.get(p.code)?.title || "", credits: p.credits, kind: "prior", status: p.status, grade: p.grade });
  const priorCards = state.settings.prior.filter(p => !p.term && p.include !== false).map(toCard);
  let html = "";
  if (priorCards.length || state.settings.genericCredits) {
    const total = priorCards.reduce((s, c) => s + Number(c.credits || 0), 0) + Number(state.settings.genericCredits || 0);
    html += `<section class="year"><div class="year-label"><b>Before UW</b><span>${total} credits</span></div><div class="terms">
      <div class="term prior"><div class="term-head"><b>${state.settings.studentType === "transfer" ? "Transfer and test credit" : "AP / test credit"}</b><span class="term-credits">${total} cr</span></div>
      ${priorCards.map(c => cardHtml(c, -2, issues, shared)).join("")}
      ${state.settings.genericCredits ? `<div class="card prior"><div class="code">+${state.settings.genericCredits} credits</div><div class="title">Credit without a UW equivalent</div></div>` : ""}
      </div></div></section>`;
  }
  html += historyHtml(issues, shared, toCard);
  years.forEach((year, i) => {
    const credits = year.terms.reduce((s, { term }) => s + termCredits(term), 0);
    html += `<section class="year"><div class="year-label"><b>${year.start}–${String(year.start + 1).slice(2)}</b><span>${credits} cr planned</span></div><div class="terms">`;
    year.terms.forEach(({ term, index }) => {
      const load = termCredits(term);
      const notes = termIssues.filter(t => t.term === index);
      const over = load > (term.season === "Summer" ? 12 : state.settings.maxCredits);
      html += `<div class="term ${term.season === "Summer" ? "summer" : ""} ${over ? "over" : ""}" data-term-index="${index}">
        <div class="term-head"><b>${esc(term.label)}</b><span class="term-credits ${over ? "bad" : ""}">${load} cr</span></div>
        ${notes.map(n => `<div class="term-note ${n.level}">${esc(n.message)}</div>`).join("")}
        ${term.courses.filter(c => !c.placeholder).map(c => cardHtml(c, index, issues, shared)).join("")}
        ${electiveSummaryHtml(term.courses.filter(c => c.placeholder), index)}
        <button type="button" class="term-add" data-add-term="${index}">+ Add course</button>
      </div>`;
    });
    html += `</div></section>`;
  });
  board.innerHTML = html;

  const tray = $("#tray");
  const unscheduled = state.plan.unscheduled || [];
  tray.classList.toggle("hidden", !unscheduled.length);
  $("#trayCourses").innerHTML = unscheduled.map(c => cardHtml(c, -1, issues, shared)).join("");
  bindBoard();
  renderStats();
  renderAlerts();
  syncChrome();
  const names = state.settings.majors.filter(m => m.id).map(m => state.programs.find(p => p.id === m.id)?.name).filter(Boolean);
  $("#planTitle").textContent = names.join(" + ") || "Your plan";
  $("#compactPlanName").textContent = names.join(" + ") || "Degree plan";
  $("#legend").classList.remove("hidden");
  const w = planWindow();
  $("#planSubtitle").textContent = `${w.current ? `Planning ${TX.termLabel(w.start)}` : `${state.settings.startSeason} ${state.settings.startYear}`} → ${state.settings.gradSeason} ${state.settings.gradYear}. Drag courses between terms; each move is re-checked for prerequisites, the published schedule and requirements.`;
  renderNextUp();
}

// Terms already taken (from the transcript), shown read-only above the plan.
function historyHtml(issues, shared, toCard) {
  const w = planWindow();
  const withTerm = state.settings.prior.filter(p => p.term && p.include !== false);
  if (!withTerm.length) {
    if (!w.current) return "";
    return `<section class="year history-note"><div class="year-label"><b>Before ${esc(TX.termLabel(w.start))}</b><span>not on this plan</span></div>
      <div class="history-empty"><p><strong>Courses you have already taken are not shown.</strong> Import your transcript so completed and in-progress courses count toward requirements and prerequisites.</p><button type="button" class="btn small" data-open-transcript>Import transcript</button></div></section>`;
  }
  const byTerm = new Map();
  withTerm.forEach(p => { if (!byTerm.has(p.term)) byTerm.set(p.term, []); byTerm.get(p.term).push(p); });
  const terms = [...byTerm.keys()].map(TX.parseTermLabel).filter(Boolean).sort((a, b) => TX.termKey(a) - TX.termKey(b));
  const years = [];
  terms.forEach(t => {
    const start = t.season === "Fall" ? t.year : t.year - 1;
    let y = years.find(g => g.start === start);
    if (!y) years.push(y = { start, terms: [] });
    y.terms.push(t);
  });
  const earned = withTerm.filter(p => p.status !== "in-progress").reduce((sum, p) => sum + Number(p.credits || 0), 0);
  return `<details class="history" ${state.historyOpen ? "open" : ""}><summary><span><b>Already taken</b> · ${withTerm.length} courses, ${earned} credits earned${withTerm.some(p => p.status === "in-progress") ? " + this term in progress" : ""}</span><span class="history-toggle">Show</span></summary>
    ${years.map(y => `<section class="year past"><div class="year-label"><b>${y.start}–${String(y.start + 1).slice(2)}</b><span>${y.terms.some(t => byTerm.get(TX.termLabel(t)).some(p => p.status === "in-progress")) ? "in progress" : "completed"}</span></div><div class="terms">
      ${y.terms.map(t => { const list = byTerm.get(TX.termLabel(t)); const cr = list.reduce((s2, p) => s2 + Number(p.credits || 0), 0);
        const inProgress = list.some(p => p.status === "in-progress");
        return `<div class="term history-term ${inProgress ? "current" : ""}"><div class="term-head"><b>${esc(TX.termLabel(t))}</b><span class="term-credits">${inProgress ? "in progress · " : ""}${cr} cr</span></div>${list.map(p => cardHtml(toCard(p), -2, issues, shared)).join("")}</div>`; }).join("")}
    </div></section>`).join("")}</details>`;
}

// Open elective slots are summarised per term instead of one card per slot.
function electiveSummaryHtml(slots, termIndex) {
  if (!slots.length) return "";
  const total = slots.reduce((sum, c) => sum + Number(c.credits || 0), 0);
  return `<button type="button" class="card elective-summary" data-elective-term="${termIndex}" data-elective-code="${esc(slots[0].code)}">
    <span class="code">${slots.length === 1 ? "Open elective" : `${slots.length} open electives`}</span>
    <span class="title">${total} credits of any course</span>
    <span class="meta"><span class="badge">Choose a course</span></span></button>`;
}

function termCredits(term) { return term.courses.reduce((s, c) => s + Number(c.credits || 0), 0); }
function credits(r) { return r.credits_min === r.credits_max ? r.credits_min : `${r.credits_min}–${r.credits_max}`; }

let dragData = null;
function listFor(index) { return index === -1 ? state.plan.unscheduled : state.plan.terms[index].courses; }
function moveCourse(code, from, to) {
  if (from === to || from === -2) return;
  const source = listFor(from);
  const i = source.findIndex(c => c.code === code);
  if (i < 0) return;
  const [card] = source.splice(i, 1);
  card.locked = to >= 0;  // a manual move pins the course so regeneration keeps it
  listFor(to).push(card);
  markDirty();
  renderBoard();
  validateSoon(60);
  const label = to === -1 ? "unscheduled" : state.plan.terms[to].label;
  toast(`${card.placeholder ? "Elective" : code} → ${label}`);
}

// card menu -------------------------------------------------------------
function openMenu(e, cardEl) {
  e.stopPropagation();
  closeMenu();
  const code = cardEl.dataset.code;
  const from = Number(cardEl.dataset.term);
  const card = findCard(code);
  const menu = document.createElement("div");
  menu.className = "card-menu";
  const moveButtons = state.plan.terms.map((t, i) => i === from ? "" : `<button data-move="${i}">Move to ${esc(t.label)}</button>`).join("");
  menu.innerHTML = `
    ${card.placeholder ? `<button data-act="replace">Choose a course…</button>` : `<button data-act="details">Details & grades</button>`}
    ${from >= 0 ? `<button data-act="lock">${card.locked ? "Unpin from this term" : "Pin to this term"}</button>` : ""}
    <div class="sep"></div>${moveButtons}
    ${from !== -1 ? `<button data-move="-1">Move to “not scheduled”</button>` : ""}
    <div class="sep"></div><button data-act="remove" class="danger">Remove from plan</button>`;
  document.body.appendChild(menu);
  const rect = e.target.getBoundingClientRect();
  menu.style.top = `${Math.min(rect.bottom + 4, window.innerHeight - menu.offsetHeight - 8)}px`;
  menu.style.left = `${Math.min(rect.left - 150, window.innerWidth - menu.offsetWidth - 8)}px`;
  menu.addEventListener("click", ev => {
    const btn = ev.target.closest("button");
    if (!btn) return;
    if (btn.dataset.move !== undefined) moveCourse(code, from, Number(btn.dataset.move));
    else if (btn.dataset.act === "details") openDrawer(code);
    else if (btn.dataset.act === "replace") openAddDialog(from, code);
    else if (btn.dataset.act === "lock") { card.locked = !card.locked; renderBoard(); markDirty(); }
    else if (btn.dataset.act === "remove") removeCourse(code);
    closeMenu();
  });
}
function closeMenu() { $$(".card-menu").forEach(m => m.remove()); }

// add / replace dialog ---------------------------------------------------
function openAddDialog(termIndex, replaceCode = null, presetQuery = "") {
  const dialog = $("#addDialog");
  const term = termIndex >= 0 ? state.plan?.terms[termIndex] : null;
  $("#addDialogTitle").textContent = replaceCode ? `Replace elective${term ? ` · ${term.label}` : ""}` : `Add a course${term ? ` to ${term.label}` : ""}`;
  const input = $("#addSearch");
  input.value = presetQuery;
  $("#addResults").innerHTML = "";
  let timer;
  input.oninput = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = input.value.trim();
      if (q.length < 2) { $("#addResults").innerHTML = ""; return; }
      const rows = await api(`/api/courses?q=${enc(q)}&limit=25`);
      $("#addResults").innerHTML = rows.map(r => resultHtml(r, "Add")).join("") || `<p class="subtle">No match.</p>`;
      $$("#addResults .result").forEach(btn => btn.addEventListener("click", () => {
        const row = rows.find(r => r.code === btn.dataset.code);
        addToPlan(row, termIndex, replaceCode);
        dialog.close();
      }));
    }, 180);
  };
  dialog.showModal();
  if (presetQuery) input.oninput();
  input.focus();
}

function addToPlan(row, termIndex, replaceCode = null) {
  if (!state.plan) return toast("Build a plan first.");
  if (findCard(row.code)) return toast(`${row.code} is already in your plan.`);
  const card = { code: row.code, title: row.title, credits: row.credits_min || row.credits_max || 3, kind: "major", reasons: ["Added by you"], avgGpa: row.avg_gpa, locked: termIndex >= 0 };
  if (replaceCode) {
    for (const list of [state.plan.unscheduled, ...state.plan.terms.map(t => t.courses)]) {
      const i = list.findIndex(c => c.code === replaceCode);
      if (i >= 0) { list.splice(i, 1, card); break; }
    }
  } else {
    let target = termIndex;
    if (target === undefined || target === null || target < -1) target = earliestTerm(row);
    listFor(target).push(card);
  }
  markDirty(); renderBoard(); validateSoon(40);
  toast(`${row.code} added.`);
}

function earliestTerm(row) {
  const seasons = row.offered_seasons || [];
  const idx = state.plan.terms.findIndex(t => t.season !== "Summer" && (!seasons.length || seasons.includes(t.season)) && termCredits(t) < state.settings.maxCredits);
  return idx >= 0 ? idx : -1;
}

// ------------------------------------------------------------------ stats + alerts
function renderStats() {
  const v = state.validation;
  if (!v?.audit) { $("#stats").innerHTML = ""; return; }
  const audit = v.audit;
  const planned = audit.credits.planned;
  const majors = audit.programs.map(p => p.summary.percent);
  const errors = Object.values(v.issues || {}).flat().filter(i => i.level === "error").length;
  const shared = audit.shared_courses.length;
  $("#stats").innerHTML = `
    <div class="stat ${planned >= 120 ? "good" : ""}"><b>${planned}</b><span>of 120 credits</span></div>
    ${audit.programs.map(p => `<div class="stat ${p.summary.percent === 100 ? "good" : ""}"><b>${p.summary.percent}%</b><span>${esc(shortName(p.name))}</span></div>`).join("")}
    <div class="stat ${audit.degree_summary.percent === 100 ? "good" : ""}"><b>${audit.degree_summary.percent}%</b><span>Degree & gen ed</span></div>
    ${audit.programs.length > 1 ? `<div class="stat gold"><b>${shared}</b><span>shared · ${audit.shared_credits} cr saved</span></div>` : ""}
    <div class="stat ${errors ? "bad" : "good"}"><b>${errors}</b><span>conflicts</span></div>`;
  void majors;
}

function shortName(name) { return name.replace(/, (B[A-Z]+|BS AMEP)$/, "").slice(0, 28); }

// ------------------------------------------------------------------ audit view
function renderAudit() {
  const body = $("#auditBody");
  const audit = state.validation?.audit;
  if (!audit) { body.innerHTML = `<p class="subtle">Build a plan to see your audit.</p>`; return; }
  const shared = sharedSet();
  const programHtml = audit.programs.map(p => {
    const prog = state.programCache.get(p.id);
    const blocksById = new Map((prog?.blocks || []).map(b => [b.key, b]));
    const pct = p.summary;
    const doneShare = Math.round(100 * pct.complete / Math.max(1, pct.complete + pct.planned + pct.partial + pct.missing));
    return `<article class="audit-card">
      <header><div><h3>${esc(p.name)}</h3><p>${esc(p.college)} · <a href="${esc(p.guide_url)}" target="_blank" rel="noopener">UW Guide requirements</a></p></div>
        ${progressHtml(doneShare, pct.percent)}</header>
      ${p.blocks.map(b => reqHtml(b, blocksById.get(b.key), shared)).join("")}
    </article>`;
  }).join("");
  const degree = audit.degree;
  const college = degree.filter(r => r.scope === "college");
  const uni = degree.filter(r => r.scope === "university");
  const ruleCard = (title, rules, sub) => `<article class="audit-card"><header><div><h3>${esc(title)}</h3><p>${esc(sub)}</p></div>
      ${(() => { const counted = Math.max(1, rules.filter(r => r.status !== "manual").length); return progressHtml(Math.round(100 * rules.filter(r => r.status === "complete").length / counted), Math.round(100 * rules.filter(r => ["complete", "planned"].includes(r.status)).length / counted)); })()}</header>
      ${rules.map(r => ruleHtml(r, shared)).join("")}</article>`;
  const profile = state.programCache.get(audit.programs[0]?.id)?.profile;
  body.innerHTML = programHtml
    + ruleCard(state.meta.profiles[profile] || "School / college requirements", college, "Degree requirements of your first major's school or college")
    + ruleCard(state.validation.rules?.gened === "Core GenEd" ? "University Core GenEd (Summer 2026+)" : "University General Education", uni, "Applies to every UW–Madison bachelor's degree");
  $$(".used .badge[data-code], .options-list button[data-code]", body).forEach(el => el.addEventListener("click", async () => {
    if (!el.dataset.add) return openDrawer(el.dataset.code);
    const d = await course(el.dataset.code).catch(() => null);
    if (!d) return toast(`${el.dataset.code} is not in the current catalog.`);
    addToPlan({ code: d.code, title: d.title, credits_min: d.credits_min, credits_max: d.credits_max, avg_gpa: d.avg_gpa, offered_seasons: d.offered_seasons });
  }));
  $$("input[data-manual]", body).forEach(box => box.addEventListener("change", () => {
    const id = box.dataset.manual;
    const set = new Set(state.settings.manualDone);
    box.checked ? set.add(id) : set.delete(id);
    state.settings.manualDone = [...set];
    markDirty(); validateSoon(0);
  }));
  // make sure program details (for alternatives) are cached
  audit.programs.forEach(p => { if (!state.programCache.has(p.id)) program(p.id).then(renderAudit).catch(() => {}); });
}

function progressHtml(done, total) {
  const planned = Math.max(0, total - done);
  return `<div class="progress" role="img" aria-label="${done}% complete, ${planned}% planned">
    <div class="bar"><i class="done" style="width:${done}%"></i><i class="plan" style="width:${planned}%"></i></div>
    <small><b>${total}%</b> covered${done ? ` · ${done}% complete` : ""}</small></div>`;
}

// Course chips under a requirement. Elective placeholders (ELECTIVE-n) are
// internal slot ids, so they are counted rather than shown as course codes.
function usedBadges(list, shared) {
  const open = list.filter(u => String(u.code).startsWith("ELECTIVE"));
  const real = list.filter(u => !String(u.code).startsWith("ELECTIVE"));
  const chips = real.map(u => u.code === "Placement exam"
    ? `<span class="badge done">Placement</span>`
    : `<button type="button" class="badge ${shared.has(u.code) ? "shared" : u.status === "planned" ? "planned" : "done"}" data-code="${esc(u.code)}" title="${u.status === "planned" ? "Planned" : "Complete"}">${esc(u.code)}</button>`);
  if (open.length) chips.push(`<span class="badge elective">${open.length} open elective${open.length === 1 ? "" : "s"}</span>`);
  return chips.join("");
}

const ICON = { complete: "✓", planned: "◔", partial: "◐", missing: "!", manual: "?" };
const STATUS_LABEL = { complete: "Complete", planned: "Planned", partial: "In progress", missing: "Missing", manual: "Confirm yourself" };
function reqHtml(result, block, shared) {
  const used = usedBadges(result.used, shared);
  let rule = { all: "All required", choose: `Choose ${result.count || 1}`, credits: `${result.credits || "?"} credits`, pattern: `${result.credits || ""} credits (subject rule)`, text: "See Guide" }[result.rule] || "";
  let options = "";
  if (block && ["missing", "partial"].includes(result.status)) {
    const usedCodes = new Set(result.used.map(u => u.code));
    const codes = [];
    block.slots.forEach(s => s.options.forEach(o => o.forEach(c => { if (!usedCodes.has(c) && !codes.includes(c)) codes.push(c); })));
    if (codes.length) options = `<div class="options-list">Options: ${codes.slice(0, 14).map(c => `<button data-code="${esc(c)}" data-add="1" title="Add ${esc(c)} to plan">+ ${esc(c)}</button>`).join("")}${codes.length > 14 ? ` <span>+${codes.length - 14} more</span>` : ""}</div>`;
  }
  const conf = result.confidence === "low" ? `<span class="pill low" title="Requirement text was complex; verify in the Guide">verify</span>` : result.confidence === "medium" ? `<span title="Rule inferred from Guide layout">inferred</span>` : "";
  return `<div class="req ${result.status}">
    <span class="icon" aria-hidden="true">${ICON[result.status]}</span>
    <div><div class="name">${esc(result.name)} <span class="status-text">${STATUS_LABEL[result.status] || ""}</span></div>
      ${result.need ? `<div class="need">${esc(result.need)}</div>` : ""}
      ${result.notes?.length && result.status !== "complete" ? `<div class="hint">${esc(result.notes[0]).slice(0, 220)}</div>` : ""}
      ${used ? `<div class="used">${used}</div>` : ""}${options}</div>
    <div class="conf">${esc(rule)}<br>${conf}</div></div>`;
}

function ruleHtml(r, shared) {
  const used = usedBadges(r.used || [], shared);
  const manual = r.type === "manual" ? `<label class="check"><input type="checkbox" data-manual="${esc(r.id)}" ${state.settings.manualDone.includes(r.id) ? "checked" : ""}> I've met this (e.g. high-school units)</label>` : "";
  const tagSearch = r.type === "designation" && ["missing", "partial"].includes(r.status) ? ` <a href="#" data-tag-search="${esc((r.tags || [])[0] || "")}">find courses</a>` : "";
  return `<div class="req ${r.status}"><span class="icon" aria-hidden="true">${ICON[r.status]}</span>
    <div><div class="name">${esc(r.name)} <span class="status-text">${STATUS_LABEL[r.status] || ""}</span></div>
      ${r.need && r.status !== "complete" ? `<div class="need">${esc(r.need)}${tagSearch}</div>` : ""}
      ${r.note && r.status !== "complete" && r.type !== "manual" ? `<div class="hint">${esc(r.note)}</div>` : ""}
      ${used ? `<div class="used">${used}</div>` : ""}${manual}</div>
    <div class="conf">${r.credits_applied !== undefined ? `${r.credits_applied} cr` : ""}</div></div>`;
}

document.addEventListener("click", e => {
  const link = e.target.closest("[data-tag-search]");
  if (!link) return;
  e.preventDefault();
  showView("explore");
  $("#exploreTag").value = link.dataset.tagSearch || "";
  $("#exploreSearch").value = "";
  runExploreSearch();
});

// ------------------------------------------------------------------ course drawer
async function openDrawer(code) {
  const drawer = $("#drawer");
  drawer.classList.add("open");
  drawer.inert = false;
  drawer.dataset.returnFocus = document.activeElement?.id || "";
  drawer.setAttribute("aria-hidden", "false");
  $("#scrim").classList.remove("hidden");
  $("#drawerBody").innerHTML = `<p class="subtle">Loading ${esc(code)}…</p>`;
  $("#drawerClose").focus({ preventScroll: true });
  let d;
  try { d = await course(code); } catch (error) { $("#drawerBody").innerHTML = `<p>${esc(error.message)}</p>`; return; }
  const placedTerm = termIndexOf(d.code);
  const before = coursesBefore(placedTerm);
  const tags = d.tags.filter(t => !["las"].includes(t)).map(t => `<span class="badge">${esc(state.meta.tags[t] || t)}</span>`).join("");
  const cumulative = d.grades.find(g => g.term === "cumulative");
  const termsHist = d.grades.filter(g => g.term !== "cumulative").reverse();
  const inPlan = !!findCard(d.code) || state.settings.prior.some(p => p.code === d.code);
  const programs = d.required_by || [];
  $("#drawerBody").innerHTML = `
    <div class="d-code">${esc(d.code)}</div>
    <div class="d-title">${esc(d.title)}</div>
    <div class="d-row">
      <span class="badge">${d.credits_min === d.credits_max ? d.credits_min : `${d.credits_min}–${d.credits_max}`} credits</span>
      <span class="badge" title="From ${esc(d.offering_confidence)} data">${d.offered_seasons.length ? esc(d.offered_seasons.join(" / ")) : "Offering unknown"}</span>
      ${d.offering_frequency !== "unknown" ? `<span class="badge">${esc(d.offering_frequency)}</span>` : ""}
      ${d.last_taught ? `<span class="badge">Last taught ${esc(d.last_taught)}</span>` : ""}
      ${tags}
    </div>
    ${state.plan && !inPlan ? `<button class="btn primary small" id="drawerAdd">Add to my plan</button>` : ""}
    <div class="d-section"><h4>Description</h4>${descriptionHtml(d, "d-desc")}</div>
    <div class="d-section"><h4>Requisites</h4>
      ${d.requisite_text ? `<p class="d-desc">${esc(d.requisite_text)}</p>` : `<p class="subtle">None listed.</p>`}
      ${d.requisite_tree ? `<div class="req-tree">${treeHtml(d.requisite_tree, before)}</div><p class="source-note">✓ = satisfied by an earlier term in your plan${placedTerm >= 0 ? ` (before ${esc(state.plan.terms[placedTerm].label)})` : ""}.</p>` : ""}
      ${d.exclusions?.length ? `<p class="hint">Not open to students with credit for ${d.exclusions.map(esc).join(", ")}.</p>` : ""}
    </div>
    ${cumulative ? `<div class="d-section"><h4>Grade distribution · Madgrades</h4>${gradeChart(cumulative)}
      <div class="grade-legend"><span>Average GPA <b>${cumulative.gpa?.toFixed(2) ?? "—"}</b></span><span>${cumulative.total.toLocaleString()} grades, all terms</span></div>
      ${termsHist.length > 1 ? gpaTrend(termsHist) : ""}</div>` : `<div class="d-section"><h4>Grade distribution</h4><p class="subtle">No Madgrades history for this course.</p></div>`}
    <div class="d-section"><h4>Instructors · Rate My Professors</h4>${instructorTable(d.instructors)}
      <p class="source-note">RMP ratings are student opinions (1–5) attached to the instructor, not the course; low review counts are noisy. Instructors are from Madgrades records since Fall 2021.</p></div>
    ${d.unlocks?.length ? `<div class="d-section"><h4>Unlocks</h4><div class="d-row">${d.unlocks.slice(0, 30).map(c => `<button class="badge" data-open="${esc(c)}">${esc(c)}</button>`).join("")}</div></div>` : ""}
    ${programs.length ? `<div class="d-section"><h4>Counts toward (${programs.length}${programs.length >= 60 ? "+" : ""} majors)</h4><div class="d-row">${programs.slice(0, 24).map(p => `<span class="badge" title="${esc(p.block)}">${esc(shortName(p.name))}</span>`).join("")}</div></div>` : ""}
    <div class="link-row">
      <a href="${esc(d.guide_url)}" target="_blank" rel="noopener">UW Guide</a>
      <a href="https://public.enroll.wisc.edu/search?keywords=${enc(d.code)}" target="_blank" rel="noopener">Course Search & Enroll</a>
      <a href="https://madgrades.com/search?query=${enc(d.code)}" target="_blank" rel="noopener">Madgrades</a>
      <a href="https://www.ratemyprofessors.com/search/professors/1256?q=${enc(d.instructors?.[0]?.display_name || "")}" target="_blank" rel="noopener">Rate My Professors</a>
    </div>`;
  $$("[data-open]", $("#drawerBody")).forEach(b => b.addEventListener("click", () => openDrawer(b.dataset.open)));
  $("#drawerAdd")?.addEventListener("click", () => {
    addToPlan({ code: d.code, title: d.title, credits_min: d.credits_min, credits_max: d.credits_max, avg_gpa: d.avg_gpa, offered_seasons: d.offered_seasons });
    closeDrawer();
  });
}

function closeDrawer() {
  if (!$("#drawer").classList.contains("open")) return;
  $("#drawer").classList.remove("open");
  $("#drawer").inert = true;
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#scrim").classList.add("hidden");
  const back = $("#drawer").dataset.returnFocus;
  if (back) document.getElementById(back)?.focus();
}

function termIndexOf(code) {
  if (!state.plan) return -1;
  return state.plan.terms.findIndex(t => t.courses.some(c => c.code === code));
}

function coursesBefore(index) {
  const set = new Set(state.settings.prior.map(p => p.code));
  if (!state.plan) return set;
  const limit = index >= 0 ? index : state.plan.terms.length;
  state.plan.terms.forEach((t, i) => { if (i < limit) t.courses.forEach(c => set.add(c.code)); });
  return set;
}

function treeHtml(node, have) {
  if (!node) return "";
  if (node.op) {
    return `<div class="node"><span class="op">${node.op === "and" ? "All of" : "One of"}</span>${node.args.map(a => treeHtml(a, have)).join("")}</div>`;
  }
  if (node.course) {
    const ok = have.has(node.course);
    return `<div><span class="leaf ${ok ? "ok" : "no"}"><button data-open="${esc(node.course)}">${esc(node.course)}</button>${node.coreq ? " <small>(same term OK)</small>" : ""}</span></div>`;
  }
  if (node.placement !== undefined) return `<div><span class="leaf cond">placement ${node.placement ? `into ${esc(node.placement)}` : "exam"}</span></div>`;
  if (node.standing) return `<div><span class="leaf cond">${esc(node.standing)} standing</span></div>`;
  if (node.text === "retired-option") return "";
  return `<div><span class="leaf cond">${esc(node.text || "")}</span></div>`;
}

function gradeChart(g) {
  const keys = [["a", "A"], ["ab", "AB"], ["b", "B"], ["bc", "BC"], ["c", "C"], ["d", "D"], ["f", "F"]];
  const graded = keys.reduce((s, [k]) => s + (g[k] || 0), 0) || 1;
  const w = 420, h = 150, pad = 22, bw = (w - pad * 2) / keys.length;
  const max = Math.max(...keys.map(([k]) => (g[k] || 0) / graded));
  // One ramp: A–B green, BC–C amber, D–F red.
  const colors = ["var(--grade-a)", "var(--grade-a)", "var(--grade-b)", "var(--grade-c)", "var(--grade-c)", "var(--grade-f)", "var(--grade-f)"];
  const bars = keys.map(([k, label], i) => {
    const share = (g[k] || 0) / graded;
    const bh = max ? (share / max) * (h - 44) : 0;
    const x = pad + i * bw + 5, y = h - 22 - bh;
    return `<rect x="${x}" y="${y}" width="${bw - 10}" height="${bh}" rx="4" fill="${colors[i]}"><title>${label}: ${(share * 100).toFixed(1)}%</title></rect>
      <text x="${x + (bw - 10) / 2}" y="${y - 5}" text-anchor="middle" font-size="11" fill="var(--color-ink-soft)">${Math.round(share * 100)}%</text>
      <text x="${x + (bw - 10) / 2}" y="${h - 6}" text-anchor="middle" font-size="12" font-weight="700" fill="var(--color-ink)">${label}</text>`;
  }).join("");
  return `<svg class="grade-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Grade distribution">${bars}</svg>`;
}

function gpaTrend(rows) {
  const pts = rows.filter(r => r.gpa);
  if (pts.length < 2) return "";
  const w = 420, h = 90, pad = 26;
  const min = Math.min(...pts.map(p => p.gpa)) - 0.1, max = Math.max(...pts.map(p => p.gpa)) + 0.1;
  const x = i => pad + (i * (w - pad * 2)) / (pts.length - 1);
  const y = v => h - 22 - ((v - min) / (max - min || 1)) * (h - 40);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.gpa).toFixed(1)}`).join(" ");
  const dots = pts.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.gpa)}" r="3.5" fill="var(--color-accent)"><title>${p.label}: ${p.gpa.toFixed(2)} (${p.total} grades)</title></circle>`).join("");
  const labels = [0, pts.length - 1].map(i => `<text x="${x(i)}" y="${h - 4}" text-anchor="${i ? "end" : "start"}" font-size="11" fill="var(--color-muted)">${pts[i].label}</text>`).join("");
  return `<div class="hint" style="margin-top:12px">Average GPA by term</div><svg class="grade-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="GPA trend">
    <path d="${path}" fill="none" stroke="var(--color-accent)" stroke-width="2"/>${dots}${labels}
    <text x="${w - 4}" y="12" text-anchor="end" font-size="11" fill="var(--color-muted)">${max.toFixed(2)}</text><text x="${w - 4}" y="${h - 24}" text-anchor="end" font-size="11" fill="var(--color-muted)">${min.toFixed(2)}</text></svg>`;
}

const RMP_MIN_REVIEWS = 5;
function rmpCell(value, count, digits = 1, suffix = "") {
  if (value == null) return `<span class="subtle">—</span>`;
  const text = `${Number(value).toFixed(digits)}${suffix}`;
  return count >= RMP_MIN_REVIEWS ? text : `<span class="thin-sample" title="Only ${count} review${count === 1 ? "" : "s"} — too few to compare">${text}*</span>`;
}

// RMP aggregates are only colour-coded once there are enough reviews; rows
// with no RMP record at all are folded away so they do not crowd the table.
function instructorTable(rows) {
  if (!rows?.length) return `<p class="subtle">No instructor history.</p>`;
  const cls = v => v >= 4 ? "hi" : v >= 3 ? "mid" : "lo";
  const rated = rows.filter(r => r.rmp_rating != null).sort((a, b) => ((b.rmp_count || 0) >= RMP_MIN_REVIEWS) - ((a.rmp_count || 0) >= RMP_MIN_REVIEWS) || b.terms - a.terms);
  const unrated = rows.filter(r => r.rmp_rating == null);
  const row = r => {
    const count = r.rmp_count || 0, enough = count >= RMP_MIN_REVIEWS;
    const name = r.rmp_id ? `<a href="https://www.ratemyprofessors.com/professor/${r.rmp_id}" target="_blank" rel="noopener">${esc(r.display_name || titleCase(r.name))}</a>` : esc(r.display_name || titleCase(r.name));
    return `<tr><td>${name}<br><small class="subtle">${esc(r.position || "Instructor")}${r.rmp_rating != null ? ` · ${count} review${count === 1 ? "" : "s"}` : ""}</small></td>
      <td class="num">${r.rmp_rating == null ? `<span class="subtle">—</span>` : enough ? `<span class="rating ${cls(r.rmp_rating)}">${r.rmp_rating.toFixed(1)}</span>` : rmpCell(r.rmp_rating, count)}</td>
      <td class="num">${rmpCell(r.rmp_difficulty, count)}</td>
      <td class="num">${rmpCell(r.rmp_would_take_again, count, 0, "%")}</td>
      <td class="num">${r.terms}</td></tr>`;
  };
  const head = `<thead><tr><th>Instructor</th><th class="num">Rating</th><th class="num">Difficulty</th><th class="num">Again</th><th class="num">Terms</th></tr></thead>`;
  const thin = rated.some(r => (r.rmp_count || 0) < RMP_MIN_REVIEWS);
  return `${rated.length ? `<div class="table-scroll"><table class="inst-table">${head}<tbody>${rated.map(row).join("")}</tbody></table></div>` : `<p class="subtle">None of the recent instructors has a matched Rate My Professors profile.</p>`}
    ${thin ? `<p class="source-note">* Fewer than ${RMP_MIN_REVIEWS} reviews: shown for reference, not colour-coded.</p>` : ""}
    ${unrated.length ? `<details class="more-instructors"><summary>${unrated.length} more instructor${unrated.length === 1 ? "" : "s"} without RMP ratings</summary><ul>${unrated.map(r => `<li>${esc(r.display_name || titleCase(r.name))} <small class="subtle">${esc(r.position || "")}${r.position ? " · " : ""}${r.terms} term${r.terms === 1 ? "" : "s"}</small></li>`).join("")}</ul></details>` : ""}`;
}
function titleCase(s = "") { return s.toLowerCase().replace(/\b\w/g, c => c.toUpperCase()); }

// ------------------------------------------------------------------ double major
// ------------------------------------------------------------------ explore
function resultHtml(r, action = "") {
  return `<button type="button" class="result" data-code="${esc(r.code)}"><div><b>${esc(r.code)}</b><small>${esc(r.title)}</small></div>
    <div class="right">${credits(r)} cr${r.avg_gpa ? ` · GPA ${r.avg_gpa.toFixed(2)}` : ""}<br>${esc((r.offered_seasons || []).join("/") || "")}${action ? ` · <b class="result-action">${action}</b>` : ""}</div></button>`;
}

// ------------------------------------------------------------------ save / load / export
function bindTopActions() {
  $("#savePlan").addEventListener("click", savePlan);
  $("#exportPlan").addEventListener("click", exportPlan);
  $("#printPlan").addEventListener("click", () => { showView("plan"); window.print(); });
  $("#openPlans").addEventListener("click", openPlans);
  $("#importFile").addEventListener("change", importPlan);
}

function snapshot() {
  const names = state.settings.majors.filter(m => m.id).map(m => state.programs.find(p => p.id === m.id)?.name).filter(Boolean);
  return { id: state.planId, name: names.join(" + ") || "My UW plan", settings: state.settings, terms: state.plan?.terms || [], unscheduled: state.plan?.unscheduled || [], savedAt: new Date().toISOString() };
}

// Saved plans live in the local database when BadgerPlan runs on your own
// computer, and in this browser on the public site (meta.public).
const BROWSER_PLANS = "badgerplan:saved";
function browserPlans() {
  try { return JSON.parse(localStorage.getItem(BROWSER_PLANS) || "[]"); } catch { return []; }
}
function writeBrowserPlans(list) {
  try { localStorage.setItem(BROWSER_PLANS, JSON.stringify(list)); return true; } catch { return false; }
}

async function savePlan() {
  if (!state.plan) return toast("Build a plan before saving.");
  try {
    if (state.meta?.public) {
      const plans = browserPlans();
      const data = snapshot();
      data.id = state.planId || `p${Date.now().toString(36)}`;
      const i = plans.findIndex(p => p.id === data.id);
      if (i >= 0) plans[i] = data; else plans.unshift(data);
      if (!writeBrowserPlans(plans.slice(0, 20))) throw new Error("This browser is not allowing storage. Use Export to keep a copy.");
      state.planId = data.id;
    } else {
      const result = await api("/api/plans", { method: "POST", body: snapshot() });
      state.planId = result.id;
    }
    state.dirty = false;
    $("#saveStatus").textContent = "Saved";
    saveLocal();
    toast(state.meta?.public ? "Plan saved in this browser. Use Export to move it to another device." : "Plan saved to your local database.");
  } catch (error) { toast(error.message); }
}

async function openPlans() {
  const dialog = $("#plansDialog");
  const list = $("#plansList");
  list.innerHTML = `<p class="subtle">Loading…</p>`;
  dialog.showModal();
  const plans = state.meta?.public ? browserPlans().map(p => ({ id: p.id, name: p.name, updated_at: p.savedAt }))
    : await api("/api/plans").catch(() => []);
  list.innerHTML = plans.map(p => `<button type="button" class="result" data-plan="${esc(p.id)}"><div><b>${esc(p.name)}</b><small>Saved ${new Date(p.updated_at).toLocaleString()}</small></div><div class="right">Open</div></button>`).join("")
    || `<p class="subtle">No saved plans yet.${state.meta?.public ? " Plans you save here stay in this browser." : ""}</p>`;
  $$("[data-plan]", list).forEach(btn => btn.addEventListener("click", async () => {
    const data = state.meta?.public ? browserPlans().find(p => p.id === btn.dataset.plan) : await api(`/api/plans/${enc(btn.dataset.plan)}`);
    if (data) loadSnapshot(data);
    dialog.close();
  }));
}

function loadSnapshot(data) {
  state.settings = { ...defaultSettings(), ...(data.settings || {}) };
  state.plan = data.terms?.length ? { terms: data.terms, unscheduled: data.unscheduled || [] } : null;
  state.planId = data.id || null;
  renderSetup();
  if (state.plan) { renderBoard(); validateSoon(0); }
  showView("plan");
  toast(`Opened “${data.name || "plan"}”.`);
}

function exportPlan() {
  if (!state.plan) return toast("Build a plan before exporting.");
  const blob = new Blob([JSON.stringify(snapshot(), null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "badgerplan.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

async function importPlan(e) {
  const file = e.target.files?.[0];
  if (!file) return;
  try { loadSnapshot(JSON.parse(await file.text())); $("#plansDialog").close(); }
  catch { toast("That file is not a BadgerPlan export."); }
  e.target.value = "";
}

function markDirty() {
  state.dirty = true;
  $("#saveStatus").textContent = "Unsaved changes";
  saveLocal();
}

function saveLocal() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(snapshot())); } catch { /* storage unavailable */ }
}

function restoreLocal() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    state.settings = { ...defaultSettings(), ...(data.settings || {}) };
    state.settings.majors = (state.settings.majors || []).filter(m => !m.id || state.programs.some(p => p.id === m.id));
    if (!data.settings?.yearInSchool) {
      // Plans saved before "Where are you now?" existed: infer it from the first term.
      const now = TX.currentTerm(), s = state.settings;
      const years = (now.season === "Fall" ? now.year : now.year - 1) - s.startYear;
      s.yearInSchool = TX.termKey({ season: s.startSeason, year: s.startYear }) > TX.termKey(now) ? "incoming" : STANDINGS[Math.max(0, Math.min(3, years))];
    }
    if (data.terms?.length) state.plan = { terms: data.terms, unscheduled: data.unscheduled || [] };
    state.planId = data.id || null;
    $("#saveStatus").textContent = data.id ? "Restored" : "Restored draft";
  } catch { /* ignore */ }
}

let toastTimer;
// ------------------------------------------------------------------ application shell
async function init() {
  buildYearSelects();
  bindSetup();
  bindTopActions();
  bindRouter();
  bindHomeSearch();
  bindTranscriptImport();
  bindExplore();
  bindProfessorSearch();
  bindDoubleSearch();
  bindMobileSettings();
  $("#drawerClose").addEventListener("click", closeDrawer);
  $("#scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { closeDrawer(); closeMenu(); closeSettings(); }
  });
  document.addEventListener("click", e => {
    if (!e.target.closest(".card-menu") && !e.target.closest(".menu-btn")) closeMenu();
  });

  try {
    const [meta, programs, departments] = await Promise.all([api("/api/meta"), api("/api/programs"), api("/api/departments")]);
    state.meta = meta;
    state.programs = programs;
    state.departments = departments;
    $("#catalogBadge").textContent = `${meta.catalog_year} catalog · ${meta.stats.courses.toLocaleString()} courses · ${meta.stats.programs} majors`;
    Object.entries(meta.tags).forEach(([tag, label]) => $("#exploreTag").add(new Option(label, tag)));
    departments.forEach(row => $("#exploreDepartment").add(new Option(`${row.name} (${row.courses})`, row.id)));
  } catch (error) {
    toast(`Could not load catalog: ${error.message}`);
    return;
  }
  restoreLocal();
  renderSetup();
  renderPrograms("");
  if (state.plan) { renderBoard(); validateSoon(0); }
  if (!state.settings.majors.length) addMajorRow();
  renderRoute();
  renderHome();
  $("#datesIcs").addEventListener("click", downloadDatesIcs);
}

function bindRouter() {
  document.addEventListener("click", e => {
    const link = e.target.closest("a[data-route]");
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(link.getAttribute("href"));
  });
  window.addEventListener("popstate", renderRoute);
}

function navigate(url, replace = false) {
  const target = new URL(url, location.origin);
  history[replace ? "replaceState" : "pushState"]({}, "", target.pathname + target.search);
  closeDrawer();
  closeSettings();
  renderRoute();
  window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

function renderRoute() {
  const path = location.pathname.replace(/\/$/, "") || "/";
  let view = "home", area = "home";
  if (path === "/plan") { view = "plan"; area = "plan"; }
  else if (path === "/plan/requirements") { view = "audit"; area = "plan"; renderAudit(); }
  else if (path === "/plan/double-major") { view = "double"; area = "plan"; renderDouble(); }
  else if (path === "/plan/schedule") { view = "schedule"; area = "plan"; renderSchedule(); }
  else if (path === "/plan/dates") { view = "dates"; area = "plan"; renderDates(); }
  else if (path === "/explore/professors") { view = "professors"; area = "explore"; runProfessorSearch(); }
  else if (path === "/explore/majors") { view = "majors"; area = "explore"; }
  else if (path.startsWith("/courses/")) { view = "course"; area = "explore"; renderCoursePage(decodeURIComponent(path.slice(9))); }
  else if (path.startsWith("/professors/")) { view = "professor"; area = "explore"; renderProfessorPage(decodeURIComponent(path.slice(12))); }
  else if (path.startsWith("/majors/")) { view = "major"; area = "explore"; renderMajorPage(decodeURIComponent(path.slice(8))); }
  else if (path.startsWith("/explore")) { view = "explore"; area = "explore"; syncExploreFromUrl(); runExploreSearch(); }
  else if (path !== "/") { navigate("/", true); return; }
  document.body.dataset.area = area;
  document.body.dataset.view = view;
  if (view === "home") renderHome();
  $$(".view").forEach(node => node.classList.toggle("active", node.id === `view-${view}`));
  syncChrome();
  $("#planNav").classList.toggle("hidden", area !== "plan");
  $("#exploreNav").classList.toggle("hidden", area !== "explore");
  $$(".primary-nav a").forEach(a => a.classList.toggle("active", a.dataset.nav === area));
  $$(".context-nav a").forEach(a => a.classList.toggle("active", new URL(a.href).pathname === path));
  document.title = `${routeTitle(view)} · BadgerPlan`;
}

function routeTitle(view) {
  return ({ home: "UW academic planning", plan: "Degree plan", audit: "Requirements", double: "Double major", schedule: "Next term schedule", dates: "Key dates", explore: "Explore courses", professors: "Professors", majors: "Majors", course: "Course", professor: "Professor", major: "Major" })[view] || "BadgerPlan";
}

function showView(view) {
  const routes = { plan: "/plan", audit: "/plan/requirements", double: "/plan/double-major", schedule: "/plan/schedule", dates: "/plan/dates", explore: "/explore/courses", programs: "/explore/majors", home: "/" };
  navigate(routes[view] || "/");
}

const DESKTOP = matchMedia("(min-width: 64rem)");
function bindMobileSettings() {
  ["openSettings", "emptySettings"].forEach(id => $(`#${id}`)?.addEventListener("click", openSettings));
  $("#closeSettings").addEventListener("click", closeSettings);
  $("#settingsScrim").addEventListener("click", closeSettings);
  DESKTOP.addEventListener("change", syncChrome);
}
function openSettings() { document.body.classList.add("settings-open"); syncChrome(); $("#closeSettings").focus(); }
function closeSettings() {
  const wasOpen = document.body.classList.contains("settings-open");
  document.body.classList.remove("settings-open");
  syncChrome();
  if (wasOpen && !DESKTOP.matches) $("#openSettings")?.focus();
}

// Keeps page chrome in step with state: the settings panel is only reachable
// where it is visible, and plan actions only appear once a plan exists.
function syncChrome() {
  const onPlan = document.body.dataset.view === "plan";
  const open = document.body.classList.contains("settings-open");
  const visible = (DESKTOP.matches && onPlan) || open;
  $("#setup").inert = !visible;
  $("#setup").setAttribute("aria-hidden", String(!visible));
  document.body.classList.toggle("has-plan", !!state.plan);
}

let homeTimer;
function bindHomeSearch() {
  const input = $("#homeSearch");
  input.addEventListener("input", () => { clearTimeout(homeTimer); homeTimer = setTimeout(runHomeSearch, 160); });
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && input.value.trim()) { e.preventDefault(); navigate(`/explore/courses?q=${enc(input.value.trim())}`); }
    if (e.key === "Escape") closeHomeResults();
  });
  input.addEventListener("blur", () => setTimeout(closeHomeResults, 180));
}

async function runHomeSearch() {
  const input = $("#homeSearch"), box = $("#homeSearchResults"), q = input.value.trim();
  if (q.length < 2) { closeHomeResults(); return; }
  try {
    const data = await api(`/api/search?q=${enc(q)}`);
    const groups = data.groups || [];
    box.innerHTML = groups.filter(group => group.results.length).map(group =>
      `<div class="result-group-title">${esc(group.label)}</div>${group.results.map(result => `<a class="search-result" href="${esc(result.href)}" data-route role="option"><strong>${esc(result.title)}</strong><small>${esc(result.meta || "")}</small></a>`).join("")}`
    ).join("") || `<div class="combo-item">No exact match. Press Enter to search the full catalog.</div>`;
    box.classList.remove("hidden"); input.setAttribute("aria-expanded", "true");
  } catch (error) { box.innerHTML = `<div class="combo-item">${esc(error.message)}</div>`; box.classList.remove("hidden"); }
}
function closeHomeResults() { $("#homeSearchResults").classList.add("hidden"); $("#homeSearch").setAttribute("aria-expanded", "false"); }

function renderHome() {
  const block = $("#continuePlan");
  block.classList.toggle("hidden", !state.plan);
  $("#glanceStart").textContent = state.plan ? "Open your plan" : "Start a plan";
  if (state.meta) {
    const st = state.meta.stats, n = v => Number(v || 0).toLocaleString();
    $("#glanceStats").innerHTML = [[st.courses, "Courses in the catalog"], [st.programs, "Majors & named options"], [st.courses_with_grades, "Courses with grade history"], [st.instructors_with_rmp, "Instructors with RMP data"]]
      .map(([v, label]) => `<div><dt>${esc(label)}</dt><dd>${n(v)}</dd></div>`).join("");
    renderSources();
  }
  initCampusMap();
  loadTimeline().then(renderHomeDates);
  if (!state.plan) return;
  const names = state.settings.majors.filter(m => m.id).map(m => state.programs.find(p => p.id === m.id)?.name).filter(Boolean);
  const creditsPlanned = state.validation?.audit?.credits?.planned ?? state.plan.terms.reduce((sum, term) => sum + termCredits(term), 0);
  const conflicts = Object.values(state.validation?.issues || {}).flat().filter(i => i.level === "error").length;
  $("#continueName").textContent = names.join(" + ") || "My degree plan";
  $("#continueMeta").textContent = `${state.settings.startSeason} ${state.settings.startYear} to ${state.settings.gradSeason} ${state.settings.gradYear}`;
  $("#continueStatus").innerHTML = `<span><strong>${creditsPlanned}</strong> planned credits</span><span><strong>${conflicts}</strong> conflict${conflicts === 1 ? "" : "s"}</span>`;
}

function renderSources() {
  const grid = $("#sourceGrid");
  if (grid.dataset.ready) return;
  const extra = [{ name: "OpenStreetMap", url: "https://www.openstreetmap.org/copyright", authority: "community", license: "ODbL", use: "Building outlines on the campus map" }];
  grid.innerHTML = [...(state.meta.sources || []), ...extra].map(src => `<article class="source-card">
      <span class="source-kind ${src.authority === "official" ? "official" : ""}">${src.authority === "official" ? "Official" : "Community data"}${src.license ? ` · ${esc(src.license)}` : ""}</span>
      <h3><a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(src.name)}</a></h3><p>${esc(src.use)}</p></article>`).join("");
  grid.dataset.ready = "1";
  $("#footerMeta").textContent = `${state.meta.catalog_year} catalog snapshot · data built ${new Date(state.meta.built_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}`;
}

// ------------------------------------------------------------------ campus map
// Static SVG built by scripts/build_campus_map.py: one teaching week of class
// meetings per building. No tiles or API keys, so it also works offline.
const campus = { data: null, loading: false, mode: "now", day: 1, hour: 2, selected: -1, timer: null, max: {} };
const DAY_NAMES = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday" };

async function initCampusMap() {
  if (campus.data || campus.loading) return;
  campus.loading = true;
  try {
    const response = await fetch("/static/campus-map.json");
    if (!response.ok) throw new Error(response.status);
    campus.data = await response.json();
  } catch {
    $("#campusMap").innerHTML = `<p class="subtle">The campus map could not be loaded. Run <code>python scripts/build_campus_map.py</code> to create it.</p>`;
    return;
  } finally { campus.loading = false; }
  const d = campus.data, now = new Date();
  if (now.getDay() >= 1 && now.getDay() <= 5) campus.day = now.getDay() - 1;
  const slot = d.hours.indexOf(now.getHours());
  if (slot >= 0) campus.hour = slot;
  campus.max.week = Math.max(...d.buildings.map(b => b.meetings));
  campus.max.now = Math.max(...d.buildings.flatMap(b => b.occupancy.flat()));
  $("#campusSub").textContent = `Every scheduled class meeting in the ${d.term} week of ${d.week}, placed on the building where it meets. Hover or tap a building to see what is taught there; drag the time slider to watch campus fill up and empty out.`;
  $("#campusDays").innerHTML = d.days.map((day, i) => `<button type="button" class="seg" data-day="${i}" role="radio" aria-label="${DAY_NAMES[day] || day}">${day}</button>`).join("");
  $("#campusHour").max = d.hours.length - 1;
  $("#campusHour").value = campus.hour;
  const paths = d.buildings.map((b, i) => `<path class="bldg" d="${b.path}" data-i="${i}" tabindex="0" role="button" aria-label="${esc(b.name)}"></path>`).join("");
  $("#campusMap").innerHTML = `<svg viewBox="0 0 ${d.width} ${d.height}" role="group" aria-label="Map of UW–Madison teaching buildings">
    <rect class="campus-ground" width="${d.width}" height="${d.height}"></rect>
    <g class="campus-north" transform="translate(${d.width - 34},34)" aria-hidden="true"><circle r="16"></circle><path d="M0,-11 L5,4 L0,1 L-5,4Z"></path><text y="-19" text-anchor="middle">N</text></g>
    <g class="bldgs">${paths}</g><g class="bldg-labels" aria-hidden="true"></g></svg>`;
  const core = d.buildings.filter(x => x.meetings >= 25);
  const xs = core.map(x => x.label[0]), ys = core.map(x => x.label[1]);
  const x0 = Math.max(0, Math.min(...xs) - 70), x1 = Math.min(d.width, Math.max(...xs) + 70);
  const y0 = Math.max(0, Math.min(...ys) - 55), y1 = Math.min(d.height, Math.max(...ys) + 55);
  campus.views = { central: [x0, y0, x1 - x0, y1 - y0], all: [0, 0, d.width, d.height] };
  campus.view = "central";
  $("#campusMap").insertAdjacentHTML("beforeend", `<div class="map-view-toggle" role="group" aria-label="Map extent"><button type="button" class="btn small" data-view="central" aria-pressed="true">Central campus</button><button type="button" class="btn small" data-view="all" aria-pressed="false">Whole campus</button></div>`);
  $(".map-view-toggle").addEventListener("click", e => { const btn = e.target.closest("[data-view]"); if (btn) setCampusView(btn.dataset.view); });
  setCampusView("central");
  bindCampus();
  paintCampus();
}

function setCampusView(name) {
  campus.view = name;
  const [x, y, w, h] = campus.views[name], svg = $("#campusMap svg");
  svg.setAttribute("viewBox", `${x} ${y} ${w} ${h}`);
  const k = w / campus.data.width;
  $(".campus-north").setAttribute("transform", `translate(${x + w - 30 * k},${y + 30 * k}) scale(${k})`);
  $(".campus-ground").setAttribute("x", x); $(".campus-ground").setAttribute("y", y);
  $(".campus-ground").setAttribute("width", w); $(".campus-ground").setAttribute("height", h);
  $$(".map-view-toggle [data-view]").forEach(btn => btn.setAttribute("aria-pressed", String(btn.dataset.view === name)));
  svg.style.setProperty("--map-scale", (w / campus.data.width).toFixed(3));
  hideCampusTip();
}

function bindCampus() {
  const map = $("#campusMap"), figure = $(".campus-figure");
  const target = e => e.target.closest?.(".bldg");
  map.addEventListener("pointermove", e => { const el = target(e); if (el) showCampusTip(Number(el.dataset.i), e.clientX, e.clientY); else hideCampusTip(); });
  map.addEventListener("pointerleave", hideCampusTip);
  map.addEventListener("click", e => { const el = target(e); if (el) selectBuilding(Number(el.dataset.i)); });
  map.addEventListener("keydown", e => {
    const el = target(e);
    if (el && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); selectBuilding(Number(el.dataset.i)); }
    if (e.key === "Escape") { selectBuilding(-1); hideCampusTip(); }
  });
  map.addEventListener("focusin", e => {
    const el = target(e); if (!el) return;
    const box = el.getBoundingClientRect();
    showCampusTip(Number(el.dataset.i), box.left + box.width / 2, box.top + box.height / 2);
  });
  map.addEventListener("focusout", hideCampusTip);
  figure.addEventListener("scroll", hideCampusTip, { passive: true });
  $$(".campus-mode .seg").forEach(btn => btn.addEventListener("click", () => { campus.mode = btn.dataset.mode; stopCampusPlay(); paintCampus(); }));
  $("#campusDays").addEventListener("click", e => { const btn = e.target.closest("[data-day]"); if (btn) { campus.day = Number(btn.dataset.day); paintCampus(); } });
  $("#campusHour").addEventListener("input", e => { campus.hour = Number(e.target.value); paintCampus(); });
  $("#campusPlay").addEventListener("click", () => campus.timer ? stopCampusPlay() : startCampusPlay());
  const input = $("#campusSearch"), list = $("#campusSearchResults");
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    const hits = q ? campus.data.buildings.map((b, i) => [b, i]).filter(([b]) => b.name.toLowerCase().includes(q) || b.address.toLowerCase().includes(q)).slice(0, 8) : [];
    list.innerHTML = hits.map(([b, i]) => `<button type="button" class="combo-item" data-id="${i}">${esc(b.name)}<small>${esc(b.address || `${b.meetings} classes this week`)}</small></button>`).join("") || (q ? `<div class="combo-item">No teaching building matches.</div>` : "");
    list.classList.toggle("hidden", !q);
  });
  input.addEventListener("keydown", e => comboKeys(e, list));
  input.addEventListener("blur", () => setTimeout(() => list.classList.add("hidden"), 180));
  list.addEventListener("mousedown", e => {
    const btn = e.target.closest("[data-id]"); if (!btn) return;
    e.preventDefault(); input.value = ""; list.classList.add("hidden");
    selectBuilding(Number(btn.dataset.id), true);
  });
  $("#campusPanel").addEventListener("click", e => {
    const pick = e.target.closest("[data-building]");
    if (pick) selectBuilding(Number(pick.dataset.building), true);
    const hour = e.target.closest("[data-hour]");
    if (hour) { campus.mode = "now"; campus.hour = Number(hour.dataset.hour); paintCampus(); }
    if (e.target.closest("[data-clear-building]")) selectBuilding(-1);
    if (e.target.closest("[data-show-all]")) { campus.showAll = true; renderCampusPanel(); }
  });
}

function startCampusPlay() {
  campus.mode = "now";
  if (campus.hour >= campus.data.hours.length - 1) campus.hour = 0;
  $("#campusPlay").setAttribute("aria-label", "Pause");
  $("#campusPlay").innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5h3v14H8zM13 5h3v14h-3z"/></svg>`;
  paintCampus();
  campus.timer = setInterval(() => {
    if (campus.hour >= campus.data.hours.length - 1) return stopCampusPlay();
    campus.hour += 1; paintCampus();
  }, 900);
}
function stopCampusPlay() {
  clearInterval(campus.timer); campus.timer = null;
  $("#campusPlay").setAttribute("aria-label", "Play through the day");
  $("#campusPlay").innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>`;
}

const hourLabel = h => `${((h + 11) % 12) + 1}:30 ${h < 12 ? "AM" : "PM"}`;
function campusValue(b) { return campus.mode === "week" ? b.meetings : b.occupancy[campus.day][campus.hour]; }
function campusLevel(value) {
  if (!value) return 0;
  const share = value / (campus.max[campus.mode] || 1);
  return share > 0.55 ? 5 : share > 0.3 ? 4 : share > 0.15 ? 3 : share > 0.06 ? 2 : 1;
}
function campusMetric(b) {
  const v = campusValue(b);
  if (campus.mode === "week") return `${v.toLocaleString()} class meeting${v === 1 ? "" : "s"} this week`;
  return v ? `${v.toLocaleString()} students in class at ${hourLabel(campus.data.hours[campus.hour])} ${campus.data.days[campus.day]}` : `No classes at ${hourLabel(campus.data.hours[campus.hour])} ${campus.data.days[campus.day]}`;
}

function paintCampus() {
  const d = campus.data;
  $$(".campus-mode .seg").forEach(btn => { const on = btn.dataset.mode === campus.mode; btn.classList.toggle("active", on); btn.setAttribute("aria-checked", String(on)); });
  $$("#campusDays .seg").forEach(btn => { const on = Number(btn.dataset.day) === campus.day; btn.classList.toggle("active", on); btn.setAttribute("aria-checked", String(on)); });
  const timed = campus.mode === "now";
  $("#campusDays").classList.toggle("is-off", !timed);
  $("#campusTime").classList.toggle("is-off", !timed);
  $("#campusHour").value = campus.hour;
  $("#campusHourLabel").textContent = `${hourLabel(d.hours[campus.hour])}`;
  $$(".bldg").forEach(el => {
    const i = Number(el.dataset.i), b = d.buildings[i];
    el.setAttribute("class", `bldg lv${campusLevel(campusValue(b))}${i === campus.selected ? " selected" : ""}`);
    el.setAttribute("aria-label", `${b.name}: ${campusMetric(b)}`);
    el.setAttribute("aria-pressed", String(i === campus.selected));
  });
  const sel = d.buildings[campus.selected];
  $(".bldg-labels").innerHTML = sel ? `<text x="${sel.label[0]}" y="${sel.label[1] - 14}" text-anchor="middle">${esc(sel.name)}</text>` : "";
  const unit = timed ? "students in class" : "class meetings / week";
  $("#campusLegend").innerHTML = `<span>Fewer</span>${[1, 2, 3, 4, 5].map(l => `<i class="lv${l}"></i>`).join("")}<span>More ${unit}</span>`;
  renderCampusPanel();
}

function showCampusTip(i, x, y) {
  const b = campus.data.buildings[i], tip = $("#campusTip"), figure = $(".campus-figure").getBoundingClientRect();
  tip.innerHTML = `<strong>${esc(b.name)}</strong>${b.address ? `<small>${esc(b.address)}</small>` : ""}
    <span class="tip-metric">${esc(campusMetric(b))}</span>
    <span>${b.meetings} classes · ${b.courses} courses this week</span>
    ${b.departments.length ? `<span class="tip-depts">${b.departments.map(esc).join(" · ")}</span>` : ""}
    ${b.top.length ? `<span class="tip-top">Largest: ${b.top.slice(0, 3).map(c => esc(c.code)).join(", ")}</span>` : ""}
    <em>Click for details</em>`;
  tip.classList.remove("hidden");
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let left = x - figure.left + 14, top = y - figure.top + 14;
  if (left + w > figure.width) left = Math.max(4, x - figure.left - w - 14);
  if (top + h > figure.height) top = Math.max(4, y - figure.top - h - 14);
  tip.style.left = `${left}px`; tip.style.top = `${top}px`;
}
function hideCampusTip() { $("#campusTip")?.classList.add("hidden"); }

function selectBuilding(i, reveal = false) {
  campus.selected = campus.selected === i && !reveal ? -1 : i;
  campus.showAll = false;
  hideCampusTip();
  paintCampus();
  if (reveal && campus.selected >= 0 && campus.view === "central") {
    const [x, y, w, h] = campus.views.central, [lx, ly] = campus.data.buildings[i].label;
    if (lx < x || lx > x + w || ly < y || ly > y + h) setCampusView("all");
  }
  if (reveal && campus.selected >= 0) {
    $(`.bldg[data-i="${i}"]`)?.focus({ preventScroll: true });
    if (!DESKTOP.matches) $("#campusPanel").scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function renderCampusPanel() {
  const d = campus.data, panel = $("#campusPanel"), b = d.buildings[campus.selected];
  if (!b) {
    const ranked = d.buildings.map((x, i) => [x, i, campusValue(x)]).filter(r => r[2]).sort((a, z) => z[2] - a[2]).slice(0, 8);
    const top = ranked[0]?.[2] || 1;
    const when = campus.mode === "week" ? "this week" : `at ${hourLabel(d.hours[campus.hour])} on ${DAY_NAMES[d.days[campus.day]]}`;
    panel.innerHTML = `<h3>Busiest buildings ${esc(when)}</h3>
      ${ranked.length ? `<ol class="rank-list">${ranked.map(([x, i, v]) => `<li><button type="button" data-building="${i}"><span>${esc(x.name)}</span><b>${v.toLocaleString()}</b><i style="width:${Math.round(100 * v / top)}%"></i></button></li>`).join("")}</ol>` : `<p class="subtle">No classes are scheduled at this time.</p>`}
      <p class="source-note">${campus.mode === "week" ? "Number of class meetings (lectures, discussions, labs) in the week." : "Sum of enrollment in sections meeting at that time."} ${d.buildings.length} teaching buildings shown.</p>`;
    return;
  }
  const occ = b.occupancy[campus.day], peak = Math.max(1, ...occ);
  const bars = occ.map((v, h) => `<button type="button" data-hour="${h}" class="${h === campus.hour && campus.mode === "now" ? "now" : ""}" aria-label="${hourLabel(d.hours[h])}: ${v} students"><i style="height:${Math.max(2, Math.round(100 * v / peak))}%"></i><span>${h % 3 === 0 ? ((d.hours[h] + 11) % 12) + 1 : ""}</span></button>`).join("");
  const courses = campus.showAll ? b.all : b.all.slice(0, 18);
  panel.innerHTML = `<div class="panel-title"><div><h3>${esc(b.name)}</h3>${b.address ? `<p class="subtle">${esc(b.address)}</p>` : ""}</div><button type="button" class="icon-btn" data-clear-building aria-label="Close building details"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
    <dl class="building-facts"><div><dt>Class meetings</dt><dd>${b.meetings}</dd></div><div><dt>Courses</dt><dd>${b.courses}</dd></div><div><dt>Rooms in use</dt><dd>${b.rooms}</dd></div></dl>
    <h4>${esc(DAY_NAMES[d.days[campus.day]])}, students in class by hour</h4><div class="hour-bars" role="group" aria-label="Students in class by hour">${bars}</div>
    ${b.departments.length ? `<h4>Main departments</h4><div class="d-row">${b.departments.map(x => `<span class="badge">${esc(x)}</span>`).join("")}</div>` : ""}
    <h4>Courses meeting here <small class="subtle">(largest section first)</small></h4>
    <ul class="building-courses">${courses.map(([code, size, inCatalog]) => `<li>${inCatalog ? `<a href="/courses/${enc(code)}" data-route>${esc(code)}</a>` : `<span>${esc(code)}</span>`}<small>${size ? `${size} enrolled` : ""}</small></li>`).join("")}</ul>
    ${!campus.showAll && b.all.length > courses.length ? `<button type="button" class="text-action" data-show-all>Show all ${b.all.length} courses</button>` : ""}`;
}

function bindExplore() {
  let timer;
  $("#exploreForm").addEventListener("submit", e => { e.preventDefault(); updateExploreUrl(); });
  $$("#exploreForm input, #exploreForm select").forEach(control => control.addEventListener(control.type === "search" ? "input" : "change", () => {
    clearTimeout(timer); timer = setTimeout(updateExploreUrl, control.type === "search" ? 220 : 0);
  }));
  $("#clearFilters").addEventListener("click", () => { $("#exploreForm").reset(); updateFilterCount(); navigate("/explore/courses"); });
  $("#toggleFilters").addEventListener("click", () => setFiltersOpen($("#moreFilters").classList.contains("hidden")));
  $("#programSearch").addEventListener("input", e => renderPrograms(e.target.value));
  $("#exploreResults").addEventListener("click", e => {
    const add = e.target.closest("[data-add-code]");
    if (!add) return;
    const row = state.exploreRows?.find(r => r.code === add.dataset.addCode);
    if (row) addToPlan(row, Number(add.dataset.term));
    e.target.closest("details")?.removeAttribute("open");
  });
}

const ADVANCED_FILTERS = ["exploreCredits", "exploreReq", "exploreDepth", "exploreGpa", "exploreSample", "exploreFrequency", "exploreInstructor"];
function setFiltersOpen(open) {
  $("#moreFilters").classList.toggle("hidden", !open);
  $("#toggleFilters").setAttribute("aria-expanded", String(open));
}
function updateFilterCount() {
  const active = ADVANCED_FILTERS.filter(id => $(`#${id}`).value.trim()).length;
  $("#filterCount").textContent = active;
  $("#filterCount").classList.toggle("hidden", !active);
  return active;
}

function syncExploreFromUrl() {
  const p = new URLSearchParams(location.search);
  const map = { q: "exploreSearch", department: "exploreDepartment", credits: "exploreCredits", tag: "exploreTag", requisites: "exploreReq", gpa_min: "exploreGpa", grade_count_min: "exploreSample", season: "exploreSeason", frequency: "exploreFrequency", instructor: "exploreInstructor" };
  Object.entries(map).forEach(([key, id]) => { $(`#${id}`).value = p.get(key) || ""; });
  const min = p.get("level_min"), max = p.get("level_max");
  $("#exploreLevel").value = min && max ? `${min}-${max}` : "";
  const prereqMin = p.get("prerequisite_count_min"), prereqMax = p.get("prerequisite_count_max");
  $("#exploreDepth").value = prereqMin && prereqMax ? `${prereqMin}-${prereqMax}` : "";
  if (updateFilterCount()) setFiltersOpen(true);
}

function updateExploreUrl() {
  const p = new URLSearchParams(), put = (k, v) => { if (v) p.set(k, v); };
  put("q", $("#exploreSearch").value.trim()); put("department", $("#exploreDepartment").value); put("credits", $("#exploreCredits").value);
  put("tag", $("#exploreTag").value); put("requisites", $("#exploreReq").value); put("gpa_min", $("#exploreGpa").value); put("grade_count_min", $("#exploreSample").value);
  put("season", $("#exploreSeason").value); put("frequency", $("#exploreFrequency").value);
  put("instructor", $("#exploreInstructor").value.trim());
  if ($("#exploreLevel").value) { const [min, max] = $("#exploreLevel").value.split("-"); put("level_min", min); put("level_max", max); }
  if ($("#exploreDepth").value) { const [min, max] = $("#exploreDepth").value.split("-"); put("prerequisite_count_min", min); put("prerequisite_count_max", max); }
  if (new URLSearchParams(location.search).get("mode") === "easiest") put("mode", "easiest");
  updateFilterCount();
  history.replaceState({}, "", `/explore/courses${p.size ? `?${p}` : ""}`);
  runExploreSearch();
}

function interpretExploreQuery(value) {
  const notes = [];
  if (/\beasy|easiest\b/i.test(value)) notes.push("“easy” is interpreted as evidence-led high historical outcomes; no synthetic difficulty score is used.");
  if (/\bonline|hybrid|in[ -]?person\b/i.test(value)) notes.push("Instruction mode is not available in this snapshot, so it cannot be applied as a filter.");
  return notes;
}

async function runExploreSearch() {
  const p = new URLSearchParams(location.search), easiest = p.get("mode") === "easiest";
  const notes = interpretExploreQuery(p.get("q") || "");
  $("#queryInterpretation").classList.toggle("hidden", !notes.length);
  $("#queryInterpretation").innerHTML = notes.map(n => `<span>${esc(n)}</span>`).join("");
  $("#easiestNote").classList.toggle("hidden", !easiest);
  p.delete("mode"); p.set("limit", "60");
  state.settings.majors.filter(m => m.id).forEach(m => p.append("program", m.id));
  $("#exploreSummary").textContent = "Searching the local catalog…";
  try {
    const rows = await api(`${easiest ? "/api/discovery/easiest" : "/api/courses"}?${p}`);
    state.exploreRows = rows;
    $("#exploreSummary").textContent = `${rows.length} course${rows.length === 1 ? "" : "s"}${easiest ? " with adequate historical evidence" : ""}. Historical results are descriptive, not guarantees.`;
    $("#exploreResults").innerHTML = rows.map(courseRowHtml).join("") || `<tr><td colspan="7"><div class="empty-state"><h2>No matching courses</h2><p>Remove a filter or try a course code, topic, or instructor name.</p></div></td></tr>`;
  } catch (error) { $("#exploreResults").innerHTML = `<tr><td colspan="7">${esc(error.message)}</td></tr>`; }
}

function courseRowHtml(r) {
  const fit = planFit(r), sample = r.grade_count ? `${Number(r.avg_gpa).toFixed(2)} GPA · ${r.grade_count.toLocaleString()} grades${r.df_rate != null ? ` · ${r.df_rate}% D/F` : ""}` : "No grade history";
  const req = r.prerequisite_count ? `${r.prerequisite_count} prerequisite course${r.prerequisite_count === 1 ? "" : "s"}` : r.requisite_tree ? "Standing, placement or consent" : "None";
  const offerings = (r.offered_seasons || []).length ? `${r.offered_seasons.join(" / ")} · ${r.offering_frequency || "history varies"}` : "Unknown";
  return `<tr>
    <td data-label="Course"><span class="course-code">${esc(r.code)}</span></td>
    <td data-label="Title"><a class="course-title" href="/courses/${enc(r.code)}" data-route>${esc(r.title)}</a>${fit ? `<span class="fit">${esc(fit)}</span>` : ""}${r.peer_percentile != null ? `<span class="fit">Higher than ${r.peer_percentile}% of ${esc(r.peer_group)} peers in this result cohort</span>` : ""}</td>
    <td data-label="Credits" class="num">${credits(r)}</td><td data-label="Historical grades">${esc(sample)}</td><td data-label="Prerequisites">${esc(req)}</td><td data-label="Usually offered">${esc(offerings)}</td>
    <td class="actions">${addMenuHtml(r)}</td></tr>`;
}

function planFit(row) {
  if (!state.plan) return "";
  if (findCard(row.code) || state.settings.prior.some(p => p.code === row.code)) return "Already in your plan";
  const matches = row.requirement_matches || [];
  if (matches.length) return `Matches ${[...new Set(matches.map(m => m.block_name))].slice(0, 2).join("; ")}`;
  const before = coursesBefore(state.plan.terms.length), prereqs = collectTreeCourses(row.requisite_tree);
  if (prereqs.length && prereqs.every(code => before.has(code))) return "Listed course prerequisites appear covered";
  return "Not listed in your majors' requirements (counts as an elective)";
}
function coursePlanFitHtml(d) {
  const programs = d.required_by || [];
  const mine = programs.filter(r => state.settings.majors.some(m => m.id === r.id));
  const listed = programs.length ? `Listed in the requirements of ${programs.length}${programs.length >= 60 ? "+" : ""} major${programs.length === 1 ? "" : "s"}.` : "Not listed in any major's requirements; it can count as an elective.";
  if (!state.plan) return `<p>${esc(listed)}</p><p class="subtle"><a href="/plan" data-route>Start a plan</a> to see whether it fits your majors and timeline.</p>`;
  const fit = planFit({ ...d, requirement_matches: mine.map(r => ({ block_name: r.block })) });
  return `<p><strong>${esc(fit)}</strong></p><p class="subtle">${esc(listed)}</p>`;
}

// Some older Guide descriptions were stored at a 600-character cap.
function descriptionHtml(d, cls = "") {
  const text = d.description || "";
  if (!text) return `<p class="${cls}">No description in the UW Guide snapshot.</p>`;
  const clipped = text.length >= 598 && text.length <= 601 && !/[.!?)]$/.test(text.trim());
  return `<p class="${cls}">${esc(text)}${clipped ? `… <a href="${esc(d.guide_url)}" target="_blank" rel="noopener">Read the rest in the UW Guide</a>` : ""}</p>`;
}

function collectTreeCourses(node, out = []) { if (!node) return out; if (node.course) out.push(node.course); (node.args || []).forEach(n => collectTreeCourses(n, out)); return out; }
function addMenuHtml(row) {
  if (!state.plan) return "";
  if (findCard(row.code)) return `<span class="badge">In plan</span>`;
  const suggested = earliestTerm(row);
  const options = state.plan.terms.map((t, i) => `<button type="button" data-add-code="${esc(row.code)}" data-term="${i}">${i === suggested ? "Suggested · " : ""}${esc(t.label)}</button>`).join("");
  return `<details class="add-menu"><summary>Add to plan</summary><div>${options}<button type="button" data-add-code="${esc(row.code)}" data-term="-1">Not scheduled yet</button></div></details>`;
}

function bindProfessorSearch() {
  let timer;
  $("#professorSearch").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(runProfessorSearch, 180); });
}
async function runProfessorSearch() {
  const q = $("#professorSearch").value.trim();
  const rows = await api(`/api/instructors?q=${enc(q)}&limit=60`).catch(() => []);
  $("#professorResults").innerHTML = rows.map(r => `<a class="data-row" href="/professors/${enc(r.id)}" data-route><span><strong>${esc(r.display_name)}</strong><small>${esc(r.department || r.position || "UW–Madison")}</small></span><span>${r.course_count} course${r.course_count === 1 ? "" : "s"}${r.rmp_rating != null ? ` · RMP ${rmpCell(r.rmp_rating, r.rmp_count || 0)} <small>(${r.rmp_count || 0} review${r.rmp_count === 1 ? "" : "s"})</small>` : ""}</span></a>`).join("") || `<p class="subtle">No instructors match that name.</p>`;
}

function renderPrograms(query) {
  const q = query.trim().toLowerCase();
  const rows = state.programs.filter(p => !q || `${p.name} ${p.college} ${p.department}`.toLowerCase().includes(q)).slice(0, 100);
  $("#programResults").innerHTML = rows.map(p => `<a class="data-row" href="/majors/${enc(p.id)}" data-route><span><strong>${esc(p.name)}</strong><small>${esc(p.college)}</small></span><span>${p.blocks} requirement groups${p.confidence === "low" || p.confidence === "medium" ? " · verify in Guide" : ""}</span></a>`).join("");
}

async function renderMajorPage(id) {
  $("#majorPage").innerHTML = `<p class="subtle">Loading requirements…</p>`;
  await renderProgramDetail(id, $("#majorPage"));
}
async function renderProgramDetail(id, target = $("#programDetail")) {
  try {
    const p = await program(id), blocks = p.blocks.filter(b => b.rule !== "recommended");
    const ruleText = b => ({ all: "All of", choose: `Choose ${b.count || 1}`, credits: `${b.credits} credits from`, pattern: `${b.credits || ""} credits`, text: "Confirm in Guide" }[b.rule] || b.rule);
    target.innerHTML = `<div class="detail-head"><div><div class="detail-code">MAJOR</div><h1 class="detail-title">${esc(p.name)}</h1><p>${esc(p.college)} · ${esc(state.meta.profiles[p.profile] || "")}</p></div><div class="detail-actions"><button class="btn primary" data-use="${esc(p.id)}">Plan this major</button><a class="btn" href="${esc(p.guide_url)}" target="_blank" rel="noopener">Open UW Guide</a></div></div><div class="detail-sections"><section class="requirement-group"><header><div><h2>Requirements</h2><p>${blocks.length} requirement groups · ${esc({ high: "read directly from the UW Guide", medium: "some rules inferred — verify in the Guide", low: "complex rules — verify in the Guide", none: "choose a named option" }[p.confidence] || "")}</p></div></header>${blocks.map(b => `<div class="req"><span class="icon">${b.section === "college" ? "C" : "M"}</span><div><div class="name">${esc(b.name)}${b.variant ? ` <span class="badge">${esc(b.variant)}</span>` : ""}</div><div class="options-list">${ruleText(b)}: ${b.slots.slice(0, 24).map(s => s.options.length ? s.options.map(o => `<button data-code="${esc(o[0])}">${esc(o.join(" + "))}</button>`).join(" or ") : `<span>${esc(s.label)}</span>`).join("")}</div>${b.notes?.[0] ? `<p class="hint">${esc(b.notes[0]).slice(0, 240)}</p>` : ""}</div><div class="conf">${b.confidence === "low" ? `<span class="pill">verify</span>` : esc(b.confidence)}</div></div>`).join("")}</section></div>`;
    $$('[data-code]', target).forEach(b => b.addEventListener("click", () => navigate(`/courses/${enc(b.dataset.code)}`)));
    $("[data-use]", target)?.addEventListener("click", e => { state.settings.majors[0] = { id: e.currentTarget.dataset.use, variants: {} }; renderMajors(); markDirty(); navigate("/plan"); toast("Major selected. Review settings, then build your plan."); });
  } catch (error) { target.innerHTML = `<div class="empty-state"><h1>Major not found</h1><p>${esc(error.message)}</p></div>`; }
}

async function renderCoursePage(code) {
  const target = $("#coursePage"); target.innerHTML = `<p class="subtle">Loading course evidence…</p>`;
  try {
    const d = await course(code), cumulative = d.grades.find(g => g.term === "cumulative"), placed = termIndexOf(d.code), before = coursesBefore(placed);
    const inPlan = !!findCard(d.code) || state.settings.prior.some(p => p.code === d.code);
    const reqCodes = collectTreeCourses(d.requisite_tree), tags = d.tags.filter(t => t !== "las");
    target.innerHTML = `<a href="/explore/courses" data-route>← Back to course search</a>
      <div class="detail-head"><div><div class="detail-code">${esc(d.code)}</div><h1 class="detail-title">${esc(d.title)}</h1>${descriptionHtml(d)}</div><div><div class="planning-facts"><div class="fact"><b>${credits(d)}</b><span>credits</span></div><div class="fact"><b>${cumulative?.gpa?.toFixed(2) || "—"}</b><span>historical GPA${cumulative ? ` · ${cumulative.total.toLocaleString()} grades` : ""}</span></div><div class="fact"><b>${reqCodes.length || (d.requisite_tree ? "Other" : "None")}</b><span>${reqCodes.length ? `prerequisite course${reqCodes.length === 1 ? "" : "s"}` : d.requisite_tree ? "standing / consent requirement" : "prerequisites"}</span></div><div class="fact"><b>${esc(d.offered_seasons.join(" / ") || "Unknown")}</b><span>${esc(d.offering_frequency || "offering history")}</span></div></div><div class="detail-actions">${inPlan ? `<span class="badge">Already in your plan</span>` : addMenuHtml(d)}<a class="btn" href="${esc(d.guide_url)}" target="_blank" rel="noopener">UW Guide</a></div></div></div>
      <div class="detail-sections"><section class="d-section"><h2>How it counts</h2>${coursePlanFitHtml(d)}<div class="d-row">${tags.map(t => `<span class="badge">${esc(state.meta.tags[t] || t)}</span>`).join("") || `<span class="subtle">No UW designations listed.</span>`}</div></section>
      <section class="d-section"><h2>Prerequisite path</h2><p>${esc(d.requisite_text || "No requisite statement is listed.")}</p><div class="prereq-map"><div class="prereq-node"><strong>Before this course</strong><div class="req-tree">${d.requisite_tree ? treeHtml(d.requisite_tree, before) : `<p class="subtle">No listed prerequisites</p>`}</div></div><div class="prereq-node"><strong>${esc(d.code)}</strong><p>${placed >= 0 ? `Placed in ${esc(state.plan.terms[placed].label)}` : "Not currently scheduled"}</p></div><div class="prereq-node"><strong>Courses this unlocks</strong><div class="d-row">${d.unlocks?.slice(0, 18).map(c => `<a href="/courses/${enc(c)}" data-route class="badge">${esc(c)}</a>`).join("") || `<span class="subtle">No courses list this as a prerequisite</span>`}</div></div></div></section>
      <section class="d-section"><h2>Historical grades</h2>${cumulative ? `${gradeChart(cumulative)}<div class="grade-legend"><span>Average GPA <b>${cumulative.gpa?.toFixed(2) || "—"}</b></span><span>${cumulative.total.toLocaleString()} grades across available terms</span></div>` : `<p class="subtle">No Madgrades history for this course.</p>`}</section>
      <section class="d-section"><h2>Instructors</h2>${instructorTable(d.instructors)}<p class="source-note">Instructor history comes from recent Madgrades records. RMP ratings are third-party student opinions and vary by reviewer and course.</p></section>
      <section class="d-section"><h2>Sources and limitations</h2><p>Catalog description and requisites: UW Guide. Grades: Madgrades. Offerings are historical, not a promise of future availability. Instruction mode and live sections are not present in this snapshot.</p><div class="link-row"><a href="${esc(d.guide_url)}" target="_blank" rel="noopener">UW Guide</a><a href="https://public.enroll.wisc.edu/search?keywords=${enc(d.code)}" target="_blank" rel="noopener">Course Search & Enroll</a><a href="https://madgrades.com/search?query=${enc(d.code)}" target="_blank" rel="noopener">Madgrades</a></div></section></div>`;
    target.onclick = e => { const add = e.target.closest("[data-add-code]"); if (add) addToPlan(d, Number(add.dataset.term)); };
    $$('[data-open]', target).forEach(b => b.addEventListener("click", () => navigate(`/courses/${enc(b.dataset.open)}`)));
  } catch (error) { target.innerHTML = `<div class="empty-state"><h1>Course not found</h1><p>${esc(error.message)}</p></div>`; }
}

async function renderProfessorPage(id) {
  const target = $("#professorPage"); target.innerHTML = `<p class="subtle">Loading instructor history…</p>`;
  try {
    const d = await api(`/api/instructors/${enc(id)}`);
    target.innerHTML = `<a href="/explore/professors" data-route>← Back to professor search</a><div class="detail-head"><div><div class="detail-code">PROFESSOR</div><h1 class="detail-title">${esc(d.display_name)}</h1><p>${esc(d.department || "UW–Madison")} · ${esc(d.position || "Instructor")}</p></div><div class="planning-facts"><div class="fact"><b>${rmpCell(d.rmp_rating, d.rmp_count || 0)}</b><span>RMP rating · ${d.rmp_count || 0} review${d.rmp_count === 1 ? "" : "s"}</span></div><div class="fact"><b>${rmpCell(d.rmp_difficulty, d.rmp_count || 0)}</b><span>RMP difficulty</span></div><div class="fact"><b>${rmpCell(d.rmp_would_take_again, d.rmp_count || 0, 0, "%")}</b><span>would take again</span></div><div class="fact"><b>${d.courses.length}</b><span>courses in history</span></div></div></div><div class="detail-sections"><section class="requirement-group"><header><div><h2>Courses taught</h2><p>Historical teaching records; current assignment may differ.</p></div></header>${d.courses.map(r => `<a class="data-row" href="/courses/${enc(r.code)}" data-route><span><strong>${esc(r.code)} · ${esc(r.title)}</strong><small>${r.terms} term${r.terms === 1 ? "" : "s"} · last ${esc(r.last_term || "unknown")}</small></span><span>${r.avg_gpa ? `course GPA ${Number(r.avg_gpa).toFixed(2)}` : "No grade summary"}</span></a>`).join("")}</section><p class="source-note">Rate My Professors data is third-party opinion data, not an official UW assessment and not course-specific.${(d.rmp_count || 0) < RMP_MIN_REVIEWS && d.rmp_rating != null ? ` * Fewer than ${RMP_MIN_REVIEWS} reviews, so treat these numbers with caution.` : ""}</p></div>`;
  } catch (error) { target.innerHTML = `<div class="empty-state"><h1>Professor not found</h1><p>${esc(error.message)}</p></div>`; }
}

let doubleRows = [];
function bindDoubleSearch() {
  const input = $("#secondMajorSearch"), box = $("#secondMajorResults");
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase(), primary = state.settings.majors[0]?.id;
    const matches = state.programs.filter(p => p.id !== primary && q.length >= 2 && `${p.name} ${p.department || ""}`.toLowerCase().includes(q)).slice(0, 12);
    box.innerHTML = matches.map(p => `<button type="button" class="combo-item" data-compare="${esc(p.id)}"><strong>${esc(p.name)}</strong><small>${esc(p.college)}</small></button>`).join("");
    box.classList.toggle("hidden", !matches.length);
  });
  box.addEventListener("click", e => { const b = e.target.closest("[data-compare]"); if (b) { compareMajor(b.dataset.compare); box.classList.add("hidden"); input.value = state.programs.find(p => p.id === b.dataset.compare)?.name || ""; } });
  $("#doubleSort").addEventListener("change", renderDoubleRows);
}

async function renderDouble() {
  const primary = state.settings.majors[0]?.id, body = $("#doubleBody");
  if (!primary) { body.innerHTML = `<div class="empty-state inline"><h2>Choose your first major</h2><p>Pick a major in plan settings, then come back to see which second majors fit best.</p><a class="btn primary" href="/plan" data-route>Open plan settings</a></div>`; return; }
  body.innerHTML = `<p class="subtle">Comparing requirement lists across available majors…</p>`;
  try { doubleRows = await api(`/api/programs/${enc(primary)}/second-majors`); renderDoubleRows(); }
  catch (error) { body.innerHTML = `<p>${esc(error.message)}</p>`; }
}
function renderDoubleRows() {
  const sort = $("#doubleSort").value, rows = [...doubleRows];
  if (sort === "additional") rows.sort((a, b) => a.additional_credits - b.additional_credits || a.name.localeCompare(b.name));
  else if (sort === "name") rows.sort((a, b) => a.name.localeCompare(b.name));
  else rows.sort((a, b) => b.shared_credits - a.shared_credits || b.percent - a.percent);
  $("#doubleBody").innerHTML = `<div class="double-grid">${rows.map(r => `<div class="dm-row"><div><div class="name">${esc(r.name)}</div><div class="meta">${esc(r.college)} · ${r.shared_courses.length} shared course options</div></div><div><div class="dm-meter"><i style="width:${Math.min(100, r.percent)}%"></i></div><small><b>~${r.additional_credits} extra credits</b> · ~${r.shared_credits} of ${r.second_major_credits} major credits overlap</small></div><button class="btn small" data-compare-row="${esc(r.id)}">Compare</button></div>`).join("")}</div>`;
  $$('[data-compare-row]', $("#doubleBody")).forEach(b => b.addEventListener("click", () => compareMajor(b.dataset.compareRow)));
}
async function compareMajor(secondId) {
  const primary = state.settings.majors[0]?.id;
  if (!primary) return toast("Choose a first major before comparing.");
  const box = $("#majorComparison"); box.innerHTML = `<p class="subtle">Calculating overlap…</p>`;
  try {
    const d = await api(`/api/programs/${enc(primary)}/compare/${enc(secondId)}`);
    box.innerHTML = `<section class="comparison"><div class="section-head"><div><h2>${esc(d.primary.name)} + ${esc(d.secondary.name)}</h2><p class="subtle">Estimate only; school and college double-counting policies may change the result.</p></div><button class="btn primary small" data-add-second="${esc(secondId)}">Add as second major</button></div><div class="comparison-grid"><div class="comparison-stat"><b>${d.percent}%</b><span>estimated requirement overlap</span></div><div class="comparison-stat"><b>${d.shared_credits}</b><span>credits that can count for both</span></div><div class="comparison-stat"><b>${d.additional_credits}</b><span>estimated extra major credits</span></div><div class="comparison-stat"><b>${d.unique_requirements.length}</b><span>requirement blocks with additional work</span></div></div><p>${esc(d.estimate_note)}</p><div class="d-row">${d.shared_courses.slice(0, 24).map(c => `<a class="badge" href="/courses/${enc(c)}" data-route>${esc(c)}</a>`).join("")}</div>${d.manual_requirements.length ? `<p class="source-note">${d.manual_requirements.length} complex requirement group${d.manual_requirements.length === 1 ? "" : "s"} need a manual check in the UW Guide.</p>` : ""}</section>`;
    $('[data-add-second]', box).addEventListener("click", () => { const majors = state.settings.majors.filter(m => m.id); majors[1] = { id: secondId, variants: {} }; state.settings.majors = majors; renderMajors(); markDirty(); toast("Second major added to settings. Your current schedule has not been regenerated."); });
  } catch (error) { box.innerHTML = `<p>${esc(error.message)}</p>`; }
}

function findCard(code) {
  if (!state.plan) return null;
  for (const t of state.plan.terms) { const c = t.courses.find(x => x.code === code); if (c) return c; }
  return state.plan.unscheduled.find(x => x.code === code) || null;
}

function cardHtml(c, termIndex, issues, shared) {
  const own = issues[c.code] || [], errorIssue = own.find(i => i.level === "error"), warnIssue = own.find(i => i.level === "warning"), isShared = shared.has(c.code);
  const kind = c.kind === "prior" ? "prior" : c.placeholder ? "elective" : isShared ? "shared" : c.kind;
  const gpa = c.avgGpa ?? state.courseCache.get(c.code)?.avg_gpa, badges = [`<span class="badge">${c.credits} cr</span>`];
  if (isShared) badges.push(`<span class="badge shared">Both majors</span>`);
  if (gpa) badges.push(`<span class="badge gpa" title="Madgrades average GPA">GPA ${Number(gpa).toFixed(2)}</span>`);
  if (c.locked) badges.push(`<span class="badge lock" title="Pinned to this term">Pinned</span>`);
  if (c.kind === "prior") badges.push(`<span class="badge ${c.status === "in-progress" ? "in-progress" : ""}">${c.status === "completed" && c.grade ? `Grade ${esc(c.grade)}` : { ap: "AP/IB", transfer: "Transfer", completed: "Taken", "in-progress": "In progress" }[c.status] || "Earned"}</span>`);
  const offered = termIndex >= 0 ? state.validation?.offerings?.[c.code] : null;
  if (offered?.offered) badges.push(`<span class="badge confirmed" title="On the published ${esc(state.plan?.terms[termIndex]?.label || "")} schedule in Course Search & Enroll">On schedule</span>`);
  const issue = errorIssue || warnIssue, draggable = c.kind !== "prior";
  const location = termIndex >= 0 ? state.plan?.terms[termIndex]?.label : "not scheduled";
  return `<article class="card ${kind || ""} ${errorIssue ? "has-error" : ""} ${!errorIssue && warnIssue ? "has-warning" : ""}" ${draggable ? `draggable="true"` : ""} data-code="${esc(c.code)}" data-term="${termIndex}" tabindex="0"><div class="code">${c.placeholder ? "Elective" : esc(c.code)}</div><div class="title">${c.placeholder ? "Any course · choose a specific option" : esc(c.title || "")}</div><div class="meta">${badges.join("")}</div>${issue ? `<div class="issue ${issue.level}">${esc(issue.message)}</div>` : ""}${draggable ? `<button type="button" class="menu-btn" aria-label="Move, pin or remove ${esc(c.placeholder ? "elective" : c.code)} (${esc(location)})" aria-haspopup="menu">•••</button>` : ""}</article>`;
}

function bindBoard() {
  $$(".card[draggable]").forEach(card => {
    card.addEventListener("dragstart", e => { dragData = { code: card.dataset.code, from: Number(card.dataset.term) }; e.dataTransfer.setData("text/plain", card.dataset.code); e.dataTransfer.effectAllowed = "move"; requestAnimationFrame(() => card.classList.add("dragging")); });
    card.addEventListener("dragend", () => { card.classList.remove("dragging"); dragData = null; $$(".drag-over").forEach(el => el.classList.remove("drag-over")); });
    card.addEventListener("click", e => {
      if (e.target.closest(".menu-btn")) { openMenu(e, card); return; }
      const c = findCard(card.dataset.code); if (c?.placeholder) openAddDialog(Number(card.dataset.term), c.code); else openDrawer(card.dataset.code);
    });
    card.addEventListener("keydown", e => {
      if (e.key === "Enter" && e.target === card) openDrawer(card.dataset.code);
      if ((e.key === "Delete" || e.key === "Backspace") && e.target === card) removeCourse(card.dataset.code);
    });
  });
  $$(".card.prior").forEach(card => card.addEventListener("click", () => card.dataset.code && openDrawer(card.dataset.code)));
  [...$$(".term[data-term-index]"), $("#trayCourses")].filter(Boolean).forEach(zone => {
    zone.addEventListener("dragover", e => { if (dragData) { e.preventDefault(); zone.classList.add("drag-over"); } });
    zone.addEventListener("dragleave", e => { if (!zone.contains(e.relatedTarget)) zone.classList.remove("drag-over"); });
    zone.addEventListener("drop", e => { e.preventDefault(); zone.classList.remove("drag-over"); if (dragData) moveCourse(dragData.code, dragData.from, Number(zone.dataset.termIndex)); });
  });
  $$('[data-add-term]').forEach(btn => btn.addEventListener("click", () => openAddDialog(Number(btn.dataset.addTerm))));
  $$('[data-elective-term]').forEach(btn => btn.addEventListener("click", () => openAddDialog(Number(btn.dataset.electiveTerm), btn.dataset.electiveCode)));
  $("#board details.history")?.addEventListener("toggle", e => { state.historyOpen = e.target.open; });
  $("#board [data-open-transcript]")?.addEventListener("click", () => openTranscriptDialog());
  bindTouchDrag();
}

let removalUndo = null;
function removeCourse(code) {
  if (!state.plan) return;
  const lists = [state.plan.unscheduled, ...state.plan.terms.map(t => t.courses)];
  for (let listIndex = 0; listIndex < lists.length; listIndex++) {
    const index = lists[listIndex].findIndex(c => c.code === code);
    if (index >= 0) {
      const [card] = lists[listIndex].splice(index, 1);
      removalUndo = { listIndex, index, card };
      markDirty(); renderBoard(); validateSoon(60);
      toast(`${code} removed from your plan.`, { label: "Undo", action: undoRemoval });
      return;
    }
  }
}
function undoRemoval() {
  if (!removalUndo || !state.plan) return;
  const lists = [state.plan.unscheduled, ...state.plan.terms.map(t => t.courses)];
  lists[removalUndo.listIndex]?.splice(removalUndo.index, 0, removalUndo.card);
  const code = removalUndo.card.code; removalUndo = null; markDirty(); renderBoard(); validateSoon(60); toast(`${code} restored.`);
}

function renderAlerts() {
  const v = state.validation || {}, box = $("#alerts"), rows = [];
  Object.entries(v.issues || {}).forEach(([code, list]) => list.forEach(item => rows.push({ level: item.level === "error" ? "error" : "warning", where: code, message: item.message, code })));
  (v.warnings || []).forEach(message => rows.push({ level: "warning", where: "Plan", message }));
  (v.audit?.programs || []).flatMap(p => p.blocks || []).filter(b => b.confidence === "low" && b.status !== "complete").slice(0, 4).forEach(b => rows.push({ level: "assumption", where: "Audit", message: `${b.name}: this rule is complex, so check it in the UW Guide.` }));
  box.classList.toggle("hidden", !rows.length);
  box.innerHTML = rows.length ? `<div class="constraint-head"><div><strong>Constraint center</strong><p class="subtle">Conflicts, warnings, and assumptions that affect this plan.</p></div><span>${rows.length} item${rows.length === 1 ? "" : "s"}</span></div>${rows.slice(0, 12).map(r => `<div class="constraint-item ${r.level}"><span class="constraint-level">${r.level.toUpperCase()}</span><div><strong>${esc(r.where)}</strong><div>${esc(r.message)}</div></div>${r.code ? `<button class="btn small" data-repair="${esc(r.code)}">Inspect</button>` : `<a class="btn small" href="/plan/requirements" data-route>Review</a>`}</div>`).join("")}` : "";
  $$('[data-repair]', box).forEach(b => b.addEventListener("click", () => openDrawer(b.dataset.repair)));
}

function toast(message, options = {}) {
  const el = $("#toast"), action = $("#toastAction");
  $("#toastMessage").textContent = message;
  action.classList.toggle("hidden", !options.action); action.textContent = options.label || ""; action.onclick = options.action || null;
  el.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), options.action ? 6000 : 3000);
}

// ------------------------------------------------------------------ key dates
// Enrollment appointment windows (Registrar) and add/drop deadlines (Enroll),
// personalised by the standing the student will have when they enroll.
let timelineCache = null, timelineKey = "";
function enrollingStanding() {
  const s = state.settings;
  if (s.yearInSchool === "incoming") return null;
  const info = standingInfo();
  return info.fromTranscript ? info.projected : s.yearInSchool;
}
async function loadTimeline(force = false) {
  const standing = enrollingStanding() || "";
  if (!force && timelineCache && timelineKey === standing) return timelineCache;
  try {
    timelineCache = await api(`/api/timeline?standing=${enc(standing)}`);
    timelineKey = standing;
  } catch { timelineCache = { events: [], sources: {} }; }
  if (document.body.dataset.view === "dates") renderDates();
  renderNextUp();
  renderHomeDates();
  return timelineCache;
}
function daysUntil(iso) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return Math.round((new Date(`${iso}T00:00:00`) - today) / 86400000);
}
function whenText(e) {
  const d = daysUntil(e.date), end = e.end ? daysUntil(e.end) : d;
  if (d <= 0 && end >= 0) return e.end ? "now open" : "today";
  if (d === 1) return "tomorrow";
  return d < 0 ? "passed" : `in ${d} days`;
}
function fmtDate(iso, opts = { month: "short", day: "numeric" }) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, opts);
}
function relevantEvents(events) {
  return (events || []).filter(e => e.mine || e.kind !== "enroll");
}
function renderNextUp() {
  const box = $("#nextUp");
  if (!box || !timelineCache) return;
  const next = relevantEvents(timelineCache.events).slice(0, 3);
  box.classList.toggle("hidden", !next.length || !state.plan);
  box.innerHTML = `<span class="next-up-label">Next dates</span>${next.map(e => `<span class="next-up-item k-${e.kind}"><b>${fmtDate(e.date)}${e.end ? `–${fmtDate(e.end, { day: "numeric" })}` : ""}</b> ${esc(e.title.replace(/^.*?: /, ""))} <small>${whenText(e)}${e.estimate ? " · estimate" : ""}</small></span>`).join("")}<a href="/plan/dates" data-route>All dates</a>`;
}
function renderHomeDates() {
  const box = $("#homeDates");
  if (!box || !timelineCache) return;
  const next = relevantEvents(timelineCache.events).slice(0, 3);
  box.classList.toggle("hidden", !next.length);
  $("#homeDatesList").innerHTML = next.map(e => `<li class="k-${e.kind}"><time datetime="${e.date}"><b>${fmtDate(e.date, { day: "numeric" })}</b><span>${fmtDate(e.date, { month: "short" })}</span></time><span><strong>${esc(e.title)}</strong><small>${whenText(e)}${e.estimate ? " · estimated" : ""}</small></span></li>`).join("");
}
async function renderDates() {
  const body = $("#datesBody");
  const data = await loadTimeline();
  const standing = enrollingStanding();
  $("#datesSub").textContent = standing
    ? `Personalised for ${standing.toLowerCase()} standing. Your exact enrollment time is in Student Center.`
    : "New students enroll at SOAR; once you have a UW transcript, choose your year in Plan settings to see your enrollment window.";
  const events = data.events || [];
  if (!events.length) { body.innerHTML = `<div class="empty-state inline"><h2>No upcoming dates saved</h2><p>Run <code>python scripts/fetch_enroll.py</code> to load the latest terms from Course Search &amp; Enroll.</p></div>`; return; }
  const months = new Map();
  events.forEach(e => { const key = e.date.slice(0, 7); if (!months.has(key)) months.set(key, []); months.get(key).push(e); });
  body.innerHTML = `<ol class="date-list">${[...months.entries()].map(([key, list]) => `<li class="date-month"><h2>${fmtDate(`${key}-01`, { month: "long", year: "numeric" })}</h2><ol>${list.map(e => `
    <li class="date-item k-${e.kind} ${e.mine ? "mine" : "other"} ${e.estimate ? "estimate" : ""}">
      <time datetime="${e.date}"><b>${fmtDate(e.date, { day: "numeric" })}${e.end ? `–${fmtDate(e.end, { day: "numeric" })}` : ""}</b><span>${fmtDate(e.date, { weekday: "short" })}</span></time>
      <div><strong>${esc(e.title)}</strong>${e.mine && e.kind === "enroll" && standing ? ` <span class="badge confirmed">Your group</span>` : ""}${e.estimate ? ` <span class="badge">Estimate</span>` : ""}
        ${e.detail ? `<p>${esc(e.detail)}</p>` : ""}
        ${e.source ? `<a class="source-link" href="${esc(e.source.url)}" target="_blank" rel="noopener">${esc(e.source.name)}</a>` : ""}</div>
      <span class="countdown">${whenText(e)}</span>
    </li>`).join("")}</ol></li>`).join("")}</ol>
    <p class="source-note">Add and drop dates shown are for regular 15-week courses. Courses in shorter sessions have their own deadlines, which the Next term schedule shows for each section.</p>`;
}
function downloadDatesIcs() {
  const events = relevantEvents(timelineCache?.events).filter(e => e.mine);
  if (!events.length) return toast("No upcoming dates to export yet.");
  downloadFile("badgerplan-dates.ics", SCH.deadlinesIcs(events), "text/calendar");
  toast(`Saved ${events.length} dates to badgerplan-dates.ics.`);
}
function downloadFile(name, text, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ------------------------------------------------------------------ next-term schedule
const schedule = { termCode: null, courses: [], prefs: { openOnly: true, noBefore: null, freeDays: [], compact: false }, options: [], active: 0, picks: null, sections: null };
function termCodeOf(t) {
  const ay = t.season === "Fall" ? t.year + 1 : t.year;
  return `1${String(ay % 100).padStart(2, "0")}${{ Fall: 2, Spring: 4, Summer: 6 }[t.season]}`;
}
async function renderSchedule() {
  const body = $("#scheduleBody");
  if (!state.plan) { body.innerHTML = `<div class="empty-state inline"><h2>No plan yet</h2><p>Build a plan first; its next term becomes your timetable here.</p><a class="btn primary" href="/plan" data-route>Go to plan</a></div>`; return; }
  const index = state.plan.terms.findIndex(t => t.season !== "Summer");
  const term = state.plan.terms[index];
  if (!term) { body.innerHTML = `<p class="subtle">Your plan has no upcoming fall or spring term.</p>`; return; }
  const code = termCodeOf(term);
  const courses = term.courses.filter(c => !c.placeholder);
  const electives = term.courses.filter(c => c.placeholder);
  $("#scheduleTitle").textContent = `${term.label} schedule`;
  body.innerHTML = `<p class="subtle">Loading sections for ${courses.length} courses from Course Search &amp; Enroll…</p>`;
  const sections = {};
  let regular = null;
  try {
    for (let i = 0; i < courses.length; i += 12) {
      const batch = courses.slice(i, i + 12).map(c => c.code);
      const data = await api(`/api/terms/${code}/sections?codes=${enc(batch.join(","))}`);
      regular = data.regular_session || regular;
      Object.assign(sections, data.courses);
    }
  } catch (error) { body.innerHTML = `<p>${esc(error.message)}</p>`; return; }
  schedule.termCode = code;
  schedule.term = { ...term, regular };
  schedule.sections = sections;
  schedule.courses = courses.map(c => ({ code: c.code, title: c.title, credits: c.credits, offered: sections[c.code]?.offered, packages: sections[c.code]?.packages || null, source: sections[c.code]?.source, sample: sections[c.code]?.sample }));
  schedule.electives = electives;
  schedule.index = index;
  runSchedule();
}
function runSchedule() {
  const usable = schedule.courses.filter(c => c.offered !== false);
  const result = SCH.buildSchedules(usable.map(c => ({ code: c.code, packages: c.packages || [] })), { ...schedule.prefs, max: 6 });
  schedule.result = result;
  schedule.active = 0;
  schedule.picks = result.options[0]?.picks.map(p => ({ ...p })) || null;
  paintSchedule();
}
function paintSchedule() {
  const body = $("#scheduleBody"), t = schedule.term, r = schedule.result, p = schedule.prefs;
  const notOffered = schedule.courses.filter(c => c.offered === false);
  const noData = schedule.courses.filter(c => c.offered !== false && !c.packages?.length);
  const credits = schedule.courses.reduce((sum, c) => sum + Number(c.credits || 0), 0);
  const prefsHtml = `<form class="schedule-prefs" id="schedulePrefs">
    <label class="check"><input type="checkbox" name="openOnly" ${p.openOnly ? "checked" : ""}> Open seats only</label>
    <label>No classes before<select name="noBefore"><option value="">Any time</option>${[480, 540, 570, 600].map(v => `<option value="${v}" ${p.noBefore === v ? "selected" : ""}>${SCH.fmtTime(v)}</option>`).join("")}</select></label>
    <fieldset class="day-picks"><legend>Keep free</legend>${["M", "T", "W", "R", "F"].map(d => `<label><input type="checkbox" name="free" value="${d}" ${p.freeDays.includes(d) ? "checked" : ""}> ${SCH.DAY_NAMES[d]}</label>`).join("")}</fieldset>
    <label class="check"><input type="checkbox" name="compact" ${p.compact ? "checked" : ""}> Fewer days on campus</label></form>`;
  const notes = [
    ...notOffered.map(c => `<div class="constraint-item error"><span class="constraint-level">NOT OFFERED</span><div><strong>${esc(c.code)}</strong><div>Not on the published ${esc(t.label)} schedule. Move it to another term on the plan board.</div></div><a class="btn small" href="/plan" data-route>Open plan</a></div>`),
    ...noData.map(c => `<div class="constraint-item assumption"><span class="constraint-level">NO SECTIONS</span><div><strong>${esc(c.code)}</strong><div>Section times are not loaded. BadgerPlan fetches them from Course Search &amp; Enroll when it is online; you can also run <code>python scripts/fetch_enroll.py --term ${schedule.termCode}</code>.</div></div></div>`),
    ...(r.blocked || []).map(b => `<div class="constraint-item error"><span class="constraint-level">CONFLICT</span><div><strong>${esc(b.codes.join(" and "))}</strong><div>${esc(b.reason)}.</div></div></div>`),
  ].join("");
  const electiveNote = schedule.electives.length ? `<p class="hint">${schedule.electives.length} open elective slot${schedule.electives.length === 1 ? "" : "s"} on the plan for this term are not scheduled; pick specific courses on the plan board to include them.</p>` : "";
  const deadlines = t.regular ? `<p class="source-note">Regular-session deadlines for ${esc(t.label)}: add by <b>${fmtDate(t.regular.add)}</b>, drop without a DR by <b>${fmtDate(t.regular.drop_no_dr)}</b>, drop by <b>${fmtDate(t.regular.drop)}</b>.</p>` : "";
  let main = "";
  if (schedule.picks) {
    const o = r.options[schedule.active];
    const scheduled = schedule.picks.reduce((sum, p) => sum + Number(schedule.courses.find(c => c.code === p.code)?.credits || 0), 0);
    main = `<div class="schedule-options" role="tablist" aria-label="Timetable options">${r.options.map((_, i) => `<button type="button" role="tab" class="${i === schedule.active ? "active" : ""}" aria-selected="${i === schedule.active}" data-option="${i}">${i + 1}</button>`).join("")}<span>Option ${schedule.active + 1} of ${r.options.length} · ${scheduled}${scheduled !== credits ? ` of ${credits}` : ""} credits · ${o.stats.days.map(d => SCH.DAY_NAMES[d]).join(" ")} · ${SCH.fmtTime(o.stats.earliest)}–${SCH.fmtTime(o.stats.latest)}</span>
      <span class="schedule-actions"><button type="button" class="text-action compact" id="copyClassNumbers">Copy class numbers</button><button type="button" class="text-action compact" id="scheduleIcs">Add to calendar (.ics)</button></span></div>
      ${weekGrid(schedule.picks)}
      <ol class="section-list">${schedule.picks.map(pick => sectionRow(pick)).join("")}</ol>`;
  } else if (!r.blocked?.length && !noData.length) {
    main = `<p class="subtle">No courses to schedule.</p>`;
  }
  const sample = schedule.courses.some(c => c.sample);
  body.innerHTML = prefsHtml + (notes ? `<div class="constraint-center">${notes}</div>` : "") + electiveNote + main + deadlines
    + `<p class="source-note">Sections, times, rooms and seats: Course Search &amp; Enroll${sample ? " (saved sample; seats change quickly, confirm before enrolling)" : ""}. Final exam times are included in the calendar file.</p>`;
  bindSchedule();
}
const GRID_START = 480, GRID_END = 1260;
function weekGrid(picks) {
  const colors = ["c1", "c2", "c3", "c4", "c5", "c6", "c7"];
  const blocks = [];
  picks.forEach((p, k) => (p.pkg.meetings || []).forEach(m => SCH.meetingDays(m.days).forEach(d => blocks.push({ d, m, p, k }))));
  const earliest = Math.min(GRID_START, ...blocks.map(b => b.m.start)), latest = Math.max(1080, ...blocks.map(b => b.m.end));
  const top = Math.floor(earliest / 60) * 60, bottom = Math.ceil(latest / 60) * 60, span = bottom - top;
  const hours = [];
  for (let h = top; h < bottom; h += 60) hours.push(h);
  const days = ["M", "T", "W", "R", "F"];
  return `<div class="week-grid" style="--rows:${span / 15}">
    <div class="wg-times">${hours.map(h => `<span style="top:${((h - top) / span) * 100}%">${SCH.fmtTime(h)}</span>`).join("")}</div>
    ${days.map(d => `<div class="wg-day"><b>${SCH.DAY_NAMES[d]}</b><div class="wg-col">${hours.map(h => `<i style="top:${((h - top) / span) * 100}%"></i>`).join("")}
      ${blocks.filter(b => b.d === d).map(b => `<div class="wg-block ${colors[b.k % colors.length]}" style="top:${((b.m.start - top) / span) * 100}%;height:${((b.m.end - b.m.start) / span) * 100}%"><strong>${esc(b.p.code)}</strong><span>${SCH.fmtTime(b.m.start)}–${SCH.fmtTime(b.m.end)}</span><span>${esc([b.m.building, b.m.room].filter(Boolean).join(" "))}</span></div>`).join("")}
    </div></div>`).join("")}</div>`;
}
function sectionRow(pick) {
  const course = schedule.courses.find(c => c.code === pick.code);
  const pkg = pick.pkg;
  const alternatives = SCH.compatiblePackages(course, schedule.picks, schedule.prefs);
  const status = pkg.status === "OPEN" ? `<span class="seat open">Open · ${pkg.seats ?? "?"} seats</span>` : pkg.status === "WAITLISTED" ? `<span class="seat wait">Waitlist · ${pkg.waitlist ?? 0}</span>` : `<span class="seat full">Full</span>`;
  const session = pkg.session && pkg.session !== "A1" ? `<small class="hint">Session ${esc(pkg.session)} has its own add/drop dates; check this section in Enroll.</small>` : "";
  return `<li class="section-row"><div><strong>${esc(pick.code)}</strong> <span class="subtle">${esc(course.title || "")} · ${esc(course.credits)} cr</span>
      ${pkg.sections.map(sec => `<div class="sec-line"><b>${esc(sec.type)} ${esc(sec.number)}</b> #${esc(sec.classNumber)} ${pkg.meetings.length ? "" : ""}${sec.instructors.length ? `· ${esc(sec.instructors.join(", "))}` : ""}</div>`).join("")}
      <div class="sec-line">${pkg.meetings.map(m => `${esc(m.days)} ${SCH.fmtTime(m.start)}–${SCH.fmtTime(m.end)} · ${esc([m.building, m.room].filter(Boolean).join(" ") || "TBA")}`).join("<br>") || "No set meeting time"}</div>${session}</div>
    <div class="sec-side">${status}${alternatives.length > 1 ? `<label class="swap">Swap section<select data-swap="${esc(pick.code)}">${alternatives.map(a => `<option value="${a.classNumber}" ${a.classNumber === pkg.classNumber ? "selected" : ""}>${esc(a.sections.map(x => `${x.type} ${x.number}`).join(" + "))} · ${esc(a.meetings.map(m => `${m.days} ${SCH.fmtTime(m.start)}`).join(", "))}</option>`).join("")}</select></label>` : ""}</div></li>`;
}
function bindSchedule() {
  const form = $("#schedulePrefs");
  form?.addEventListener("change", () => {
    const data = new FormData(form);
    schedule.prefs = { openOnly: data.has("openOnly"), noBefore: data.get("noBefore") ? Number(data.get("noBefore")) : null, freeDays: data.getAll("free"), compact: data.has("compact") };
    runSchedule();
  });
  $$("[data-option]").forEach(b => b.addEventListener("click", () => {
    schedule.active = Number(b.dataset.option);
    schedule.picks = schedule.result.options[schedule.active].picks.map(p => ({ ...p }));
    paintSchedule();
  }));
  $$("[data-swap]").forEach(sel => sel.addEventListener("change", () => {
    const course = schedule.courses.find(c => c.code === sel.dataset.swap);
    const pkg = course.packages.find(p => String(p.classNumber) === sel.value);
    schedule.picks = schedule.picks.map(p => (p.code === course.code ? { ...p, pkg } : p));
    paintSchedule();
  }));
  $("#copyClassNumbers")?.addEventListener("click", async () => {
    const text = schedule.picks.map(p => `${p.code}: ${p.pkg.classNumber}`).join("\n");
    try { await navigator.clipboard.writeText(text); toast("Class numbers copied. Paste them into your cart in Course Search & Enroll."); }
    catch { toast(text.replace(/\n/g, " · ")); }
  });
  $("#scheduleIcs")?.addEventListener("click", () => {
    const t = schedule.term;
    const term = { name: t.label, classes_begin: t.regular?.begin, classes_end: t.regular?.end };
    if (!term.classes_begin) return toast("Term dates are not loaded yet.");
    const picks = schedule.picks.map(p => ({ ...p, title: schedule.courses.find(c => c.code === p.code)?.title }));
    const dates = relevantEvents(timelineCache?.events).filter(e => e.term === schedule.termCode && e.kind === "deadline");
    downloadFile(`badgerplan-${t.label.replace(/\s+/g, "-").toLowerCase()}.ics`, SCH.scheduleIcs(picks, term, dates), "text/calendar");
  });
}

// ------------------------------------------------------------------ touch drag
// HTML drag and drop does not fire on phones; a long press picks a card up instead.
const touchDrag = { active: false };
// Registered once, before any touch starts: Chrome only lets a touchmove listener
// block scrolling if it existed when the touch began.
document.addEventListener("touchmove", e => { if (touchDrag.active) e.preventDefault(); }, { passive: false });
function bindTouchDrag() {
  $$(".card[draggable]").forEach(card => {
    if (card.dataset.touchBound) return;
    card.dataset.touchBound = "1";
    card.addEventListener("pointerdown", e => {
      if (e.pointerType === "mouse" || e.target.closest("button")) return;
      const startX = e.clientX, startY = e.clientY;
      let ghost = null, over = null;
      const timer = setTimeout(() => {
        touchDrag.active = true;
        ghost = card.cloneNode(true);
        ghost.classList.add("drag-ghost");
        ghost.style.width = `${card.offsetWidth}px`;
        document.body.appendChild(ghost);
        card.classList.add("dragging");
        navigator.vibrate?.(12);
        place(startX, startY);
      }, 380);
      const place = (x, y) => {
        if (!ghost) return;
        ghost.style.transform = `translate(${x - ghost.offsetWidth / 2}px, ${y - 24}px)`;
        ghost.hidden = true;
        const zone = document.elementFromPoint(x, y)?.closest(".term[data-term-index], #trayCourses");
        ghost.hidden = false;
        if (zone !== over) { over?.classList.remove("drag-over"); over = zone; over?.classList.add("drag-over"); }
        if (y < 80) window.scrollBy(0, -12); else if (y > innerHeight - 80) window.scrollBy(0, 12);
      };
      const move = ev => {
        if (!ghost) { if (Math.hypot(ev.clientX - startX, ev.clientY - startY) > 10) cleanup(); return; }
        ev.preventDefault();
        place(ev.clientX, ev.clientY);
      };
      const up = () => {
        if (ghost && over) moveCourse(card.dataset.code, Number(card.dataset.term), Number(over.dataset.termIndex));
        cleanup();
      };
      const cleanup = () => {
        clearTimeout(timer);
        touchDrag.active = false;
        ghost?.remove(); card.classList.remove("dragging"); over?.classList.remove("drag-over");
        document.removeEventListener("pointermove", move);
        document.removeEventListener("pointerup", up);
        document.removeEventListener("pointercancel", cleanup);
      };
      document.addEventListener("pointermove", move, { passive: false });
      document.addEventListener("pointerup", up);
      document.addEventListener("pointercancel", cleanup);
    });
    card.addEventListener("contextmenu", e => { if (card.classList.contains("dragging")) e.preventDefault(); });
  });
}
