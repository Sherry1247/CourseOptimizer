const state = {
  catalog: null,
  courses: new Map(),
  plan: null,
  completed: new Set(),
  studentType: "first-year",
  planId: null,
  dirty: false,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const esc = (value = "") => String(value).replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));

document.addEventListener("DOMContentLoaded", init);

async function init() {
  buildYearOptions();
  bindEvents();
  const response = await fetch("/api/catalog");
  state.catalog = await response.json();
  state.catalog.courses.forEach(course => state.courses.set(course.code, course));
  populatePrograms();
  renderLibrary("");
}

function buildYearOptions() {
  const thisYear = new Date().getFullYear();
  const start = $("#startYear");
  const graduation = $("#graduationYear");
  for (let year = thisYear; year <= thisYear + 7; year++) {
    start.add(new Option(year, year));
  }
  for (let year = thisYear + 1; year <= thisYear + 9; year++) {
    graduation.add(new Option(year, year));
  }
  start.value = thisYear;
  graduation.value = thisYear + 4;
  updateTimelineHint();
}

function populatePrograms() {
  const names = state.catalog.programs.map(program => program.name);
  [$("#primaryMajor"), $("#secondMajor")].forEach(select => {
    select.innerHTML = names.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join("");
  });
  if (names.length > 1) $("#secondMajor").selectedIndex = 1;
}

function bindEvents() {
  $$(".segment").forEach(button => button.addEventListener("click", () => {
    $$(".segment").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    state.studentType = button.dataset.studentType;
    $("#creditHelp").textContent = state.studentType === "transfer"
      ? "Add evaluated transfer courses. Verify equivalencies in Transferology/DARS."
      : "Add AP/IB, placement, or dual-enrollment credit you already know.";
    markDirty();
  }));

  $("#doubleMajor").addEventListener("change", event => {
    $("#secondMajorField").classList.toggle("hidden", !event.target.checked);
    markDirty();
  });
  $("#maxCredits").addEventListener("input", event => {
    $("#maxCreditsValue").textContent = event.target.value;
    if (state.plan) validateAndRender();
  });
  ["#startYear", "#graduationYear", "#startTerm"].forEach(selector => {
    $(selector).addEventListener("change", () => { updateTimelineHint(); markDirty(); });
  });
  ["#primaryMajor", "#secondMajor"].forEach(selector => $(selector).addEventListener("change", markDirty));

  $("#completedSearch").addEventListener("input", showCompletedSuggestions);
  $("#completedSearch").addEventListener("blur", () => setTimeout(() => $("#completedSuggestions").classList.add("hidden"), 150));
  $("#generatePlan").addEventListener("click", generatePlan);
  $("#savePlan").addEventListener("click", savePlan);
  $("#exportPlan").addEventListener("click", exportPlan);
  $("#openLibrary").addEventListener("click", () => $("#courseLibrary").showModal());
  $("#closeLibrary").addEventListener("click", () => $("#courseLibrary").close());
  $("#librarySearch").addEventListener("input", event => renderLibrary(event.target.value));
}

function updateTimelineHint() {
  const years = Number($("#graduationYear").value) - Number($("#startYear").value);
  $("#timelineHint").textContent = years > 0 ? `${years}-year planning horizon · ${years * 2} regular terms` : "Graduation must be after your start year";
}

function showCompletedSuggestions(event) {
  const query = event.target.value.trim().toLowerCase();
  const box = $("#completedSuggestions");
  if (!query) { box.classList.add("hidden"); return; }
  const matches = [...state.courses.values()]
    .filter(course => !state.completed.has(course.code) && `${course.code} ${course.title}`.toLowerCase().includes(query))
    .slice(0, 8);
  box.innerHTML = matches.map(course => `<button type="button" data-code="${esc(course.code)}"><strong>${esc(course.code)}</strong><span>${esc(course.title)}</span></button>`).join("");
  box.classList.toggle("hidden", matches.length === 0);
  box.querySelectorAll("button").forEach(button => button.addEventListener("mousedown", () => addCompleted(button.dataset.code)));
}

function addCompleted(code) {
  state.completed.add(code);
  $("#completedSearch").value = "";
  $("#completedSuggestions").classList.add("hidden");
  renderCompleted();
  markDirty();
}

function renderCompleted() {
  $("#completedTokens").innerHTML = [...state.completed].map(code => `<span class="token">${esc(code)}<button data-code="${esc(code)}" aria-label="Remove ${esc(code)}">×</button></span>`).join("");
  $("#completedTokens").querySelectorAll("button").forEach(button => button.addEventListener("click", () => {
    state.completed.delete(button.dataset.code);
    renderCompleted();
    markDirty();
  }));
}

function currentSettings() {
  return {
    studentType: state.studentType,
    startTerm: $("#startTerm").value,
    startYear: Number($("#startYear").value),
    graduationYear: Number($("#graduationYear").value),
    primaryMajor: $("#primaryMajor").value,
    secondMajor: $("#doubleMajor").checked ? $("#secondMajor").value : null,
    completedCourses: [...state.completed],
    maxCredits: Number($("#maxCredits").value),
    priority: "balanced",
  };
}

