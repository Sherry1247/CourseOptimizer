"""BadgerPlan planner: choose courses for every requirement, then schedule them.

Pipeline
  1. Seed with completed / AP / transfer courses and any courses the student
     pinned to a term.
  2. Fill each major requirement block.  Candidate bundles are scored so that
     courses which also satisfy the *other* major (double-major overlap) or
     open gen-ed requirements win, and courses with long prerequisite chains,
     stale offerings or graduate numbering lose.
  3. Expand prerequisite chains (cheapest OR-branch first).
  4. Fill school/college + university gen-ed rules with popular, low-barrier
     courses that cover several open designations at once.
  5. Add elective placeholders up to 120 credits.
  6. Schedule term by term: requisites must be complete in an earlier term
     (or same term when concurrent enrollment is allowed), the course must be
     typically offered that season, and the credit cap holds.  Longest
     prerequisite chains are placed first.

The same validation used by the scheduler checks any user-edited plan, so a
drag-and-drop move is re-verified exactly like a generated plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Iterable

from audit import AuditInput, StudentCourse, active_blocks, run_audit
from degree_rules import degree_rules, gened_rules
from requisites import STANDING_CREDITS, cheapest_path, coreqs_in, describe, evaluate

SEASON_ORDER = {"Spring": 0, "Summer": 1, "Fall": 2}
CURRENT_YEAR = 2026
PLACEHOLDER_PREFIX = "ELECTIVE"
GENED_PREFIX = "GENED"


# ----------------------------------------------------------------------------- terms

@dataclass(frozen=True)
class Term:
    id: str
    season: str
    year: int

    @property
    def label(self) -> str:
        return f"{self.season} {self.year}"


def term_sequence(start_season: str, start_year: int, grad_season: str, grad_year: int, include_summer: bool) -> list[Term]:
    seasons = ["Spring", "Summer", "Fall"]
    terms: list[Term] = []
    season, year = start_season, start_year
    guard = 0
    while guard < 40:
        guard += 1
        if season != "Summer" or include_summer:
            terms.append(Term(f"{year}-{season.lower()}", season, year))
        if (year, SEASON_ORDER[season]) >= (grad_year, SEASON_ORDER[grad_season]):
            break
        index = seasons.index(season)
        if index == 2:
            season, year = "Spring", year + 1
        else:
            season = seasons[index + 1]
    return terms


# ----------------------------------------------------------------------------- request

@dataclass
class PlanRequest:
    program_ids: list[str]
    start_season: str = "Fall"
    start_year: int = CURRENT_YEAR
    grad_season: str = "Spring"
    grad_year: int = CURRENT_YEAR + 4
    student_type: str = "first-year"
    first_college_season: str | None = None
    first_college_year: int | None = None
    include_summer: bool = False
    max_credits: int = 17
    target_credits: int = 15
    prior: list[dict] = field(default_factory=list)      # {code, status, credits?}
    generic_credits: float = 0.0
    placements: dict[str, bool] = field(default_factory=dict)
    manual_done: list[str] = field(default_factory=list)
    variants: dict[str, str] = field(default_factory=dict)
    priority: str = "balanced"   # balanced | gpa | fast
    math_placement: str = "calculus"  # calculus (MATH 221-ready) | precalc (MATH 112/114) | none
    locked: list[dict] = field(default_factory=list)     # {code, term}
    excluded: list[str] = field(default_factory=list)    # courses the student never wants suggested

    @classmethod
    def from_payload(cls, payload: dict) -> "PlanRequest":
        programs = [p for p in payload.get("programs") or [] if p]
        if not programs:
            raise ValueError("Choose at least one major")
        if len(programs) > 3:
            raise ValueError("At most three majors are supported")
        request = cls(
            program_ids=programs,
            start_season=payload.get("startSeason", "Fall"),
            start_year=int(payload.get("startYear", CURRENT_YEAR)),
            grad_season=payload.get("gradSeason", "Spring"),
            grad_year=int(payload.get("gradYear", CURRENT_YEAR + 4)),
            student_type=payload.get("studentType", "first-year"),
            first_college_season=payload.get("firstCollegeSeason"),
            first_college_year=int(payload["firstCollegeYear"]) if payload.get("firstCollegeYear") else None,
            include_summer=bool(payload.get("includeSummer", False)),
            max_credits=int(payload.get("maxCredits", 17)),
            target_credits=int(payload.get("targetCredits", 15)),
            prior=list(payload.get("prior") or []),
            generic_credits=float(payload.get("genericCredits") or 0),
            placements=dict(payload.get("placements") or {}),
            manual_done=list(payload.get("manualDone") or []),
            variants=dict(payload.get("variants") or {}),
            priority=payload.get("priority", "balanced"),
            math_placement=payload.get("mathPlacement", "calculus"),
            locked=list(payload.get("locked") or []),
            excluded=list(payload.get("excluded") or []),
        )
        if request.start_season not in SEASON_ORDER or request.grad_season not in SEASON_ORDER:
            raise ValueError("Seasons must be Fall, Spring or Summer")
        if (request.grad_year, SEASON_ORDER[request.grad_season]) <= (request.start_year, SEASON_ORDER[request.start_season]):
            raise ValueError("Graduation term must be after the start term")
        if not 6 <= request.max_credits <= 24:
            raise ValueError("Credit cap must be between 6 and 24")
        return request

    @property
    def gened_start(self) -> tuple[str, int]:
        if self.first_college_season and self.first_college_year:
            return self.first_college_season, self.first_college_year
        return self.start_season, self.start_year


# ----------------------------------------------------------------------------- context

class PlanContext:
    """Catalog view shared by the generator and the validator."""

    def __init__(self, catalog: dict[str, dict], programs: list[dict], request: PlanRequest, aliases: dict[str, str] | None = None):
        self.catalog = dict(catalog)
        self.programs = programs
        self.request = request
        self.aliases = aliases or {}
        profile = programs[0].get("profile", "GENERIC")
        season, year = request.gened_start
        self.degree_rules = degree_rules(profile)
        self.gened_rules = gened_rules(season, year)
        self.terms = term_sequence(request.start_season, request.start_year, request.grad_season,
                                   request.grad_year, request.include_summer)
        self._cost_memo: dict[str, float] = {}

    # --- placement
    def placement_ok(self, code: str | None) -> bool:
        """Did the student place into ``code`` (used for 'placement into X' requisites)?"""

        level = self.request.math_placement
        if code is None:
            return level != "none"
        if code in self.request.placements and isinstance(self.request.placements[code], bool):
            return self.request.placements[code]
        subject = code.rsplit(" ", 1)[0].replace(" ", "")
        if "MATH" in subject.split("/"):
            number = self.number(code) or int(re.sub(r"\D", "", code.rsplit(" ", 1)[-1]) or 0)
            if level == "calculus":
                return number <= 222
            if level == "precalc":
                return number <= 114 or number == 141
            return False
        return False

    # --- catalog helpers
    def resolve(self, code: str) -> str | None:
        code = " ".join((code or "").upper().split())
        if code in self.catalog:
            return code
        key = re.sub(r"\s+", "", code.rsplit(" ", 1)[0]) + " " + code.rsplit(" ", 1)[-1] if " " in code else code
        return self.aliases.get(key) or self.aliases.get(code)

    def credits(self, code: str) -> float:
        info = self.catalog.get(code)
        if not info:
            return 3.0
        low, high = info["credits"]
        return float(low or high or 3)

    def number(self, code: str) -> int:
        info = self.catalog.get(code) or {}
        digits = "".join(ch for ch in str(info.get("number", "0")) if ch.isdigit())
        return int(digits or 0)

    def is_active(self, code: str) -> bool:
        info = self.catalog.get(code) or {}
        last = info.get("last_taught") or ""
        match = re.search(r"(\d{4})", last)
        if match and int(match.group(1)) < CURRENT_YEAR - 3:
            return False
        return True

    def conflicts(self, code: str, have: set[str]) -> bool:
        """True when ``code`` and something already planned exclude each other."""

        info = self.catalog.get(code) or {}
        if set(info.get("exclusions") or []) & have:
            return True
        return any(code in (self.catalog.get(other) or {}).get("exclusions", []) for other in have)

    def chain_cost(self, code: str, have: set[str], depth: int = 0) -> float:
        """Approximate number of courses needed to be able to take ``code``."""

        if depth == 0:
            self._cost_memo = {}  # memo is only valid for one ``have`` set
        if code in have:
            return 0.0
        if self.conflicts(code, have):
            return math.inf
        if depth > 6:
            return 1.0
        memo_key = code
        if memo_key in self._cost_memo and depth > 0:
            return self._cost_memo[memo_key]
        info = self.catalog.get(code)
        if not info:
            return math.inf  # retired / unknown course: not a route anyone can take now
        cost, _ = cheapest_path(info.get("requisites"), lambda c: self.chain_cost(c, have, depth + 1), lambda c: c in have,
                                self.placement_ok)
        value = 1.0 + (cost if cost != math.inf else 6.0)
        if not self.is_active(code):
            value += 4.0
        if depth > 0:
            self._cost_memo[memo_key] = value
        return value

    def ancestors(self, code: str) -> set[str]:
        """Every course reachable through ``code``'s requisite trees (cached)."""

        cache = self.__dict__.setdefault("_ancestor_cache", {})
        if code in cache:
            return cache[code]
        from requisites import courses_in
        seen: set[str] = set()
        stack = [code]
        while stack and len(seen) < 400:
            current = stack.pop()
            for parent in courses_in((self.catalog.get(current) or {}).get("requisites")):
                if parent not in seen:
                    seen.add(parent)
                    stack.append(parent)
        cache[code] = seen
        return seen

    def prereq_courses(self, code: str, have: set[str]) -> list[str]:
        info = self.catalog.get(code)
        if not info or not info.get("requisites"):
            return []
        # A planned course that itself depends on ``code`` cannot satisfy it (cycles
        # like SPANISH 226 <- "204 or 311" where 311 requires 226).
        have = {c for c in have if code not in self.ancestors(c)}
        _, chosen = cheapest_path(info["requisites"], lambda c: self.chain_cost(c, have, 1), lambda c: c in have,
                                  self.placement_ok)
        return [c for c in chosen if c in self.catalog]


