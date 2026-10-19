// BadgerPlan front end — vanilla ES module, no build step.
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (v = "") => String(v).replace(/[&<>'"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c]));
const enc = encodeURIComponent;
const SEASONS = { Spring: 0, Summer: 1, Fall: 2 };
const THIS_YEAR = new Date().getFullYear();
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
    startSeason: "Fall", startYear: THIS_YEAR,
    gradSeason: "Spring", gradYear: THIS_YEAR + 4,
    firstCollegeSeason: "Fall", firstCollegeYear: THIS_YEAR - 1,
    majors: [],               // [{id, variants:{group:name}}]
    prior: [],                // [{code, status, credits}]
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
  $$(".seg").forEach(btn => btn.addEventListener("click", () => {
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
  $("#addMajor").addEventListener("click", () => addMajorRow());
  $("#setupForm").addEventListener("submit", e => { e.preventDefault(); generate(); });
  bindPriorSearch();
}

function renderSetup() {
  const s = state.settings;
  $$(".seg").forEach(btn => {
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
  const s = state.settings;
  const start = s.startYear * 3 + SEASONS[s.startSeason];
  const end = s.gradYear * 3 + SEASONS[s.gradSeason];
  if (end <= start) { $("#timelineHint").textContent = "Graduation must be after your first term."; return; }
  let regular = 0;
  let season = s.startSeason, year = s.startYear;
  for (let guard = 0; guard < 40; guard++) {
    if (season !== "Summer") regular++;
    if (year * 3 + SEASONS[season] >= end) break;
    if (season === "Fall") { season = "Spring"; year++; } else if (season === "Spring") season = "Summer"; else season = "Fall";
  }
  $("#timelineHint").textContent = `${regular} fall/spring terms · ${s.startSeason} ${s.startYear} → ${s.gradSeason} ${s.gradYear}`;
  $("#compactPlanDates").textContent = `${s.startSeason} ${s.startYear} → ${s.gradSeason} ${s.gradYear} · ${regular} terms`;
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
  $("#openTranscript").addEventListener("click", () => {
    resetTranscriptDialog();
    dialog.showModal();
  });
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
    const checks = $$("[data-transcript-code]", $("#transcriptRows"));
    const select = checks.every(check => !check.checked);
    checks.forEach(check => { check.checked = select; });
    $("#toggleTranscriptRows").textContent = select ? "Clear all" : "Select all";
    updateTranscriptImportCount();
  });
  $("#transcriptRows").addEventListener("change", updateTranscriptImportCount);
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

function bytesToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let start = 0; start < bytes.length; start += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(start, start + 0x8000));
  }
  return btoa(binary);
}

async function parseTranscriptUpload() {
  const button = $("#parseTranscript");
  const feedback = $("#transcriptFeedback");
  const file = $("#transcriptFile").files?.[0];
  const pasted = $("#transcriptText").value.trim();
  if (!file && !pasted) {
    feedback.textContent = "Choose a transcript file or paste transcript text first.";
    feedback.className = "transcript-feedback error";
    feedback.focus();
    return;
  }
  if (file && file.size > 12 * 1024 * 1024) {
    feedback.textContent = "That file is larger than the 12 MB limit.";
    feedback.className = "transcript-feedback error";
    feedback.focus();
    return;
  }
  button.disabled = true;
  button.textContent = "Reading transcript…";
  feedback.classList.add("hidden");
  try {
    const body = { text: pasted };
    if (file) {
      body.filename = file.name;
      if (file.name.toLowerCase().endsWith(".pdf")) body.file_data = bytesToBase64(await file.arrayBuffer());
      else body.text = `${pasted}\n${await file.text()}`;
    }
    const data = await api("/api/transcript/parse", { method: "POST", body });
    state.transcriptMatches = data.matches || [];
    renderTranscriptReview(data);
  } catch (error) {
    feedback.textContent = error.message;
    feedback.className = "transcript-feedback error";
    feedback.focus();
  } finally {
    button.disabled = false;
    button.textContent = "Review courses";
  }
}

function renderTranscriptReview(data) {
  const rows = $("#transcriptRows");
  rows.innerHTML = state.transcriptMatches.map(row => `
    <tr class="${row.include ? "" : "excluded"}">
      <td><input type="checkbox" data-transcript-code="${esc(row.code)}" ${row.include ? "checked" : ""} aria-label="Import ${esc(row.code)}"></td>
      <td><strong>${esc(row.code)}</strong><span>${esc(row.title)}</span><small title="${esc(row.evidence)}">${esc(row.note)}</small></td>
      <td>${esc(row.credits)}</td>
      <td><span class="match-status ${row.confidence}">${row.confidence === "matched" ? "Matched" : "Review"}</span></td>
    </tr>`).join("") || `<tr><td colspan="4">No catalog course codes were found. Try pasting the course-history section.</td></tr>`;
  $("#transcriptSummary").textContent = `${data.summary.matched} catalog matches · ${data.summary.needs_review} need a closer look`;
  $("#transcriptReview").classList.remove("hidden");
  $("#parseTranscript").classList.add("hidden");
  $("#importTranscript").classList.toggle("hidden", !state.transcriptMatches.length);
  updateTranscriptImportCount();
}

function updateTranscriptImportCount() {
  const selected = $$("[data-transcript-code]:checked", $("#transcriptRows")).length;
  $("#importTranscript").textContent = `Import ${selected} course${selected === 1 ? "" : "s"}`;
  $("#importTranscript").disabled = selected === 0;
}

function importTranscriptMatches() {
  const selected = new Set($$("[data-transcript-code]:checked", $("#transcriptRows")).map(input => input.dataset.transcriptCode));
  let added = 0;
  state.transcriptMatches.filter(row => selected.has(row.code)).forEach(row => {
    if (state.settings.prior.some(prior => prior.code === row.code)) return;
    state.settings.prior.push({ code: row.code, status: row.status, credits: row.credits });
    state.courseCache.set(row.code, { code: row.code, title: row.title, credits_min: row.credits, credits_max: row.credits });
    added += 1;
  });
  renderPriorChips();
  markDirty();
  if (state.plan) { syncPriorIntoPlan(); validateSoon(); }
  $("#transcriptDialog").close();
  toast(added ? `Imported ${added} completed course${added === 1 ? "" : "s"}.` : "Those courses were already in prior credit.");
}

function renderPriorChips() {
  const box = $("#priorChips");
  box.innerHTML = state.settings.prior.map((p, i) => `
    <span class="chip">${esc(p.code)}
      <select data-i="${i}" aria-label="Credit type">
        ${["ap", "transfer", "completed", "in-progress"].map(s => `<option value="${s}" ${p.status === s ? "selected" : ""}>${{ ap: "AP/IB", transfer: "Transfer", completed: "Taken at UW", "in-progress": "In progress" }[s]}</option>`).join("")}
      </select>
      <button type="button" data-remove="${i}" aria-label="Remove">×</button></span>`).join("");
  $$("select[data-i]", box).forEach(sel => sel.addEventListener("change", () => { state.settings.prior[sel.dataset.i].status = sel.value; markDirty(); validateSoon(); }));
  $$("button[data-remove]", box).forEach(btn => btn.addEventListener("click", () => {
    state.settings.prior.splice(Number(btn.dataset.remove), 1);
    renderPriorChips(); markDirty();
    if (state.plan) { syncPriorIntoPlan(); validateSoon(); }
  }));
}

function syncPriorIntoPlan() {
  const priorCodes = new Set(state.settings.prior.map(p => p.code));
  state.plan.terms.forEach(t => t.courses = t.courses.filter(c => !priorCodes.has(c.code)));
  renderBoard();
}

// ------------------------------------------------------------------ payload
function payload(extra = {}) {
  const s = state.settings;
  const majors = s.majors.filter(m => m.id);
  const variants = {};
  majors.forEach(m => { if (Object.keys(m.variants).length) variants[m.id] = m.variants; });
  const placements = {};
  if (s.placeCommA) Object.assign(placements, { comm_a: true, ge_cl: true });
  if (s.placeQrA) Object.assign(placements, { qr_a: true, ge_mqr: true });
  const locked = [];
  state.plan?.terms.forEach(t => t.courses.forEach(c => { if (c.locked) locked.push({ code: c.code, term: t.id }); }));
  return {
    programs: majors.map(m => m.id), variants,
    studentType: s.studentType,
    startSeason: s.startSeason, startYear: s.startYear,
    gradSeason: s.gradSeason, gradYear: s.gradYear,
    firstCollegeSeason: s.studentType === "transfer" ? s.firstCollegeSeason : null,
    firstCollegeYear: s.studentType === "transfer" ? s.firstCollegeYear : null,
    includeSummer: s.includeSummer,
    targetCredits: s.targetCredits, maxCredits: s.maxCredits,
    prior: s.prior, genericCredits: s.genericCredits,
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
  const priorCards = state.settings.prior.map(p => ({ code: p.code, title: state.courseCache.get(p.code)?.title || "", credits: p.credits, kind: "prior", status: p.status }));
  let html = "";
  if (priorCards.length || state.settings.genericCredits) {
    const total = priorCards.reduce((s, c) => s + Number(c.credits || 0), 0) + Number(state.settings.genericCredits || 0);
    html += `<section class="year"><div class="year-label"><b>Before</b><span>${total} credits</span></div><div class="terms">
      <div class="term prior"><div class="term-head"><b>${state.settings.studentType === "transfer" ? "Transfer credit" : "AP / prior credit"}</b><span class="term-credits">${total} cr</span></div>
      ${priorCards.map(c => cardHtml(c, -2, issues, shared)).join("")}
      ${state.settings.genericCredits ? `<div class="card prior"><div class="code">+${state.settings.genericCredits} credits</div><div class="title">Credit without a UW equivalent</div></div>` : ""}
      </div></div></section>`;
  }
  years.forEach((year, i) => {
    const credits = year.terms.reduce((s, { term }) => s + termCredits(term), 0);
    html += `<section class="year"><div class="year-label"><b>Year ${i + 1}</b><span>${year.start}–${String(year.start + 1).slice(2)} · ${credits} cr</span></div><div class="terms">`;
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
  $("#planSubtitle").textContent = `${state.settings.startSeason} ${state.settings.startYear} → ${state.settings.gradSeason} ${state.settings.gradYear}. Drag courses between terms; each move is re-checked for prerequisites, offering season and requirements.`;
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

async function savePlan() {
  if (!state.plan) return toast("Build a plan before saving.");
  try {
    const result = await api("/api/plans", { method: "POST", body: snapshot() });
    state.planId = result.id;
    state.dirty = false;
    $("#saveStatus").textContent = "Saved";
    saveLocal();
    toast("Plan saved to your local database.");
  } catch (error) { toast(error.message); }
}

async function openPlans() {
  const dialog = $("#plansDialog");
  const list = $("#plansList");
  list.innerHTML = `<p class="subtle">Loading…</p>`;
  dialog.showModal();
  const plans = await api("/api/plans").catch(() => []);
  list.innerHTML = plans.map(p => `<button type="button" class="result" data-plan="${esc(p.id)}"><div><b>${esc(p.name)}</b><small>Saved ${new Date(p.updated_at).toLocaleString()}</small></div><div class="right">Open</div></button>`).join("") || `<p class="subtle">No saved plans yet.</p>`;
  $$("[data-plan]", list).forEach(btn => btn.addEventListener("click", async () => {
    loadSnapshot(await api(`/api/plans/${enc(btn.dataset.plan)}`));
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
  return ({ home: "UW academic planning", plan: "Degree plan", audit: "Requirements", double: "Double major", explore: "Explore courses", professors: "Professors", majors: "Majors", course: "Course", professor: "Professor", major: "Major" })[view] || "BadgerPlan";
}

function showView(view) {
  const routes = { plan: "/plan", audit: "/plan/requirements", double: "/plan/double-major", explore: "/explore/courses", programs: "/explore/majors", home: "/" };
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
  if (c.kind === "prior") badges.push(`<span class="badge">${{ ap: "AP/IB", transfer: "Transfer", completed: "Taken", "in-progress": "In progress" }[c.status] || "Earned"}</span>`);
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
