"""DARS-style degree audit.

Given the courses a student has completed or planned, report for every
requirement (major blocks, school/college rules, university gen ed):

    status   complete | planned | partial | missing | manual
    used     which courses were applied (and whether completed or planned)
    need     what is still missing (courses / credits / text)

Assignment rules
  * Inside one program a course is applied to at most one block (UW majors
    generally forbid double counting within the major; e.g. the CS footnote
    "COMP SCI courses may only fulfill one COMP SCI major requirement area").
  * Across two majors a course may count for both -- this is how double
    majors save credits -- and those courses are reported as ``shared``.
  * Designation rules (breadth, Comm A/B, QR, Core GenEd, L&S credit) may use
    any course, including ones already counted in a major.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

COMPLETE_STATUSES = {"completed", "transfer", "ap", "in-progress"}


@dataclass
class StudentCourse:
    code: str
    credits: float
    status: str = "planned"  # completed | transfer | ap | in-progress | planned
    term_index: int = -1     # -1 = before the first planned term

    @property
    def done(self) -> bool:
        return self.status in COMPLETE_STATUSES


@dataclass
class AuditInput:
    courses: list[StudentCourse]
    programs: list[dict]                    # loaded program dicts; index 0 = primary
    degree_rules: list[dict]
    gened_rules: list[dict]
    catalog: dict[str, dict]
    variants: dict[str, str] = field(default_factory=dict)   # program_id -> variant name
    generic_credits: float = 0.0            # transfer/AP credit without a UW equivalent
    placements: dict[str, bool] = field(default_factory=dict)  # comm_a / qr_a / ge_cl / ge_mqr
    manual_done: set[str] = field(default_factory=set)       # manual rule ids the student checked
    max_shared: int | None = None           # cap on courses shared between majors


def _course_credits(course: StudentCourse) -> float:
    return float(course.credits or 0)


def active_blocks(program: dict, variant: str | dict | None, include_college: bool) -> list[dict]:
    """Blocks that apply, given the chosen variant(s).

    ``variant`` is either one variant name or a {variant_group: name} mapping
    (a program can have several independent choice groups).
    """

    blocks = []
    for block in program["blocks"]:
        if block["rule"] == "recommended":
            continue
        if block["section"] == "college" and not include_college:
            continue
        if block.get("variant_group"):
            chosen = variant.get(block["variant_group"]) if isinstance(variant, dict) else variant
            if not chosen:
                # default to the first variant of the group
                options = [b["variant"] for b in program["blocks"] if b.get("variant_group") == block["variant_group"]]
                chosen = options[0] if options else None
            if block["variant"] != chosen:
                continue
        blocks.append(block)
    return blocks


def _pattern_match(pattern: dict, catalog_course: dict | None) -> bool:
    if not pattern or not catalog_course:
        return False
    subjects = {s.replace(" ", "") for s in pattern.get("subjects", [])}
    course_subjects = {s.replace(" ", "") for s in catalog_course.get("subjects", [])}
    if not subjects & course_subjects:
        return False
    number = int("".join(ch for ch in str(catalog_course.get("number", "0")) if ch.isdigit()) or 0)
    if pattern.get("min_number") and number < pattern["min_number"]:
        return False
    return True


def audit_block(block: dict, available: dict[str, StudentCourse], catalog: dict[str, dict]) -> dict:
    """Evaluate one block against the pool of still-unused courses."""

    rule = block["rule"]
    result = {
        "id": block.get("id"), "key": block.get("key"), "name": block["name"], "rule": rule,
        "count": block.get("count"), "credits": block.get("credits"), "section": block["section"],
        "confidence": block.get("confidence"), "notes": block.get("notes", []),
        "used": [], "status": "missing", "need": "", "slots_total": len(block.get("slots", [])),
        "variant": block.get("variant"),
    }
    if rule == "text":
        result["status"] = "manual"
        result["need"] = "Check this requirement in the Guide / DARS"
        return result

    def bundle_available(bundle: list[str]) -> bool:
        return bool(bundle) and all(code in available for code in bundle)

    satisfied_slots: list[tuple[int, list[str]]] = []
    for index, slot in enumerate(block.get("slots", [])):
        # choose the option with the most completed courses
        best = None
        for bundle in slot["options"]:
            if bundle_available(bundle):
                done = sum(1 for code in bundle if available[code].done)
                if best is None or done > best[0]:
                    best = (done, bundle)
        if best:
            satisfied_slots.append((index, best[1]))

    def credits_of(codes: Iterable[str]) -> float:
        return sum(_course_credits(available[code]) for code in codes)

    used: list[str] = []
    if rule == "all":
        for _, bundle in satisfied_slots:
            used.extend(code for code in bundle if code not in used)
        need_slots = len(block["slots"]) - len(satisfied_slots)
        met = need_slots == 0
        missing = [block["slots"][i] for i in range(len(block["slots"])) if i not in {s for s, _ in satisfied_slots}]
        result["need"] = "" if met else "Still need: " + "; ".join(
            " or ".join(" + ".join(b) for b in slot["options"][:3]) or slot["label"] for slot in missing[:4])
        result["missing_slots"] = [i for i in range(len(block["slots"])) if i not in {s for s, _ in satisfied_slots}]
    elif rule == "choose":
        need = block.get("count") or 1
        ordered = sorted(satisfied_slots, key=lambda s: -sum(1 for c in s[1] if available[c].done))
        for _, bundle in ordered[:need]:
            used.extend(code for code in bundle if code not in used)
        have = min(len(satisfied_slots), need)
        met = have >= need
        result["need"] = "" if met else f"Choose {need - have} more from {len(block['slots'])} options"
    elif rule in {"credits", "pattern"}:
        target = block.get("credits") or 0
        pool: list[str] = []
        if rule == "credits":
            for _, bundle in sorted(satisfied_slots, key=lambda s: -sum(1 for c in s[1] if available[c].done)):
                pool.extend(code for code in bundle if code not in pool)
        else:
            pool = [code for code, course in available.items() if _pattern_match(block.get("pattern"), catalog.get(code))]
            pool.sort(key=lambda code: not available[code].done)
        total = 0.0
        count_target = (block.get("pattern") or {}).get("count") if rule == "pattern" else None
        for code in pool:
            if (target and total >= target) or (count_target and len(used) >= count_target):
                break
            used.append(code)
            total += _course_credits(available[code])
        if not target and not count_target:
            target = 3.0
        met = (total >= target) if target and not count_target else (len(used) >= (count_target or 0))
        result["need"] = "" if met else (
            f"{max(target - total, 0):g} more credits" if not count_target else f"{count_target - len(used)} more courses")
        result["credits_applied"] = total
    else:
        met = False

    result["used"] = [{"code": code, "status": available[code].status, "term": available[code].term_index} for code in used]
    if met:
        result["status"] = "complete" if all(available[code].done for code in used) else "planned"
    else:
        result["status"] = "partial" if used else "missing"
    return result


def _assign_program(program: dict, blocks: list[dict], pool: dict[str, StudentCourse], catalog) -> list[dict]:
    """Greedy one-course-one-block assignment, most constrained blocks first."""

    def candidates(block):
        codes = set()
        for slot in block.get("slots", []):
            for bundle in slot["options"]:
                codes.update(code for code in bundle if code in pool)
        return codes

    order = sorted(
        range(len(blocks)),
        key=lambda i: (
            {"all": 0, "choose": 1, "credits": 2, "pattern": 3, "text": 4}.get(blocks[i]["rule"], 5),
            len(blocks[i].get("slots", [])) or 999,
        ),
    )
    remaining = dict(pool)
    results: dict[int, dict] = {}
    for index in order:
        block = blocks[index]
        result = audit_block(block, remaining, catalog)
        for used in result["used"]:
            remaining.pop(used["code"], None)
        result["program_id"] = program["id"]
        results[index] = result
    _ = candidates
    return [results[i] for i in range(len(blocks))]


def evaluate_rule(rule: dict, courses: list[StudentCourse], catalog: dict[str, dict], data: AuditInput) -> dict:
    kind = rule["type"]
    result = {"id": rule["id"], "name": rule["name"], "type": kind, "scope": rule.get("scope"),
              "note": rule.get("note"), "url": rule.get("url"), "used": [], "status": "missing", "need": ""}

    def info(code):
        return catalog.get(code) or {}

    def matches(course: StudentCourse) -> bool:
        tags = set(info(course.code).get("tags", []))
        if not tags & set(rule.get("tags", [])):
            return False
        if rule.get("exclude_subjects"):
            subjects = {s.replace(" ", "") for s in info(course.code).get("subjects", [])}
            if subjects & {s.replace(" ", "") for s in rule["exclude_subjects"]}:
                return False
        if rule.get("min_course_credits") and _course_credits(course) < rule["min_course_credits"]:
            return False
        return True

    def finish(met: bool, used: list[StudentCourse], need: str):
        result["used"] = [{"code": c.code, "status": c.status, "term": c.term_index} for c in used]
        if met:
            result["status"] = "complete" if all(c.done for c in used) else "planned"
        else:
            result["status"] = "partial" if used else "missing"
            result["need"] = need
        return result

    if kind == "manual":
        result["status"] = "complete" if rule["id"] in data.manual_done else "manual"
        result["need"] = rule.get("note", "")
        return result
    if kind == "designation":
        placement_ok = bool(rule.get("placement")) and any(data.placements.get(tag) for tag in rule.get("tags", []))
        if placement_ok and rule.get("courses"):
            result.update(status="complete", need="", used=[{"code": "Placement exam", "status": "completed", "term": -1}])
            return result
        pool = sorted((c for c in courses if matches(c)), key=lambda c: (not c.done, c.term_index))
        if rule.get("courses"):
            used = pool[: rule["courses"]]
            return finish(len(used) >= rule["courses"], used, f"{rule['courses'] - len(used)} more course(s)")
        target = rule.get("credits") or 0
        if placement_ok:
            # A qualifying placement score covers part of a Core GenEd credit requirement.
            target = max(target - 3, 0)
        used, total = [], 0.0
        for course in pool:
            if total >= target:
                break
            used.append(course)
            total += _course_credits(course)
        return finish(total >= target, used, f"{target - total:g} more credits")
    if kind == "tag_credits":
        pool = [c for c in courses if set(info(c.code).get("tags", [])) & set(rule["tags"])]
        total = sum(_course_credits(c) for c in pool)
        result["credits_applied"] = total
        return finish(total >= rule["credits"], pool, f"{rule['credits'] - total:g} more credits")
    if kind == "total_credits":
        total = sum(_course_credits(c) for c in courses) + data.generic_credits
        result["credits_applied"] = total
        result["used"] = []
        if total >= rule["credits"]:
            done_total = sum(_course_credits(c) for c in courses if c.done) + data.generic_credits
            result["status"] = "complete" if done_total >= rule["credits"] else "planned"
        else:
            result["status"] = "partial" if total else "missing"
            result["need"] = f"{rule['credits'] - total:g} more credits"
        return result
    if kind == "course_list":
        have = {c.code: c for c in courses}
        for bundle in rule["options"]:
            if all(code in have for code in bundle):
                return finish(True, [have[code] for code in bundle], "")
        return finish(False, [], "One of: " + ", ".join(" + ".join(b) for b in rule["options"]))
    if kind == "ls_bs_math":
        used: list[StudentCourse] = []
        seen_subject: set[str] = set()
        for course in sorted(courses, key=lambda c: (not c.done, c.term_index)):
            meta = info(course.code)
            subjects = {s.replace(" ", "") for s in meta.get("subjects", [])}
            tags = set(meta.get("tags", []))
            if not subjects & {"MATH", "COMPSCI", "STAT"} or not tags & {"level_i", "level_a"}:
                continue
            if _course_credits(course) < 3:
                continue
            capped = subjects & {"COMPSCI", "STAT"} and not subjects & {"MATH"}
            if capped:
                key = next(iter(subjects & {"COMPSCI", "STAT"}))
                if key in seen_subject:
                    continue
                seen_subject.add(key)
            used.append(course)
            if len(used) == 2:
                break
        return finish(len(used) >= 2, used, f"{2 - len(used)} more Intermediate/Advanced MATH/COMP SCI/STAT course(s)")
    return result


def run_audit(data: AuditInput) -> dict:
    catalog = data.catalog
    courses = [c for c in data.courses if c.code]
    pool = {c.code: c for c in courses}

    program_results = []
    usage: dict[str, list[str]] = {}
    for index, program in enumerate(data.programs):
        blocks = active_blocks(program, data.variants.get(program["id"]), include_college=(index == 0))
        results = _assign_program(program, blocks, pool, catalog)
        for result in results:
            for used in result["used"]:
                usage.setdefault(used["code"], [])
                if program["id"] not in usage[used["code"]]:
                    usage[used["code"]].append(program["id"])
        program_results.append({
            "id": program["id"], "name": program["name"], "degree": program["degree"],
            "college": program["college"], "guide_url": program.get("guide_url"),
            "confidence": program.get("confidence"), "blocks": results,
            "summary": _summarize(results),
        })

    shared = sorted(code for code, owners in usage.items() if len(owners) > 1)
    rule_results = [evaluate_rule(rule, courses, catalog, data) for rule in data.degree_rules + data.gened_rules]

    total_done = sum(_course_credits(c) for c in courses if c.done) + data.generic_credits
    total_planned = sum(_course_credits(c) for c in courses) + data.generic_credits
    shared_credits = sum(_course_credits(pool[code]) for code in shared)
    return {
        "programs": program_results,
        "degree": rule_results,
        "degree_summary": _summarize(rule_results),
        "shared_courses": shared,
        "shared_credits": shared_credits,
        "credits": {"completed": total_done, "planned": total_planned, "required": 120},
        "course_usage": usage,
    }


def _summarize(results: list[dict]) -> dict:
    counts = {"complete": 0, "planned": 0, "partial": 0, "missing": 0, "manual": 0}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    total = sum(counts.values()) - counts["manual"]
    satisfied = counts["complete"] + counts["planned"]
    counts["percent"] = round(100 * satisfied / total) if total else 0
    return counts