# ----------------------------------------------------------------------------- selection

def _student_courses(entries: dict[str, dict], ctx: PlanContext, term_index: dict[str, int] | None = None) -> list[StudentCourse]:
    rows = []
    for code, entry in entries.items():
        rows.append(StudentCourse(code=code, credits=entry.get("credits") or ctx.credits(code),
                                  status=entry.get("status", "planned"),
                                  term_index=(term_index or {}).get(code, entry.get("term_index", 99))))
    return rows


def _audit(ctx: PlanContext, entries: dict[str, dict], term_index: dict[str, int] | None = None) -> dict:
    return run_audit(AuditInput(
        courses=_student_courses(entries, ctx, term_index),
        programs=ctx.programs,
        degree_rules=ctx.degree_rules,
        gened_rules=ctx.gened_rules,
        catalog=ctx.catalog,
        variants=ctx.request.variants,
        generic_credits=ctx.request.generic_credits,
        placements=ctx.request.placements,
        manual_done=set(ctx.request.manual_done),
    ))


def _other_program_codes(ctx: PlanContext, program_index: int) -> dict[str, int]:
    """Course -> number of *other* programs' blocks that list it (overlap potential)."""

    counts: dict[str, int] = {}
    for index, program in enumerate(ctx.programs):
        if index == program_index:
            continue
        for block in active_blocks(program, ctx.request.variants.get(program["id"]), include_college=(index == 0)):
            seen: set[str] = set()
            for slot in block.get("slots", []):
                for bundle in slot["options"]:
                    seen.update(bundle)
            for code in seen:
                counts[code] = counts.get(code, 0) + 1
    return counts


