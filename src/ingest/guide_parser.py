"""Turn raw UW Guide extractions into structured requirement trees.

Input is the compact JSON produced by ``scripts/scrape_uw_guide.py`` (or the
equivalent in-browser extractor): each program page is a flat list of items

    ["h", level, text]            heading
    ["t", text]                   paragraph / list text
    ["c", rows]                   sc_courselist table
    ["g", class, rows]            text requirement table (Core GenEd, L&S BS ...)

and each course-list row is

    [row_class, code_or_comment_text, [linked codes], title, hours,
     is_comment, is_areaheader, is_indented]

Output model (per program)::

    block  = one requirement the student must satisfy
      rule   all | choose | credits | text
      count  number of slots needed (choose)
      credits minimum credits (credits)
      slots  -> list of alternatives; each alternative is an AND-bundle of codes

Every block records ``confidence``: ``high`` when the rule came from explicit
wording ("Complete two:"), ``medium`` when inferred, ``low`` when the parser
could only keep the course pool and the student must verify in the Guide.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json
import re
from typing import Iterable

from .codes import CodeIndex, clean, parse_credit_range

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "a": 1, "an": 1, "single": 1,
}
NUM = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"

SKIP_SECTION = re.compile(
    r"honors|residence|quality of work|gpa and other|footnote|career|additional information|"
    r"certification|continuation|learning outcomes|summary of|how to get in|admission|"
    r"four-year plan|advising|potential|non.l&s students",
    re.I,
)
UNIVERSITY_SECTION = re.compile(r"^university", re.I)
COLLEGE_SECTION = re.compile(
    r"^(college of|school of)|bba requirements|common requirements|breadth and degree|"
    r"degree requirements:|^cals|school of business requirements",
    re.I,
)
# A heading whose *children* are alternatives ("Named Options", "Focus Areas").
VARIANT_HEADING = re.compile(
    r"named options?|options in the major|major options|program options|focus areas|"
    r"emphases|concentrations|\btracks\b|regions of emphasis|select one of the following options",
    re.I,
)
# A heading that *is* one alternative ("Classics–Latin Emphasis", "Option A: ...").
SINGLE_VARIANT = re.compile(r"\bemphasis\b|^option\s+\w\b|\btrack\b|\bconcentration\b|\bfocus area\b", re.I)
OPTION_HEADER = re.compile(r"^(option|sequence|track|path(way)?)\s*[\w\d]{0,3}\b", re.I)


@dataclass
class Slot:
    label: str
    options: list[list[str]] = field(default_factory=list)  # OR of AND-bundles
    credits: tuple[float, float] | None = None
    unresolved: list[str] = field(default_factory=list)


@dataclass
class Block:
    key: str
    section: str  # college | major
    path: list[str]
    name: str
    rule: str  # all | choose | credits | text
    count: int | None = None
    credits: float | None = None
    slots: list[Slot] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    variant_group: str | None = None
    variant: str | None = None
    confidence: str = "high"
    header_credits: tuple[float, float] | None = None
    context: list[str] = field(default_factory=list)
    explicit: bool = True


def parse_rule(text: str) -> tuple[str | None, int | None, float | None]:
    """Interpret a requirement phrase.  Returns (rule, count, credits)."""

    t = clean(text).lower()
    if not t:
        return None, None, None
    m = re.search(rf"\bone (?:course )?(?:each )?from (?:at least )?{NUM} (?:of|out of) (?:the|these) {NUM}\b", t)
    if m:
        word = m.group(1)
        count = int(word) if word.isdigit() else WORD_NUMBERS.get(word)
        if count:
            return "choose", count, None
    m = re.search(rf"(?:at least|minimum of|a minimum of|complete|select|choose|take|earn)?\s*(\d+(?:\.\d+)?|{NUM[1:-1]})\s*(?:-\s*\d+\s*)?(?:additional\s+)?credits?\b", t)
    if m and re.search(r"complete|select|choose|take|earn|at least|minimum|from|of|require", t):
        value = m.group(1)
        amount = float(value) if value[0].isdigit() else float(WORD_NUMBERS.get(value, 0))
        if amount:
            return "credits", None, amount
    if re.search(r"\b(complete|select|choose|take)\s+(all|both|each)\b|complete the following|required course|complete these|all of the following", t):
        return "all", None, None
    m = re.search(
        rf"\b(?:complete|select|choose|take|pick)\s+(?:at least\s+)?{NUM}\b(?!\s*credit)", t
    ) or re.search(rf"^(?:at least\s+)?{NUM}\s+(?:course|courses|class|classes|of|from|sequence|option)\b", t) or re.search(
        rf"\(\s*(?:complete|select|choose)\s+{NUM}\b", t
    ) or re.search(rf"\b{NUM}\s+(?:course|courses)\s+from\b", t) or re.search(rf"\b(?:at least|minimum of)\s+{NUM}\s+(?:course|courses|of)\b", t)
    if m:
        word = m.group(1)
        count = int(word) if word.isdigit() else WORD_NUMBERS.get(word)
        if count:
            return "choose", count, None
    m = re.search(rf"\b{NUM}\s+(?:courses?\s+)?(?:are\s+)?required\b", t)
    if m:
        word = m.group(1)
        count = int(word) if word.isdigit() else WORD_NUMBERS.get(word)
        if count:
            return "choose", count, None
    if re.search(r"one of the following|one from|one course from|either\b", t):
        return "choose", 1, None
    return None, None, None


def _degree_from_name(name: str) -> str:
    match = re.search(r",\s*([A-Z][A-Za-z]*(?:\s+AMEP)?)\s*(?:\(|$)", name)
    return match.group(1) if match else ""


def _classify_h2(text: str) -> str:
    if UNIVERSITY_SECTION.search(text):
        return "university"
    if COLLEGE_SECTION.search(text) and not re.search(r"major requirements|curriculum", text, re.I):
        return "college"
    if SKIP_SECTION.search(text):
        return "skip"
    return "major"


def _rule_only_header(text: str) -> bool:
    """True when a header row is only an instruction ('Complete one:')."""

    stripped = re.sub(r"[:.]", "", clean(text)).lower()
    rule, _, _ = parse_rule(stripped)
    if rule is None:
        return False
    words = re.sub(rf"\b(complete|select|choose|take|at least|the|following|of|from|courses?|{NUM[1:-1]}|credits?|\d+|all|both|options?|below|list|these|may be satisfied by placement exam|or)\b", "", stripped)
    return len(words.strip(" ()")) < 6


class ProgramParser:
    def __init__(self, codes: CodeIndex, credits: dict[str, float] | None = None) -> None:
        self.codes = codes
        self.credits = credits or {}
        self.unresolved: set[str] = set()

    # ----------------------------------------------------------------- public
    def parse(self, raw: dict) -> dict:
        name = clean(raw.get("name") or raw.get("title"))
        crumbs = raw.get("crumbs") or []
        href = raw["href"]
        program = {
            "id": href.strip("/").split("/")[-1],
            "name": name,
            "degree": _degree_from_name(name),
            "college": crumbs[2] if len(crumbs) > 2 else "",
            "department": crumbs[3] if len(crumbs) > 3 else "",
            "url": "https://guide.wisc.edu" + href,
            "college_section": None,
            "blocks": [],
            "notes": [],
            "sample_plan": self._parse_plan(raw.get("plan") or []),
        }

        section_kind = "university"
        path: list[str] = [""] * 5
        pending_text: list[str] = []
        level_text: dict[int, list[str]] = {}
        current_level = 2
        variant_group: str | None = None
        variant_level = 0
        sibling_variant: tuple[str, str] | None = None
        sibling_level = 0
        blocks: list[Block] = []
        table_index = 0

        for item in raw.get("items", []):
            kind = item[0]
            if kind == "h":
                level, text = item[1], clean(re.sub(r"\d+$", "", item[2]))
                current_level = level
                for deeper in list(level_text):
                    if deeper >= level:
                        level_text.pop(deeper)
                path[level - 1] = text
                for deeper in range(level, 5):
                    path[deeper] = ""
                if level == 2:
                    section_kind = _classify_h2(text)
                    if section_kind == "college":
                        program["college_section"] = text
                    variant_group = None
                    if VARIANT_HEADING.search(text) and section_kind == "major":
                        variant_group, variant_level = text, 2
                elif variant_group and level <= variant_level:
                    variant_group = None
                if sibling_variant and level <= sibling_level:
                    sibling_variant = None
                if level > 2 and section_kind == "major" and VARIANT_HEADING.search(text) and not variant_group:
                    variant_group, variant_level = text, level
                elif level > 2 and section_kind == "major" and not variant_group and SINGLE_VARIANT.search(text):
                    parent = path[level - 2] or "Emphasis"
                    sibling_variant = (f"{parent} (choose one)", text)
                    sibling_level = level
                pending_text = []
                continue
            if kind == "t":
                pending_text.append(clean(item[1]))
                level_text.setdefault(current_level, []).append(clean(item[1]))
                if section_kind == "major" and re.search(r"\b\d+\s+credits\b", item[1]) and len(item[1]) < 400:
                    program["notes"].append(clean(item[1]))
                continue
            if kind != "c" or section_kind in {"university", "skip"}:
                continue
            if any(re.search(r"summary of|^summary", p, re.I) for p in path if p):
                continue
            table_index += 1
            heading_path = [p for p in path[1:] if p]
            variant = None
            group_name = variant_group
            if variant_group:
                depth = variant_level  # headings below the variant heading name the variant
                variant = path[depth] if depth < 5 and path[depth] else None
            elif sibling_variant:
                group_name, variant = sibling_variant
            new_blocks = self._parse_table(
                item[1],
                section="college" if section_kind == "college" else "major",
                path=heading_path,
                preface=pending_text[-2:],
                key_prefix=f"{program['id']}:{table_index}",
            )
            # nearest heading level first; natural order within a level
            ancestors = [t for lvl in sorted(level_text, reverse=True) if lvl < current_level for t in level_text[lvl]]
            for block in new_blocks:
                block.context = ancestors[:4]
                if group_name and variant:
                    block.variant_group, block.variant = group_name, variant
            blocks.extend(new_blocks)
            pending_text = []

        blocks = self._merge_pools(blocks)
        program["blocks"] = [self._block_dict(block) for block in blocks]
        program["variants"] = sorted({(b.variant_group, b.variant) for b in blocks if b.variant}, key=lambda x: (x[0], x[1]))
        program["variants"] = [{"group": g, "name": v} for g, v in program["variants"]]
        major_blocks = [b for b in blocks if b.section == "major"]
        program["confidence"] = _program_confidence(major_blocks)
        return program

    # ------------------------------------------------------------- internals
    def _resolve(self, codes: Iterable[str]) -> tuple[list[str], list[str]]:
        resolved, missing = [], []
        for code in codes:
            canonical = self.codes.resolve(code)
            if canonical:
                if canonical not in resolved:
                    resolved.append(canonical)
            else:
                missing.append(clean(code))
                self.unresolved.add(clean(code))
        return resolved, missing

    def _segments(self, rows: list[list]) -> list[dict]:
        """Split a course list into header-led segments.

        A segment carries an optional ``header`` (a label such as "Chemistry"),
        an optional ``rule_text`` ("Complete one of the following:") and notes.
        """

        segments: list[dict] = []
        current = {"header": None, "rule_text": None, "hours": "", "rows": [], "sub": False, "notes": []}
        self._listsum = None
        for row in rows:
            cls, text, codes, title, hours, is_comment, is_area, indent = (row + [0] * 8)[:8]
            if "listsum" in cls:
                total = parse_credit_range(hours)
                if total[1]:
                    self._listsum = total
                continue
            text = clean(text)
            is_header = "areaheader" in cls or "areasubheader" in cls or (is_comment and not codes)
            if is_header and text.lower() in {"or", "and"}:
                current["rows"].append(["__joiner__", text.lower()])
                continue
            if is_header:
                has_rule = parse_rule(text)[0] is not None
                if not current["rows"] and (current["header"] or current["rule_text"]):
                    # Consecutive header-like rows describe one segment.
                    if has_rule and not current["rule_text"] and not OPTION_HEADER.match(text):
                        current["rule_text"] = text
                        current["hours"] = current["hours"] or hours
                        continue
                    if not has_rule and not is_area and current["rule_text"] and not OPTION_HEADER.match(text):
                        current["notes"].append(text)
                        continue
                if current["rows"] and not has_rule and not is_area and "areasubheader" not in cls and len(text) > 60:
                    current["notes"].append(text)
                    continue
                if current["rows"] or current["header"] or current["rule_text"]:
                    segments.append(current)
                label_is_rule = has_rule and _rule_only_header(text)
                current = {
                    "header": None if label_is_rule else text,
                    "rule_text": text if has_rule else None,
                    "hours": hours,
                    "rows": [],
                    "sub": "areasubheader" in cls,
                    "notes": [],
                }
                continue
            current["rows"].append(row)
        if current["rows"] or current["header"] or current["rule_text"]:
            segments.append(current)
        return segments

    def _slots_from_rows(self, rows: list[list]) -> tuple[list[Slot], list[str]]:
        slots: list[Slot] = []
        notes: list[str] = []
        join_next_as_or = False
        for row in rows:
            if row and row[0] == "__joiner__":
                join_next_as_or = row[1] == "or"
                continue
            cls, text, codes, title, hours = (row + [""] * 5)[:5]
            text = clean(text)
            if not codes:
                # free-text row: "Complete Requirements 15", "Any ART course"
                if text:
                    low, high = parse_credit_range(hours) if hours else (0, 0)
                    slots.append(Slot(label=text, options=[], credits=(low, high) if high else None))
                continue
            resolved, missing = self._resolve(codes)
            bundle = resolved
            credit = parse_credit_range(hours) if hours else None
            is_alt = "orclass" in cls or text.lower().startswith("or ") or join_next_as_or
            join_next_as_or = False
            if is_alt and slots:
                if bundle:
                    slots[-1].options.append(bundle)
                slots[-1].unresolved.extend(missing)
                continue
            label = clean(title) or text
            slot = Slot(label=label, options=[bundle] if bundle else [], credits=credit if credit and credit[1] else None, unresolved=missing)
            slots.append(slot)
        return slots, notes

    def _parse_table(self, rows, *, section, path, preface, key_prefix) -> list[Block]:
        segments = self._segments(rows)
        blocks: list[Block] = []
        base_name = path[-1] if path else "Requirements"
        preface_rule = (None, None, None)
        for text in reversed(preface):
            # Long paragraphs: the rule is almost always in the first sentences.
            for sentence in re.split(r"(?<=[.:])\s+", text)[:3]:
                if len(sentence) < 240:
                    preface_rule = parse_rule(sentence)
                    if preface_rule[0]:
                        break
            if preface_rule[0]:
                break
        recommended = any(re.search(r"recommended|suggested", p, re.I) for p in path[-1:])

        group_label: str | None = None
        i = 0
        seg_no = 0
        while i < len(segments):
            seg = segments[i]
            seg_no += 1
            header = seg["header"] or ""
            rule_text = seg["rule_text"] or ""
            rule, count, credits = parse_rule(rule_text) if rule_text else (None, None, None)
            header_credits = parse_credit_range(seg["hours"]) if seg["hours"] else None
            if header_credits and not header_credits[1]:
                header_credits = None
            key = f"{key_prefix}.{seg_no}"

            def block_name(label: str | None) -> str:
                parts = [base_name]
                if group_label and group_label != base_name:
                    parts.append(group_label)
                if label and len(label) > 70:
                    label = None
                if label and label not in parts:
                    short = re.sub(r"\s*\((complete|select|choose)[^)]*\)", "", label, flags=re.I)
                    short = re.sub(r":\s*(complete|select|choose).*$", "", short, flags=re.I).rstrip(": ")
                    if short:
                        parts.append(short)
                return " › ".join(parts)

            # --- "Option 1 / Option 2" alternatives -------------------------
            option_run: list[dict] = []
            j = i
            if OPTION_HEADER.match(header):
                while j < len(segments) and OPTION_HEADER.match(segments[j]["header"] or ""):
                    option_run.append(segments[j])
                    j += 1
                group_count = count if rule == "choose" else (preface_rule[1] if preface_rule[0] == "choose" else 1)
                label = None
            elif not seg["rows"] and rule == "choose" and i + 1 < len(segments) and OPTION_HEADER.match(segments[i + 1]["header"] or ""):
                j = i + 1
                while j < len(segments) and OPTION_HEADER.match(segments[j]["header"] or ""):
                    option_run.append(segments[j])
                    j += 1
                group_count = count or 1
                label = header or None
            if len(option_run) >= 2:
                slots = []
                for opt in option_run:
                    inner, _ = self._slots_from_rows(opt["rows"])
                    bundle: list[str] = []
                    for s in inner:
                        for code in (s.options[0] if s.options else []):
                            if code not in bundle:
                                bundle.append(code)
                    slots.append(Slot(label=(opt["header"] or "Option").rstrip(":"), options=[bundle] if bundle else []))
                blocks.append(Block(key=key, section=section, path=path, name=block_name(label),
                                    rule="choose", count=group_count or 1, slots=slots, confidence="high"))
                i = j
                continue

            slots, _ = self._slots_from_rows(seg["rows"])
            course_slots = [s for s in slots if s.options]
            text_slots = [s for s in slots if not s.options]
            notes = list(seg["notes"]) + [s.label for s in text_slots]

            # --- label-only header ("Chemistry", "Core") --------------------
            if not seg["rows"] and header and not rule and not header_credits and len(header) <= 60:
                group_label = header.rstrip(":")
                i += 1
                continue

            # --- credit pool whose courses sit in following sub-headers ------
            if not course_slots:
                pattern = _parse_pattern(" ".join([rule_text, header] + notes))
                pool_slots: list[Slot] = []
                k = i + 1
                if (rule == "credits" or header_credits) and not pattern:
                    while k < len(segments) and segments[k]["sub"]:
                        inner, _ = self._slots_from_rows(segments[k]["rows"])
                        pool_slots.extend(s for s in inner if s.options)
                        k += 1
                if pool_slots:
                    blocks.append(Block(key=key, section=section, path=path, name=block_name(header or None),
                                        rule="credits", credits=credits or header_credits[0], slots=pool_slots,
                                        notes=notes[:4], confidence="medium"))
                    i = k
                    continue
                label = header or rule_text or "; ".join(notes)
                if not label:
                    i += 1
                    continue
                credit_hint = credits or (header_credits[0] if header_credits else None) or next(
                    (s.credits[0] for s in text_slots if s.credits), None)
                block = Block(key=key, section=section, path=path, name=block_name(header or None),
                              rule="text", credits=credit_hint, notes=([rule_text] if rule_text else []) + notes[:4],
                              confidence="low")
                if pattern:
                    block.rule = "pattern"
                    block.credits = pattern.get("credits") or credit_hint
                    block.count = pattern.get("count")
                    block.notes.insert(0, "PATTERN:" + json.dumps(pattern))
                    block.confidence = "medium"
                blocks.append(block)
                i += 1
                continue

            confidence = "high"
            if not rule:
                for text in notes:
                    r2, c2, cr2 = parse_rule(text)
                    if r2:
                        rule, count, credits = r2, c2, cr2
                        break
            if not rule and (len(segments) == 1 or (i == 0 and not header)):
                heading_rule = parse_rule(base_name)
                if heading_rule[0]:
                    rule, count, credits = heading_rule
            if not rule and i == 0 and preface_rule[0]:
                rule, count, credits = preface_rule
                confidence = "medium"
            explicit = bool(rule)
            if not rule:
                total = self._slot_credit_sum(course_slots)
                limit = header_credits or (self._listsum if len(segments) == 1 else None)
                if limit and len(course_slots) > 1 and total:
                    if total <= max(limit[1] + 0.5, limit[1] * 1.15):
                        rule, confidence = "all", "high"
                    else:
                        rule, credits, confidence = "credits", limit[0], "medium"
                if not rule:
                    if len(course_slots) > 8:
                        rule, confidence = "pool", "low"
                    elif len(course_slots) > 5:
                        rule, count, confidence = "choose", 1, "low"
                    else:
                        rule = "all"
                        confidence = "high" if (not header or seg["sub"] or len(course_slots) <= 4) else "medium"
            if rule == "choose" and count and count >= len(course_slots):
                rule, count = "all", None
            block = Block(key=key, section=section, path=path, name=block_name(header or None),
                          rule=rule, count=count, credits=credits, slots=course_slots,
                          notes=notes[:4], confidence=confidence, header_credits=header_credits,
                          explicit=explicit and confidence != "low")
            if recommended:
                block.rule, block.confidence = "recommended", "high"
            blocks.append(block)
            i += 1
        return blocks

    def _slot_credit_sum(self, slots: list[Slot]) -> float:
        total = 0.0
        for slot in slots:
            if slot.credits:
                total += slot.credits[0]
            elif slot.options:
                total += sum(self.credits.get(code, 3.0) for code in slot.options[0])
        return total

    def _merge_pools(self, blocks: list[Block]) -> list[Block]:
        """Merge sibling category tables governed by one parent sentence.

        e.g. History: "one course from four of the eight geographic breadth
        categories" followed by eight category tables -> one choose-4 block.
        Biology: "Minimum of 13 credits" over categories A–E -> one 13-credit block.
        """

        def parent_rule(block: Block):
            for text in block.context:  # nearest heading level first
                rule, count, credits = parse_rule(text)
                if rule in {"choose", "credits"}:
                    return rule, count, credits
            return None

        merged: list[Block] = []
        i = 0
        while i < len(blocks):
            block = blocks[i]
            group = [block]
            j = i + 1
            while (
                j < len(blocks)
                and len(block.path) >= 2
                and blocks[j].path[:-1] == block.path[:-1]
                and blocks[j].path != block.path
                and blocks[j].variant == block.variant
                and blocks[j].section == block.section
                and _mergeable(blocks[j])
                and _mergeable(block)
                and blocks[j].slots
            ):
                group.append(blocks[j])
                j += 1
            governing = parent_rule(block) if len(group) >= 2 else None
            if governing:
                rule, count, credits = governing
                slots: list[Slot] = []
                seen: set[str] = set()
                for member in group:
                    for slot in member.slots:
                        key = slot.options[0][0] if slot.options and slot.options[0] else slot.label
                        if key not in seen:
                            seen.add(key)
                            slots.append(slot)
                merged.append(Block(
                    key=block.key, section=block.section, path=block.path[:-1],
                    name=" › ".join(block.path[:-1][-1:]) or block.name, rule=rule, count=count, credits=credits,
                    slots=slots, notes=[f"Categories: {', '.join(m.path[-1] for m in group)}"],
                    variant_group=block.variant_group, variant=block.variant, confidence="medium",
                    context=block.context,
                ))
                i = j
                continue
            merged.append(block)
            i += 1

        for block in merged:
            if block.rule == "pool":
                credits = block.header_credits[0] if block.header_credits else None
                governing = parent_rule(block)
                if credits:
                    block.rule, block.credits, block.confidence = "credits", credits, "medium"
                elif governing:
                    block.rule, block.count, block.credits = governing
                    block.confidence = "medium"
                else:
                    block.rule, block.count, block.confidence = "choose", 1, "low"
            if block.rule == "text" and block.credits is None:
                for text in block.notes + block.context[:1]:
                    r, _, c = parse_rule(text)
                    if r == "credits" and c:
                        block.credits = c
                        break
        return merged

    def _block_dict(self, block: Block) -> dict:
        data = asdict(block)
        data.pop("header_credits", None)
        data.pop("context", None)
        for slot in data["slots"]:
            if slot["credits"]:
                slot["credits"] = list(slot["credits"])
        return data

    def _parse_plan(self, tables: list) -> list[dict]:
        terms: list[dict] = []
        for table in tables[:1]:
            year = ""
            columns: list[str] = []
            for row in table:
                if len(row) == 1:
                    year = row[0]
                    continue
                if row and row[0] in {"Fall", "Spring", "Summer"}:
                    columns = [cell for cell in row if cell not in {"Credits", ""}]
                    for season in columns:
                        terms.append({"year": year, "term": season, "items": []})
                    continue
                if not columns or not row or row[0].startswith("Total"):
                    continue
                pairs = [row[k:k + 2] for k in range(0, len(row), 2)]
                recent = terms[-len(columns):]
                for term, pair in zip(recent, pairs):
                    if pair and pair[0]:
                        credits = parse_credit_range(pair[1] if len(pair) > 1 else "")[0]
                        text = clean(pair[0])
                        codes = re.findall(r"[A-Z][A-Z &/]{0,20}?\s\d{3}", text)
                        resolved = [self.codes.resolve(code) for code in codes]
                        term["items"].append({
                            "text": text,
                            "credits": credits,
                            "codes": [code for code in resolved if code],
                        })
        return terms


def _parse_pattern(text: str) -> dict | None:
    """'15 credits of A A E courses numbered 200 or above' -> subject/number rule."""

    t = clean(text)
    m = re.search(
        r"(?:(\d+)\s+(?:additional\s+)?(?:credits?|courses?)\s+(?:of|in|from)?\s*)?(?:any\s+)?"
        r"([A-Z][A-Z&]*(?:\s[A-Z&]+)*?)\s+(?:courses?|credits?)(?:\s+numbered\s+(\d{3})\s*(?:or|and)\s*(?:above|higher|greater))?",
        t,
    )
    if not m or not m.group(2):
        return None
    subject = m.group(2).strip()
    if subject in {"A", "ANY", "THE", "OR", "AND", "ALL"} or len(subject) > 14:
        return None
    if not re.search(r"\bany\b|numbered|credits? (?:of|in)", t, re.I):
        return None
    amount = int(m.group(1)) if m.group(1) else None
    is_courses = bool(m.group(1)) and re.search(rf"{m.group(1)}\s+(?:additional\s+)?courses?", t)
    return {
        "subjects": [subject],
        "min_number": int(m.group(3)) if m.group(3) else None,
        "credits": None if is_courses else amount,
        "count": amount if is_courses else (1 if not amount else None),
    }


def _mergeable(block: "Block") -> bool:
    """Only uncertain category lists are merged under a parent sentence."""

    return block.rule == "pool" or (block.rule == "choose" and block.confidence == "low")


def _sum_credits(slots: list[Slot]) -> float:
    total = 0.0
    for slot in slots:
        if slot.credits:
            total += slot.credits[0]
    return total


def _program_confidence(blocks: list[Block]) -> str:
    if not blocks:
        return "none"
    low = sum(1 for block in blocks if block.confidence == "low")
    if low == 0:
        return "high"
    if low / len(blocks) <= 0.34:
        return "medium"
    return "low"
