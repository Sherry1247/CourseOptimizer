"""Core planning logic for the CourseOptimizer Streamlit app.

The module deliberately has no UI or third-party dependencies.  It can be tested
with the Python standard library and later replaced by a solver without changing
the presentation layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus


@dataclass(frozen=True)
class Course:
    code: str
    name: str
    credits: int
    prerequisites: tuple[str, ...] = ()
    semesters: tuple[str, ...] = ("Fall", "Spring")
    description: str = ""
    avg_gpa: float | None = None
    grade_a_rate: float | None = None
    difficulty: float | None = None
    professor_rating: float | None = None
    typical_workload: str = ""


@dataclass(frozen=True)
class TermPlan:
    label: str
    term: str
    courses: tuple[Course, ...]
    credits: int


@dataclass(frozen=True)
class PlanResult:
    terms: tuple[TermPlan, ...]
    required_courses: frozenset[str]
    completed_courses: frozenset[str]
    overlap_courses: frozenset[str]
    supporting_courses: frozenset[str]
    unscheduled_courses: frozenset[str]
    missing_catalog_courses: frozenset[str]
    warnings: tuple[str, ...] = ()

    @property
    def planned_credits(self) -> int:
        return sum(term.credits for term in self.terms)

    @property
    def planned_courses(self) -> int:
        return sum(len(term.courses) for term in self.terms)


@dataclass
class Catalog:
    courses: dict[str, Course]
    majors: dict[str, dict]
    metadata: dict = field(default_factory=dict)
    double_major_rules: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, path: str | Path) -> "Catalog":
        with Path(path).open(encoding="utf-8") as handle:
            raw = json.load(handle)

        courses: dict[str, Course] = {}
        for item in raw.get("courses", []):
            code = normalize_course_code(item["full_code"])
            courses[code] = Course(
                code=code,
                name=item["name"],
                credits=int(item["credits"]),
                prerequisites=tuple(
                    normalize_course_code(value)
                    for value in item.get("prerequisites", [])
                ),
                semesters=tuple(item.get("semesters") or ("Fall", "Spring")),
                description=item.get("description", ""),
                avg_gpa=_optional_float(item.get("avg_gpa")),
                grade_a_rate=_optional_float(item.get("grade_a_rate")),
                difficulty=_optional_float(item.get("difficulty")),
                professor_rating=_optional_float(item.get("professor_rating")),
                typical_workload=item.get("typical_workload", ""),
            )

        majors = raw.get("majors", {})
        for major in majors.values():
            major["required_courses"] = [
                normalize_course_code(code)
                for code in major.get("required_courses", [])
            ]

        return cls(
            courses=courses,
            majors=majors,
            metadata=raw.get("metadata", {}),
            double_major_rules=raw.get("double_major_rules", {}),
        )

    def requirements_for(self, majors: Iterable[str]) -> set[str]:
        requirements: set[str] = set()
        for major in majors:
            if major not in self.majors:
                raise ValueError(f"Unknown major: {major}")
            requirements.update(self.majors[major].get("required_courses", []))
        return requirements

    def overlap_for(self, majors: Iterable[str]) -> set[str]:
        selected = list(majors)
        if len(selected) < 2:
            return set()
        requirement_sets = [
            set(self.majors[major].get("required_courses", [])) for major in selected
        ]
        return set.intersection(*requirement_sets)

    def validate(self) -> list[str]:
        issues: list[str] = []
        known = set(self.courses)

        for code, course in self.courses.items():
            for prerequisite in course.prerequisites:
                if prerequisite not in known:
                    issues.append(
                        f"{code} references prerequisite {prerequisite}, which is not in the catalog."
                    )

        for major_name, major in self.majors.items():
            for code in major.get("required_courses", []):
                if code not in known:
                    issues.append(
                        f"{major_name} requires {code}, which is not in the catalog."
                    )

        cycles = find_cycles(self.courses)
        for cycle in cycles:
            issues.append("Prerequisite cycle: " + " → ".join(cycle))
        return issues


def normalize_course_code(value: str) -> str:
    return " ".join(value.upper().replace("/", " / ").split())


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _term_sequence(start_term: str, start_year: int, years: int) -> list[tuple[str, str]]:
    term = start_term.title()
    if term not in {"Fall", "Spring"}:
        raise ValueError("start_term must be Fall or Spring")

    sequence: list[tuple[str, str]] = []
    year = start_year
    for _ in range(years * 2):
        sequence.append((f"{term} {year}", term))
        if term == "Fall":
            term = "Spring"
            year += 1
        else:
            term = "Fall"
    return sequence


def generate_plan(
    catalog: Catalog,
    majors: Iterable[str],
    completed_courses: Iterable[str] = (),
    *,
    start_term: str = "Fall",
    start_year: int = 2026,
    years: int = 4,
    max_credits_per_term: int = 15,
    priority: str = "balanced",
) -> PlanResult:
    """Build a deterministic prerequisite-safe plan for major requirements.

    A prerequisite must be completed before the start of a term; the planner will
    never place a prerequisite and its dependent course in the same term.
    """

    selected_majors = tuple(dict.fromkeys(majors))
    if not selected_majors:
        raise ValueError("Select at least one major")
    if not 1 <= years <= 8:
        raise ValueError("years must be between 1 and 8")
    if not 1 <= max_credits_per_term <= 24:
        raise ValueError("max_credits_per_term must be between 1 and 24")

    required = catalog.requirements_for(selected_majors)
    completed = {normalize_course_code(code) for code in completed_courses}
    overlap = catalog.overlap_for(selected_majors)
    planning_courses = _prerequisite_closure(required, catalog.courses)
    supporting_courses = planning_courses - required
    missing = planning_courses - set(catalog.courses)
    remaining = (planning_courses - completed) - missing
    completed_state = set(completed)
    terms: list[TermPlan] = []

    dependent_count = {code: 0 for code in catalog.courses}
    for course in catalog.courses.values():
        for prerequisite in course.prerequisites:
            dependent_count[prerequisite] = dependent_count.get(prerequisite, 0) + 1

    for label, season in _term_sequence(start_term, start_year, years):
        completed_before_term = set(completed_state)
        eligible = [
            catalog.courses[code]
            for code in remaining
            if season in catalog.courses[code].semesters
            and set(catalog.courses[code].prerequisites).issubset(completed_before_term)
        ]
        eligible.sort(
            key=lambda course: _course_priority(
                course,
                priority=priority,
                overlap=overlap,
                dependent_count=dependent_count,
            ),
            reverse=True,
        )

        selected: list[Course] = []
        used_credits = 0
        for course in eligible:
            if used_credits + course.credits <= max_credits_per_term:
                selected.append(course)
                used_credits += course.credits

        selected_codes = {course.code for course in selected}
        remaining.difference_update(selected_codes)
        completed_state.update(selected_codes)
        terms.append(
            TermPlan(
                label=label,
                term=season,
                courses=tuple(selected),
                credits=used_credits,
            )
        )

    warnings: list[str] = []
    if missing:
        warnings.append(
            "Some stated requirements are absent from the local catalog and cannot be scheduled."
        )
    if remaining:
        warnings.append(
            "Some requirements could not be placed within the selected timeline and credit limit."
        )
    if any(code not in catalog.courses for code in completed):
        warnings.append(
            "Some completed course codes are outside the demo catalog; they are still accepted as prerequisite credit."
        )

    return PlanResult(
        terms=tuple(terms),
        required_courses=frozenset(required),
        completed_courses=frozenset(completed),
        overlap_courses=frozenset(overlap),
        supporting_courses=frozenset(supporting_courses),
        unscheduled_courses=frozenset(remaining),
        missing_catalog_courses=frozenset(missing),
        warnings=tuple(warnings),
    )


def _prerequisite_closure(
    course_codes: Iterable[str], courses: dict[str, Course]
) -> set[str]:
    """Return courses plus every explicit prerequisite reachable in the catalog."""

    closure: set[str] = set()
    pending = [normalize_course_code(code) for code in course_codes]
    while pending:
        code = pending.pop()
        if code in closure:
            continue
        closure.add(code)
        course = courses.get(code)
        if course is not None:
            pending.extend(course.prerequisites)
    return closure


def _course_priority(
    course: Course,
    *,
    priority: str,
    overlap: set[str],
    dependent_count: dict[str, int],
) -> tuple[float, ...]:
    overlap_bonus = 1.0 if course.code in overlap else 0.0
    unlock_score = float(dependent_count.get(course.code, 0))
    scarcity = 1.0 / max(len(course.semesters), 1)
    gpa = course.avg_gpa if course.avg_gpa is not None else 0.0
    rating = course.professor_rating if course.professor_rating is not None else 0.0
    difficulty = course.difficulty if course.difficulty is not None else 3.0

    if priority == "gpa":
        preference = gpa + rating / 5.0 - difficulty / 10.0
    elif priority == "challenge":
        preference = difficulty
    else:
        preference = rating / 5.0 + gpa / 4.0 - abs(difficulty - 3.0) / 10.0

    # Prerequisite-chain progress and scarce offerings are more important than
    # soft preference data.  Course code is the deterministic tie breaker.
    return (overlap_bonus, unlock_score, scarcity, preference, course.code)


def unmet_prerequisites(
    course: Course, completed_courses: Iterable[str]
) -> tuple[str, ...]:
    completed = {normalize_course_code(code) for code in completed_courses}
    return tuple(code for code in course.prerequisites if code not in completed)


def prerequisite_depth(code: str, courses: dict[str, Course]) -> int:
    memo: dict[str, int] = {}

    def visit(current: str, visiting: set[str]) -> int:
        if current in memo:
            return memo[current]
        if current in visiting:
            raise ValueError(f"Prerequisite cycle involving {current}")
        course = courses.get(current)
        if course is None or not course.prerequisites:
            memo[current] = 0
            return 0
        visiting.add(current)
        depth = 1 + max(visit(parent, visiting) for parent in course.prerequisites)
        visiting.remove(current)
        memo[current] = depth
        return depth

    return visit(normalize_course_code(code), set())


def find_cycles(courses: dict[str, Course]) -> list[tuple[str, ...]]:
    visiting: list[str] = []
    visited: set[str] = set()
    cycles: list[tuple[str, ...]] = []

    def dfs(code: str) -> None:
        if code in visiting:
            start = visiting.index(code)
            cycle = tuple(visiting[start:] + [code])
            if cycle not in cycles:
                cycles.append(cycle)
            return
        if code in visited or code not in courses:
            return
        visiting.append(code)
        for prerequisite in courses[code].prerequisites:
            dfs(prerequisite)
        visiting.pop()
        visited.add(code)

    for course_code in courses:
        dfs(course_code)
    return cycles


def guide_url(course_code: str) -> str:
    subject = normalize_course_code(course_code).rsplit(" ", 1)[0]
    slug = subject.lower().replace(" ", "_").replace("/", "_")
    return f"https://guide.wisc.edu/courses/{slug}/"


def madgrades_url(course_code: str) -> str:
    return f"https://madgrades.com/search?q={quote_plus(normalize_course_code(course_code))}"


def rate_my_professors_url() -> str:
    return "https://www.ratemyprofessors.com/school/1256"


COURSE_SEARCH_URL = "https://public.enroll.wisc.edu/"
DEGREE_AUDIT_URL = "https://registrar.wisc.edu/dars/"