def _open_designation_tags(audit: dict, ctx: PlanContext) -> set[str]:
    rules = {rule["id"]: rule for rule in ctx.degree_rules + ctx.gened_rules}
    tags: set[str] = set()
    for result in audit["degree"]:
        if result["status"] in {"missing", "partial"}:
            rule = rules.get(result["id"]) or {}
            tags.update(rule.get("tags") or [])
    return tags


def _sample_plan_codes(ctx: PlanContext) -> dict[str, int]:
    """Course -> suggested term index (0-based) from the Guide four-year plans."""

    hints: dict[str, int] = {}
    for program in ctx.programs:
        for index, term in enumerate(program.get("sample_plan") or []):
            for item in term.get("items", []):
                for code in item.get("codes", []):
                    hints.setdefault(code, index)
    return hints


def _bundle_score(bundle: list[str], ctx: PlanContext, have: set[str], overlap: dict[str, int],
                  open_tags: set[str], hints: dict[str, int]) -> float:
    score = 0.0
    priority = ctx.request.priority
    for code in bundle:
        info = ctx.catalog.get(code)
        if not info:
            return -1e9
        if code in ctx.request.excluded:
            return -1e9
        if code not in have and not _suggestable(code, info):
            score -= 40  # honors-only / ESL / ROTC: never a default choice
        number = ctx.number(code)
        if number >= 700:
            return -1e9
        if code in have:
            score += 25
            continue
        if ctx.conflicts(code, have | set(bundle) - {code}):
            return -1e9
        score += 12 * overlap.get(code, 0)
        score += 2.5 * len(set(info.get("tags", [])) & open_tags)
        score -= 4 * ctx.chain_cost(code, have)
        if not ctx.is_active(code):
            score -= 15
        if not info.get("seasons"):
            score -= 3
        if number >= 600:
            score -= 3
        if code in hints:
            score += 4
        gpa = info.get("avg_gpa")
        if gpa:
            weight = 6 if priority == "gpa" else 1.5
            score += weight * (gpa - 3.2)
        popularity = info.get("grade_count") or 0
        score += min(math.log10(popularity + 1), 4) * (0.8 if priority != "fast" else 0.3)
        if priority == "fast":
            score -= 1.5 * ctx.chain_cost(code, have)
    return score / max(len(bundle), 1) - 0.5 * (len(bundle) - 1)


def _pattern_candidates(pattern: dict, ctx: PlanContext) -> list[str]:
    subjects = {s.replace(" ", "") for s in pattern.get("subjects", [])}
    result = []
    for code, info in ctx.catalog.items():
        if not {s.replace(" ", "") for s in info.get("subjects", [])} & subjects:
            continue
        number = ctx.number(code)
        if pattern.get("min_number") and number < pattern["min_number"]:
            continue
        if number >= 700 or not ctx.is_active(code):
            continue
        result.append(code)
    return result