async function generatePlan() {
  const settings = currentSettings();
  if (settings.graduationYear <= settings.startYear) return toast("Choose a graduation year after your start year.");
  if (settings.secondMajor === settings.primaryMajor) return toast("Choose two different majors.");
  const button = $("#generatePlan");
  button.disabled = true;
  button.firstElementChild.textContent = "Building prerequisite paths…";
  try {
    const response = await fetch("/api/plans/generate", {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(settings)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Plan generation failed");
    state.plan = data;
    state.planId = null;
    markDirty();
    validateAndRender();
    $("#planTitle").textContent = settings.secondMajor ? `${settings.primaryMajor} + ${settings.secondMajor}` : `${settings.primaryMajor} degree map`;
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.firstElementChild.textContent = "Generate my plan";
  }
}

function validatePlan() {
  if (!state.plan) return {issues: [], invalid: new Set(), overloaded: new Set()};
  const issues = [];
  const invalid = new Set();
  const overloaded = new Set();
  const completed = new Set(state.completed);
  const courseTerm = new Map();
  state.plan.terms.forEach((term, index) => term.courses.forEach(code => courseTerm.set(code, index)));

  state.plan.terms.forEach((term, index) => {
    const credits = term.courses.reduce((sum, code) => sum + (state.courses.get(code)?.credits || 0), 0);
    if (credits > Number($("#maxCredits").value)) {
      overloaded.add(term.label);
      issues.push(`${term.label} has ${credits} major credits, above your selected limit.`);
    }
    term.courses.forEach(code => {
      const course = state.courses.get(code);
      if (!course) return;
      const unmet = course.prerequisites.filter(prereq => !completed.has(prereq) && (!courseTerm.has(prereq) || courseTerm.get(prereq) >= index));
      if (unmet.length) {
        invalid.add(code);
        issues.push(`${code} needs ${unmet.join(", ")} in an earlier term.`);
      }
      if (course.semesters.length && !course.semesters.includes(term.term)) {
        invalid.add(code);
        issues.push(`${code} is not marked as typically offered in ${term.term}.`);
      }
    });
  });
  (state.plan.unscheduledCourses || []).forEach(code => issues.push(`${code} could not be scheduled within this timeline.`));
  (state.plan.missingCatalogCourses || []).forEach(code => issues.push(`${code} is required but missing from the pilot catalog.`));
  return {issues: [...new Set(issues)], invalid, overloaded};
}

function validateAndRender() {
  const validation = validatePlan();
  renderSchedule(validation);
  renderSummary(validation);
  renderAlerts(validation.issues);
}

function renderSchedule(validation) {
  const board = $("#schedule");
  board.classList.remove("empty-state");
  const grouped = [];
  state.plan.terms.forEach((term, index) => {
    const groupIndex = Math.floor(index / 2);
    if (!grouped[groupIndex]) grouped[groupIndex] = [];
    grouped[groupIndex].push({...term, index});
  });
  board.innerHTML = grouped.map((terms, yearIndex) => `
    <section class="year-group">
      <div class="year-label">Academic year ${yearIndex + 1}</div>
      <div class="term-grid">
        ${terms.map(term => termMarkup(term, validation)).join("")}
      </div>
    </section>`).join("");
  bindDragAndDrop();
}

function termMarkup(term, validation) {
  const credits = term.courses.reduce((sum, code) => sum + (state.courses.get(code)?.credits || 0), 0);
  return `<div class="term-column ${validation.overloaded.has(term.label) ? "invalid" : ""}" data-term-index="${term.index}">
    <div class="term-header"><strong>${esc(term.label)}</strong><span>${credits} credits</span></div>
    <div class="term-courses">
      ${term.courses.length ? term.courses.map(code => courseCardMarkup(code, validation.invalid.has(code))).join("") : '<div class="term-empty">Drop courses here</div>'}
    </div>
  </div>`;
}

function courseCardMarkup(code, invalid) {
  const course = state.courses.get(code);
  if (!course) return "";
  const overlap = state.plan.overlapCourses.includes(code);
  const supporting = state.plan.supportingCourses.includes(code);
  const creditLabel = course.credits > 0 ? `${course.credits} cr` : "variable credit";
  return `<article class="course-card ${invalid ? "invalid" : ""}" draggable="true" data-code="${esc(code)}">
    <button class="remove" data-remove="${esc(code)}" aria-label="Remove ${esc(code)}">×</button>
    <div class="code">${esc(code)}</div><div class="title">${esc(course.title)}</div>
    <div class="meta"><span class="badge">${creditLabel}</span>${overlap ? '<span class="badge overlap">shared</span>' : ""}${supporting ? '<span class="badge">prerequisite</span>' : ""}</div>
  </article>`;
}

function bindDragAndDrop() {
  $$(".course-card").forEach(card => {
    card.addEventListener("dragstart", event => {
      card.classList.add("dragging");
      const source = card.closest(".term-column").dataset.termIndex;
      event.dataTransfer.setData("text/plain", JSON.stringify({code: card.dataset.code, source: Number(source)}));
    });
    card.addEventListener("dragend", () => card.classList.remove("dragging"));
  });
  $$(".term-column").forEach(column => {
    column.addEventListener("dragover", event => { event.preventDefault(); column.classList.add("drag-over"); });
    column.addEventListener("dragleave", () => column.classList.remove("drag-over"));
    column.addEventListener("drop", event => {
      event.preventDefault();
      column.classList.remove("drag-over");
      const {code, source} = JSON.parse(event.dataTransfer.getData("text/plain"));
      moveCourse(code, source, Number(column.dataset.termIndex));
    });
  });
  $$('[data-remove]').forEach(button => button.addEventListener("click", () => removeCourse(button.dataset.remove)));
}

function moveCourse(code, sourceIndex, targetIndex) {
  if (sourceIndex === targetIndex) return;
  state.plan.terms[sourceIndex].courses = state.plan.terms[sourceIndex].courses.filter(item => item !== code);
  state.plan.terms[targetIndex].courses.push(code);
  markDirty();
  validateAndRender();
}

function removeCourse(code) {
  state.plan.terms.forEach(term => term.courses = term.courses.filter(item => item !== code));
  markDirty();
  validateAndRender();
}

function renderSummary(validation) {
  const planned = state.plan.terms.reduce((count, term) => count + term.courses.length, 0);
  $("#summaryCourses").textContent = planned;
  $("#summaryOverlap").textContent = state.plan.overlapCourses.length;
  $("#summaryIssues").textContent = validation.issues.length;
}

function renderAlerts(issues) {
  const box = $("#alerts");
  box.classList.toggle("hidden", issues.length === 0);
  box.innerHTML = issues.length ? `<strong>${issues.length} item${issues.length === 1 ? "" : "s"} to review</strong><br>${issues.slice(0, 6).map(esc).join("<br>")}${issues.length > 6 ? `<br>+ ${issues.length - 6} more` : ""}` : "";
}

function renderLibrary(query) {
  if (!state.catalog) return;
  const normalized = query.toLowerCase().trim();
  const courses = state.catalog.courses.filter(course => !normalized || `${course.code} ${course.title} ${course.description}`.toLowerCase().includes(normalized)).slice(0, 40);
  $("#libraryResults").innerHTML = courses.map(course => {
    const creditLabel = course.credits > 0 ? `${course.credits} credits` : "Variable credit";
    const offeringLabel = course.semesters.length ? course.semesters.join(" / ") : "Offering history pending";
    return `<div class="library-item"><div><strong>${esc(course.code)} · ${esc(course.title)}</strong><span>${creditLabel} · ${esc(offeringLabel)}${course.prerequisites.length ? ` · Prereq: ${esc(course.prerequisites.join(", "))}` : ""}</span></div><button data-add="${esc(course.code)}">Add</button></div>`;
  }).join("");
  $$("[data-add]").forEach(button => button.addEventListener("click", () => addCourseToPlan(button.dataset.add)));
}

function addCourseToPlan(code) {
  if (!state.plan) return toast("Generate a plan first.");
  if (state.plan.terms.some(term => term.courses.includes(code))) return toast(`${code} is already in your plan.`);
  const course = state.courses.get(code);
  const positions = new Map();
  state.plan.terms.forEach((term, index) => term.courses.forEach(item => positions.set(item, index)));
  let target = state.plan.terms.findIndex((term, index) => course.semesters.includes(term.term) && course.prerequisites.every(prereq => state.completed.has(prereq) || (positions.has(prereq) && positions.get(prereq) < index)));
  if (target < 0) target = 0;
  state.plan.terms[target].courses.push(code);
  $("#courseLibrary").close();
  markDirty();
  validateAndRender();
  toast(`${code} added to ${state.plan.terms[target].label}.`);
}

async function savePlan() {
  if (!state.plan) return toast("Generate a plan before saving.");
  const settings = currentSettings();
  const payload = {
    id: state.planId,
    name: $("#planTitle").textContent,
    ...settings,
    terms: state.plan.terms.map(term => ({label: term.label, courses: term.courses})),
  };
  const response = await fetch("/api/plans", {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) return toast(data.error || "Could not save plan.");
  state.planId = data.id;
  state.dirty = false;
  $("#saveStatus").textContent = "Saved locally";
  toast("Plan saved to the local database.");
}

function exportPlan() {
  if (!state.plan) return toast("Generate a plan before exporting.");
  const blob = new Blob([JSON.stringify({settings: currentSettings(), ...state.plan}, null, 2)], {type: "application/json"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "badgerplan.json";
  link.click();
  URL.revokeObjectURL(link.href);
}

function markDirty() {
  state.dirty = true;
  $("#saveStatus").textContent = "Unsaved changes";
}

let toastTimer;
function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("show"), 2800);
}