def select_courses(ctx: PlanContext, entries: dict[str, dict], reasons: dict[str, list[str]]) -> None:
    """Add major-requirement courses to ``entries`` until every block is met."""

    hints = _sample_plan_codes(ctx)
    for program_index, program in enumerate(ctx.programs):
        overlap = _other_program_codes(ctx, program_index)
        for _round in range(60):
            audit = _audit(ctx, entries)
            open_tags = _open_designation_tags(audit, ctx)
            program_audit = audit["programs"][program_index]
            blocks = {b["key"]: b for b in active_blocks(program, ctx.request.variants.get(program["id"]), include_college=(program_index == 0))}
            progressed = False
            have = set(entries)
            for result in program_audit["blocks"]:
                if result["status"] not in {"missing", "partial"} or result["rule"] in {"text", "recommended"}:
                    continue
                block = blocks.get(result["key"])
                if not block:
                    continue
                pick = _pick_for_block(block, result, ctx, have, overlap, open_tags, hints)
                if not pick:
                    continue
                for code in pick:
                    if code not in entries:
                        entries[code] = {"status": "planned", "credits": ctx.credits(code)}
                        have.add(code)
                    reasons.setdefault(code, [])
                    tag = f"{program['name']}: {block['name']}"
                    if tag not in reasons[code]:
                        reasons[code].append(tag)
                progressed = True
                break  # re-audit after each pick so one-course-one-block stays exact
            if not progressed:
                break


def _pick_for_block(block, result, ctx, have, overlap, open_tags, hints) -> list[str] | None:
    rule = block["rule"]
    used = {u["code"] for u in result["used"]}
    if rule == "pattern":
        candidates = [c for c in _pattern_candidates(block.get("pattern") or {}, ctx) if c not in have]
        if not candidates:
            return None
        best = max(candidates, key=lambda c: _bundle_score([c], ctx, have, overlap, open_tags, hints))
        return [best]
    options: list[list[str]] = []
    slots = block.get("slots", [])
    missing_slots = result.get("missing_slots")
    for index, slot in enumerate(slots):
        if rule == "all" and missing_slots is not None and index not in missing_slots:
            continue
        for bundle in slot["options"]:
            if not bundle or any(code not in ctx.catalog for code in bundle):
                continue
            if set(bundle) <= used:
                continue
            if all(code in have for code in bundle):
                # already planned but consumed by another block of this major
                continue
            options.append(bundle)
        if rule == "all" and options:
            break  # fill the first missing slot first
    if not options:
        return None
    best = max(options, key=lambda b: _bundle_score(b, ctx, have, overlap, open_tags, hints))
    if _bundle_score(best, ctx, have, overlap, open_tags, hints) < -1e8:
        return None
    return best


def expand_prerequisites(ctx: PlanContext, entries: dict[str, dict], reasons: dict[str, list[str]]) -> None:
    for _ in range(8):
        added = False
        for code in list(entries):
            for prereq in ctx.prereq_courses(code, set(entries)):
                if prereq not in entries:
                    entries[prereq] = {"status": "planned", "credits": ctx.credits(prereq)}
                    reasons.setdefault(prereq, []).append(f"Prerequisite for {code}")
                    added = True
        if not added:
            break


NEVER_SUGGEST_SUBJECTS = {"ESL", "MIL SCI", "NAV SCI", "AIR SCI", "AFAERO", "INTER-LS", "COUNS PSY"}


def _suggestable(code: str, info: dict) -> bool:
    subjects = set(info.get("subjects") or [])
    if subjects & NEVER_SUGGEST_SUBJECTS:
        return False
    if "honors" in (info.get("tags") or []):
        return False
    return True


def prune_unused(ctx: PlanContext, entries: dict[str, dict], reasons: dict[str, list[str]]) -> None:
    """Drop planned courses no requirement uses (e.g. superseded by a shared course)."""

    from requisites import courses_in

    audit = _audit(ctx, entries)
    keep = {code for code, entry in entries.items() if entry.get("status") != "planned" or "Pinned by you" in reasons.get(code, [])}
    keep |= set(audit["course_usage"])
    for rule in audit["degree"]:
        keep |= {u["code"] for u in rule.get("used", [])}
    changed = True
    while changed:
        changed = False
        for code in list(keep):
            for prereq in courses_in((ctx.catalog.get(code) or {}).get("requisites")):
                if prereq in entries and prereq not in keep:
                    keep.add(prereq)
                    changed = True
    for code in list(entries):
        if code not in keep:
            entries.pop(code)
            reasons.pop(code, None)


def _gened_pool(ctx: PlanContext) -> list[str]:
    pool = []
    for code, info in ctx.catalog.items():
        number = ctx.number(code)
        if number >= 500 or not info.get("tags") or not info.get("seasons"):
            continue
        if not _suggestable(code, info):
            continue
        if (info.get("grade_count") or 0) < 150 or not ctx.is_active(code):
            continue
        if info["credits"][0] < 2:
            continue
        pool.append(code)
    return pool


def fill_degree_rules(ctx: PlanContext, entries: dict[str, dict], reasons: dict[str, list[str]]) -> None:
    rules = {rule["id"]: rule for rule in ctx.degree_rules + ctx.gened_rules}
    pool = _gened_pool(ctx)
    for _ in range(30):
        audit = _audit(ctx, entries)
        open_rules = [rules[r["id"]] for r in audit["degree"]
                      if r["status"] in {"missing", "partial"} and rules.get(r["id"], {}).get("type") in {"designation", "course_list", "ls_bs_math"}]
        if not open_rules:
            return
        have = set(entries)
        open_tags: dict[str, int] = {}
        for rule in open_rules:
            for tag in rule.get("tags") or []:
                open_tags[tag] = open_tags.get(tag, 0) + 1
        # course_list rules first: they name exact courses
        course_list = next((r for r in open_rules if r["type"] == "course_list"), None)
        if course_list:
            bundle = max(course_list["options"], key=lambda b: sum((ctx.catalog.get(c) or {}).get("grade_count") or 0 for c in b))
            for code in bundle:
                resolved = ctx.resolve(code) or code
                if resolved in ctx.catalog and resolved not in entries:
                    entries[resolved] = {"status": "planned", "credits": ctx.credits(resolved)}
                    reasons.setdefault(resolved, []).append(course_list["name"])
            continue
        math_rule = next((r for r in open_rules if r["type"] == "ls_bs_math"), None)
        candidates = pool
        if math_rule and not open_tags:
            candidates = [c for c in ctx.catalog if {s.replace(" ", "") for s in ctx.catalog[c]["subjects"]} & {"MATH", "STAT"}
                          and set(ctx.catalog[c].get("tags", [])) & {"level_i"} and ctx.catalog[c]["credits"][0] >= 3
                          and ctx.is_active(c) and ctx.number(c) < 500]
            open_tags = {"level_i": 1}

        def score(code: str) -> float:
            info = ctx.catalog[code]
            if code in have or code in ctx.request.excluded:
                return -1e9
            if ctx.conflicts(code, have):
                return -1e9
            hits = sum(weight for tag, weight in open_tags.items() if tag in info.get("tags", []))
            if not hits:
                return -1e9
            cost = ctx.chain_cost(code, have)
            if cost > 2.5:
                return -1e9
            gpa = info.get("avg_gpa") or 3.2
            weight = 3 if ctx.request.priority == "gpa" else 1.5
            tags = info.get("tags", [])
            level = 2 if "level_e" in tags else (0 if "level_i" in tags else -2)
            upper = -3 if ctx.number(code) >= 300 else 0
            return (10 * min(hits, 3) - 8 * (cost - 1) + weight * (gpa - 3.2) * 4 + level + upper
                    + min(math.log10((info.get("grade_count") or 1)), 4))

        best = max(candidates, key=score, default=None)
        if not best or score(best) < -1e8:
            return
        entries[best] = {"status": "planned", "credits": ctx.credits(best), "suggested": True}
        names = [rule["name"] for rule in open_rules if set(rule.get("tags") or []) & set(ctx.catalog[best].get("tags", []))]
        reasons.setdefault(best, []).extend(names[:3] or ["Degree requirement"])


# ----------------------------------------------------------------------------- scheduling

def _depths(ctx: PlanContext, codes: set[str]) -> dict[str, int]:
    """Longest chain of planned dependents after each course (critical path)."""

    dependents: dict[str, set[str]] = {code: set() for code in codes}
    for code in codes:
        tree = (ctx.catalog.get(code) or {}).get("requisites")
        from requisites import courses_in
        for prereq in courses_in(tree) & codes:
            dependents[prereq].add(code)
    memo: dict[str, int] = {}

    def depth(code: str, stack: frozenset = frozenset()) -> int:
        if code in memo:
            return memo[code]
        if code in stack:
            return 0
        value = 1 + max((depth(d, stack | {code}) for d in dependents[code]), default=0)
        memo[code] = value
        return value

    return {code: depth(code) for code in codes}


def schedule(ctx: PlanContext, entries: dict[str, dict], reasons: dict[str, list[str]]) -> tuple[list[dict], list[str]]:
    terms = ctx.terms
    prior = {code for code, entry in entries.items() if entry.get("status") in {"completed", "transfer", "ap", "in-progress"}}
    to_place = {code for code in entries if code not in prior and not code.startswith((PLACEHOLDER_PREFIX, GENED_PREFIX))}
    locked: dict[str, int] = {}
    term_index = {term.id: i for i, term in enumerate(terms)}
    for item in ctx.request.locked:
        code = ctx.resolve(item.get("code", "")) or item.get("code")
        if code in to_place and item.get("term") in term_index:
            locked[code] = term_index[item["term"]]
    hints = _sample_plan_codes(ctx)
    depths = _depths(ctx, to_place)
    placed: dict[str, int] = dict(locked)
    loads = [0.0] * len(terms)
    for code, index in locked.items():
        loads[index] += ctx.credits(code)
    credits_before = sum(ctx.credits(code) for code in prior) + ctx.request.generic_credits

    def major_rank(code: str) -> int:
        tags = reasons.get(code, [])
        if any(t.startswith("Prerequisite") for t in tags):
            return 0
        if entries[code].get("suggested"):
            return 2
        return 1

    def projected_earned(index: int) -> float:
        # Students fill each term to (at least) the target load with electives,
        # so class standing grows with the term count, not just major credits.
        total = credits_before
        for j in range(index):
            regular = terms[j].season != "Summer"
            total += max(loads[j], ctx.request.target_credits if regular else 0)
        return total

    for index, term in enumerate(terms):
        done_before = prior | {code for code, i in placed.items() if i < index}
        earned = projected_earned(index)
        cap = ctx.request.max_credits if term.season != "Summer" else min(ctx.request.max_credits, 8)
        target = ctx.request.target_credits if term.season != "Summer" else 6
        def offered_now(code: str) -> bool:
            seasons = (ctx.catalog.get(code) or {}).get("seasons") or []
            if seasons and term.season not in seasons:
                return False
            return bool(seasons) or term.season != "Summer"

        this_term = {c for c, i in placed.items() if i == index}
        pending_now = {c for c in to_place if c not in placed and offered_now(c)}
        eligible = []
        for code in to_place:
            if code in placed or code not in pending_now:
                continue
            info = ctx.catalog.get(code) or {}
            tree = info.get("requisites")
            same_term = this_term if info.get("concurrent") else set()
            ok = evaluate(tree, lambda c: c in done_before or c in same_term, credits_earned=earned,
                          assume_placement=ctx.placement_ok,
                          coreq_ok=lambda c: c in this_term or c in pending_now)
            if ok is False:
                continue
            eligible.append(code)
        remaining_terms = len(terms) - index
        eligible.sort(key=lambda c: (
            -depths.get(c, 1) if depths.get(c, 1) >= remaining_terms - 1 else 0,
            abs(hints.get(c, index) - index) if c in hints else 3,
            major_rank(c),
            -depths.get(c, 1),
            ctx.number(c),
            c,
        ))
        in_term = [c for c, i in placed.items() if i == index]
        hard_in_term = sum(1 for c in in_term if ((ctx.catalog.get(c) or {}).get("avg_gpa") or 3.5) < 3.0)
        upper_in_term = sum(1 for c in in_term if ctx.number(c) >= 400)
        unplaced_major = [c for c in to_place if c not in placed and major_rank(c) < 2]
        regular_left = sum(1 for t in terms[index:] if t.season != "Summer") or 1
        major_quota = max(3, math.ceil(len(unplaced_major) / regular_left) + 1)
        majors_in_term = sum(1 for c in in_term if major_rank(c) < 2)
        tight = remaining_terms <= 2
        for code in eligible:
            credits = ctx.credits(code)
            if loads[index] + credits > cap:
                continue
            if loads[index] >= target and term.season != "Summer":
                break
            gpa = (ctx.catalog.get(code) or {}).get("avg_gpa") or 3.5
            is_major = major_rank(code) < 2
            on_critical_path = depths.get(code, 1) >= remaining_terms - 1
            if not tight and not on_critical_path:
                if gpa < 3.0 and hard_in_term >= 2:
                    continue  # difficulty balancing: at most two historically tough courses per term
                if ctx.number(code) >= 400 and upper_in_term >= 3:
                    continue  # at most three upper-level courses per term
                if is_major and majors_in_term >= major_quota:
                    continue  # leave room for gen eds so they are spread out
            partners = [p for p in coreqs_in((ctx.catalog.get(code) or {}).get("requisites"))
                        if p in to_place and p not in placed and p in eligible]
            if partners and loads[index] + credits + sum(ctx.credits(p) for p in partners) > cap:
                continue
            for partner in partners:
                placed[partner] = index
                loads[index] += ctx.credits(partner)
                this_term.add(partner)
            placed[code] = index
            this_term.add(code)
            loads[index] += credits
            hard_in_term += gpa < 3.0
            upper_in_term += ctx.number(code) >= 400
            majors_in_term += is_major

    unscheduled = sorted(to_place - set(placed))
    # Electives to reach 120 credits, spread over terms under the target load.
    total = credits_before + sum(ctx.credits(code) for code in placed)
    placeholders: dict[int, list[dict]] = {i: [] for i in range(len(terms))}
    needed = max(0.0, 120 - total)
    counter = 0
    regular = [i for i, t in enumerate(terms) if t.season != "Summer"]
    # Spread electives evenly: always top up the lightest regular term first,
    # first up to the target load, then (if still short) up to the cap.
    for limit in (ctx.request.target_credits, ctx.request.max_credits):
        while needed > 0:
            room = [i for i in regular if loads[i] + 1 <= limit]
            if not room:
                break
            index = min(room, key=lambda i: (loads[i], -i))
            counter += 1
            size = min(3, needed, limit - loads[index])
            placeholders[index].append({"code": f"{PLACEHOLDER_PREFIX}-{counter}", "title": "Elective", "credits": size,
                                        "kind": "elective", "placeholder": True})
            loads[index] += size
            needed -= size
    result_terms = []
    for index, term in enumerate(terms):
        courses = []
        for code, i in sorted(placed.items(), key=lambda kv: (depths.get(kv[0], 0) * -1, kv[0])):
            if i != index:
                continue
            courses.append(_course_card(code, ctx, entries, reasons, locked=code in locked))
        courses.extend(placeholders[index])
        result_terms.append({"id": term.id, "season": term.season, "year": term.year, "label": term.label,
                             "courses": courses})
    warnings = []
    if unscheduled:
        warnings.append(f"{len(unscheduled)} course(s) could not fit before graduation: {', '.join(unscheduled[:8])}"
                        + (" …" if len(unscheduled) > 8 else "") + ". Add summers, raise the credit cap, or move graduation later.")
    if needed > 0:
        warnings.append(f"The plan is {needed:g} credits short of 120 even with full electives.")
    return result_terms, warnings + [f"__unscheduled__:{c}" for c in unscheduled]


def _course_card(code: str, ctx: PlanContext, entries: dict[str, dict], reasons: dict[str, list[str]], locked=False) -> dict:
    info = ctx.catalog.get(code) or {}
    why = reasons.get(code, [])
    if any(r.startswith("Prerequisite") for r in why):
        kind = "prereq"
    elif entries.get(code, {}).get("suggested"):
        kind = "gened"
    else:
        kind = "major"
    return {"code": code, "title": info.get("title", code), "credits": ctx.credits(code), "kind": kind,
            "reasons": why[:4], "locked": locked, "avgGpa": info.get("avg_gpa")}


# ----------------------------------------------------------------------------- API

def generate_plan(catalog: dict[str, dict], programs: list[dict], request: PlanRequest, aliases: dict[str, str] | None = None) -> dict:
    ctx = PlanContext(catalog, programs, request, aliases)
    entries: dict[str, dict] = {}
    reasons: dict[str, list[str]] = {}
    for item in request.prior:
        code = ctx.resolve(item.get("code", ""))
        if not code:
            continue
        entries[code] = {"status": item.get("status", "completed"), "credits": float(item.get("credits") or ctx.credits(code)),
                         "term_index": -1}
    for item in request.locked:
        code = ctx.resolve(item.get("code", ""))
        if code and code not in entries:
            entries[code] = {"status": "planned", "credits": ctx.credits(code)}
            reasons.setdefault(code, []).append("Pinned by you")

    select_courses(ctx, entries, reasons)
    expand_prerequisites(ctx, entries, reasons)
    prune_unused(ctx, entries, reasons)
    select_courses(ctx, entries, reasons)
    expand_prerequisites(ctx, entries, reasons)
    fill_degree_rules(ctx, entries, reasons)
    expand_prerequisites(ctx, entries, reasons)
    prune_unused(ctx, entries, reasons)
    terms, warnings = schedule(ctx, entries, reasons)
    unscheduled = [w.split(":", 1)[1] for w in warnings if w.startswith("__unscheduled__:")]
    warnings = [w for w in warnings if not w.startswith("__unscheduled__:")]
    plan = {"terms": terms, "unscheduled": [_course_card(c, ctx, entries, reasons) for c in unscheduled]}
    validation = validate_plan(catalog, programs, request, plan, aliases)
    validation["warnings"] = warnings + validation["warnings"]
    return {**plan, **validation}


def validate_plan(catalog: dict[str, dict], programs: list[dict], request: PlanRequest, plan: dict,
                  aliases: dict[str, str] | None = None) -> dict:
    """Check a (possibly user-edited) plan and return issues + a full audit."""

    ctx = PlanContext(catalog, programs, request, aliases)
    placeholder_catalog = {}
    entries: dict[str, dict] = {}
    term_of: dict[str, int] = {}
    for item in request.prior:
        code = ctx.resolve(item.get("code", ""))
        if code:
            entries[code] = {"status": item.get("status", "completed"),
                             "credits": float(item.get("credits") or ctx.credits(code)), "term_index": -1}
            term_of[code] = -1
    issues: dict[str, list[dict]] = {}
    term_loads = []
    terms = plan.get("terms") or []
    seen: dict[str, int] = {}
    for index, term in enumerate(terms):
        load = 0.0
        for course in term.get("courses", []):
            code = course.get("code")
            credits = float(course.get("credits") or ctx.credits(code))
            load += credits
            if course.get("placeholder") or code.startswith((PLACEHOLDER_PREFIX, GENED_PREFIX)):
                placeholder_catalog[code] = {"code": code, "subjects": [], "number": "0", "credits": [credits, credits],
                                             "tags": course.get("tags") or ["las", "level_i"], "title": course.get("title", "Elective")}
                entries[code] = {"status": "planned", "credits": credits, "term_index": index}
                term_of[code] = index
                continue
            resolved = ctx.resolve(code) or code
            if resolved in seen or resolved in entries and entries[resolved]["term_index"] == -1:
                info = catalog.get(resolved) or {}
                if not (info.get("repeatable") or "").lower().startswith("yes"):
                    issues.setdefault(resolved, []).append({"level": "error", "message": f"{resolved} appears more than once"})
            seen[resolved] = index
            entries[resolved] = {"status": "planned", "credits": credits, "term_index": index}
            term_of[resolved] = index
        term_loads.append(load)
    ctx.catalog.update(placeholder_catalog)

    prior_credits = sum(e["credits"] for e in entries.values() if e["term_index"] == -1) + request.generic_credits
    term_list = [Term(t.get("id", ""), t.get("season", "Fall"), int(t.get("year", 0))) for t in terms]
    all_codes = set(entries)
    for code, index in term_of.items():
        if index < 0 or code in placeholder_catalog:
            continue
        info = catalog.get(code)
        if not info:
            issues.setdefault(code, []).append({"level": "warning", "message": "Not found in the 2026–27 catalog"})
            continue
        before = {c for c, i in term_of.items() if i < index}
        same = {c for c, i in term_of.items() if i == index}
        earned = prior_credits + sum(entries[c]["credits"] for c in before if term_of[c] >= 0)
        tree = info.get("requisites")
        ok = evaluate(tree, lambda c: c in before or (info.get("concurrent") and c in same), credits_earned=earned,
                      assume_placement=ctx.placement_ok, coreq_ok=lambda c: c in same)
        if ok is False:
            missing = _missing_description(tree, before | (same if info.get("concurrent") else set()), earned, ctx.placement_ok)
            issues.setdefault(code, []).append({"level": "error", "message": f"Requisites not met: {missing}"})
        season = term_list[index].season if index < len(term_list) else None
        seasons = info.get("seasons") or []
        if season and seasons and season not in seasons:
            issues.setdefault(code, []).append({"level": "warning",
                                                "message": f"Usually offered {'/'.join(seasons)}, not {season}"})
        if not seasons:
            issues.setdefault(code, []).append({"level": "info", "message": "No recent offering history — confirm in Course Search & Enroll"})
        if not ctx.is_active(code):
            issues.setdefault(code, []).append({"level": "warning", "message": f"Last taught {info.get('last_taught')}"})
        conflict = set(info.get("exclusions") or []) & all_codes
        if conflict:
            issues.setdefault(code, []).append({"level": "error", "message": f"Not open to students with credit for {', '.join(sorted(conflict))}"})

    term_issues = []
    for index, load in enumerate(term_loads):
        season = term_list[index].season if index < len(term_list) else "Fall"
        cap = request.max_credits if season != "Summer" else 12
        if load > cap:
            term_issues.append({"term": index, "level": "warning", "message": f"{load:g} credits exceeds your {cap}-credit cap"})
        if load > 18 and season != "Summer":
            term_issues.append({"term": index, "level": "error", "message": "Above 18 credits needs an overload approval"})
        if 0 < load < 12 and season != "Summer":
            term_issues.append({"term": index, "level": "info", "message": "Below 12 credits (part-time)"})

    audit = _audit(ctx, entries, term_of)
    return {
        "issues": issues,
        "termIssues": term_issues,
        "termCredits": term_loads,
        "audit": audit,
        "warnings": [],
        "rules": {"degree": [r["id"] for r in ctx.degree_rules], "gened": "Core GenEd" if ctx.gened_rules and ctx.gened_rules[0]["id"].startswith("ge_") else "Legacy Gen Ed"},
    }


def _missing_description(tree, have: set[str], earned: float, placement_ok=True) -> str:
    """Describe the unmet part of a requisite tree."""

    if tree is None:
        return ""
    if "op" in tree:
        parts = [(arg, evaluate(arg, lambda c: c in have, credits_earned=earned, assume_placement=placement_ok)) for arg in tree["args"]]
        if tree["op"] == "and":
            return " and ".join(_missing_description(arg, have, earned, placement_ok) for arg, ok in parts if ok is False)
        return describe(tree)
    if "standing" in tree:
        return f"{tree['standing']} standing ({STANDING_CREDITS.get(tree['standing'], 0)}+ credits)"
    return describe(tree)


def iter_codes(plan: dict) -> Iterable[str]:
    for term in plan.get("terms", []):
        for course in term.get("courses", []):
            yield course.get("code")
