"""Parse and evaluate UW course requisite statements.

The Guide prints requisites as prose, e.g.

    (MATH 211, 217, or 221) and STAT 240
    MATH 114 or (MATH 112 and 113) or placement into MATH 221.
        MATH 211 or 213 does not fulfill the requisite.
    COMP SCI 300 or 354. Not open to students with credit for COMP SCI 400.

``parse_requisite`` turns that into a small tree:

    {"op": "and"|"or", "args": [...]}
    {"course": "MATH 221"}
    {"placement": "MATH 221"}             placement exam route
    {"standing": "junior"}                class standing (credits earned)
    {"cond": "consent"|"graduate"|"declared"|"other", "text": "..."}

plus ``exclusions`` (anti-requisites) and ``concurrent`` (co-enrollment OK).

Evaluation is three-valued: True, False, or None ("cannot be checked by a
planner", e.g. instructor consent).  None children are ignored by both AND and
OR unless every child is None, which keeps the planner strict about courses
while never blocking on paperwork it cannot see.
"""

from __future__ import annotations

import re
from typing import Callable, Iterable

from ingest.codes import CodeIndex, clean

STANDING_CREDITS = {"freshman": 0, "first-year": 0, "sophomore": 24, "junior": 54, "senior": 86}

_CODE_RE = re.compile(r"(?<![A-Za-z0-9])((?:[A-Z&][A-Z&-]*[ /]){0,6}[A-Z][A-Z&-]*)[ ](\d{2,3})\b")
_DROP_SENTENCE = re.compile(
    r"does not (?:fulfill|satisfy|count)|do not (?:fulfill|satisfy)|not open to|recommended|"
    r"may not be taken|cannot be taken|will not count|msn eslat|required to take the .*eslat",
    re.I,
)


def _split_sentences(text: str) -> list[str]:
    # Guide text often lacks a space after periods ("MATH 221.MATH 211 ..."), so
    # split on a period followed by an optional space and an uppercase letter.
    parts = re.split(r"\.(?=\s*[A-Z(])", text)
    return [clean(part).strip(" .") for part in parts if clean(part).strip(" .")]


def _tokenize(text: str, codes: CodeIndex) -> list[tuple[str, str]]:
    """Tokens: ('(',), (')',), ('sep', and|or|,|;), ('code', canonical), ('word', w)."""

    tokens: list[tuple[str, str]] = []
    last_subject: str | None = None
    i = 0
    # Normalize glued words the scraper can produce ("221and", "orMATH").
    text = re.sub(r"(\d)(and|or)\b", r"\1 \2", text)
    text = re.sub(r"\b(and|or)([A-Z]{2})", r"\1 \2", text)
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "()":
            tokens.append((ch, ch))
            i += 1
            continue
        if ch in ",;":
            tokens.append(("sep", ch))
            i += 1
            continue
        match = _CODE_RE.match(text, i)
        if match:
            subject, number = match.group(1), match.group(2)
            # Strip leading non-subject words ("placement into MATH" -> "MATH").
            words = subject.split(" ")
            resolved = None
            for start in range(len(words)):
                candidate = " ".join(words[start:])
                resolved = codes.resolve(f"{candidate} {number}")
                if resolved:
                    for word in words[:start]:
                        tokens.append(("word", word))
                    last_subject = candidate
                    break
            if not resolved:
                # A retired or renumbered course: keep it as a course leaf so the
                # logic stays intact ("MATH 217 or 221").
                for start in range(len(words)):
                    candidate = " ".join(words[start:])
                    if codes.is_subject(candidate):
                        for word in words[:start]:
                            tokens.append(("word", word))
                        last_subject = candidate
                        resolved = f"{candidate} {number}"
                        break
            if resolved:
                tokens.append(("code", resolved))
                i = match.end()
                continue
        match = re.compile(r"\d{2,3}\b").match(text, i)
        if match and last_subject:
            resolved = codes.resolve(f"{last_subject} {match.group(0)}") or f"{last_subject} {match.group(0)}"
            tokens.append(("code", resolved))
            i = match.end()
            continue
        match = re.compile(r"[^\s(),;]+").match(text, i)
        word = match.group(0)
        low = word.lower()
        if low in {"and", "or"}:
            tokens.append(("sep", low))
        else:
            tokens.append(("word", word))
        i = match.end()
    return tokens


def _group(tokens: list[tuple[str, str]]) -> list:
    """Nest parentheses into sub-lists."""

    stack: list[list] = [[]]
    for token in tokens:
        if token[0] == "(":
            stack.append([])
        elif token[0] == ")":
            if len(stack) > 1:
                inner = stack.pop()
                stack[-1].append(inner)
        else:
            stack[-1].append(token)
    while len(stack) > 1:
        inner = stack.pop()
        stack[-1].append(inner)
    return stack[0]


def _leaf_from_words(words: list[str], code: str | None) -> dict | None:
    coreq = "COREQ" in words
    words = [w for w in words if w != "COREQ"]
    text = " ".join(words).strip()
    low = text.lower()
    if code:
        if coreq:
            return {"course": code, "coreq": True}
        if "placement" in low:
            return {"placement": code}
        if re.search(r"concurrent|prior to|or equivalent|or higher|with a grade", low) or not text:
            return {"course": code}
        return {"course": code}
    if not text:
        return None
    if "placement" in low or "placement score" in low:
        return {"placement": None, "text": text}
    for standing in ("sophomore", "junior", "senior", "freshman", "first-year"):
        if re.search(rf"\b{standing}\b", low) and "standing" in low:
            return {"standing": standing}
    if "consent" in low:
        return {"cond": "consent", "text": text}
    if re.search(r"graduate|professional standing|grad/prof", low):
        return {"cond": "graduate", "text": text}
    if re.search(r"declared|admitted|enrolled in|member of|program", low):
        return {"cond": "declared", "text": text}
    return {"cond": "other", "text": text}


def _parse_items(items: list) -> dict | None:
    # Split into operands on separators, remembering which separator joined them.
    operands: list[list] = [[]]
    seps: list[str] = []
    for item in items:
        if isinstance(item, tuple) and item[0] == "sep":
            if operands[-1]:
                operands.append([])
                seps.append(item[1])
            elif seps:
                # ", or" -- the conjunction overrides the comma before it
                seps[-1] = item[1] if item[1] in {"and", "or"} else seps[-1]
            continue
        operands[-1].append(item)
    if not operands[-1]:
        operands.pop()
    nodes = [_operand(op) for op in operands]
    pairs = [(node, sep) for node, sep in zip(nodes, seps + [None])]
    nodes = [node for node in nodes if node is not None]
    if not nodes:
        return None
    if len(nodes) == 1:
        return nodes[0]

    # Resolve commas to the conjunction that closes their list.
    resolved: list[str] = []
    for index, sep in enumerate(seps):
        if sep == ",":
            nxt = next((s for s in seps[index + 1:] if s in {"and", "or", ";"}), None)
            prv = next((s for s in reversed(seps[:index]) if s in {"and", "or"}), None)
            resolved.append(nxt if nxt in {"and", "or"} else (prv or "and"))
        else:
            resolved.append("and" if sep == ";" else sep)

    raw_nodes = [node for node, _ in pairs]
    # AND binds looser than OR at the same level only when separated by ';'.
    groups: list[list] = [[raw_nodes[0]]]
    group_ops: list[str] = []
    for node, op in zip(raw_nodes[1:], resolved):
        groups[-1].append((op, node))
    # Build: split on 'and' first, each part an OR-list.
    and_parts: list[list] = [[raw_nodes[0]]]
    for node, op in zip(raw_nodes[1:], resolved):
        if op == "and":
            and_parts.append([node])
        else:
            and_parts[-1].append(node)
    built = []
    for part in and_parts:
        part = [n for n in part if n is not None]
        if not part:
            continue
        built.append(part[0] if len(part) == 1 else {"op": "or", "args": part})
    if not built:
        return None
    return built[0] if len(built) == 1 else {"op": "and", "args": built}


def _operand(items: list) -> dict | None:
    if len(items) == 1 and isinstance(items[0], list):
        return _parse_items(items[0])
    codes = [item[1] for item in items if isinstance(item, tuple) and item[0] == "code"]
    sub = [item for item in items if isinstance(item, list)]
    words = [item[1] for item in items if isinstance(item, tuple) and item[0] == "word"]
    parts: list[dict] = []
    for group in sub:
        node = _parse_items(group)
        if node:
            parts.append(node)
    if len(codes) > 1:
        # Adjacent codes without separators ("MATH 112 113") -> all required.
        parts.extend({"course": code} for code in codes)
        return {"op": "and", "args": parts} if len(parts) > 1 else parts[0]
    leaf = _leaf_from_words(words, codes[0] if codes else None)
    if leaf:
        parts.append(leaf)
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else {"op": "and", "args": parts}


def parse_requisite(text: str, codes: CodeIndex) -> dict:
    """Return {'tree', 'exclusions', 'concurrent', 'text'} for a Guide requisite string."""

    text = clean(text)
    result = {"tree": None, "exclusions": [], "concurrent": False, "text": text}
    if not text or text.lower() in {"none", "none."}:
        return result
    kept: list[str] = []
    for sentence in _split_sentences(text):
        match = re.search(r"[;,]?\s*not open to", sentence, re.I)
        if match:
            tail = sentence[match.start():]
            result["exclusions"] = sorted(set(result["exclusions"]) | {tok[1] for tok in _tokenize(tail, codes) if tok[0] == "code"})
            sentence = sentence[: match.start()].strip(" ;,")
            if not sentence:
                continue
        if _DROP_SENTENCE.search(sentence):
            continue
        kept.append(sentence)
    body = "; ".join(kept)
    # Historical notes such as "(215 prior to Fall 2024)" or "(or AGRONOMY 103
    # prior to Fall 2025)" describe retired equivalents, not extra requirements.
    body = re.sub(r"\((?:or\s+)?[^(),]*\bprior to\b[^(),]*\)", " ", body, flags=re.I)
    # Inline "..., or MATH 211 prior to Fall 2024" keeps the conjunction but the
    # retired option becomes an unverifiable leaf.
    body = re.sub(r"(?:[A-Z][A-Z &/]*\s)?\d{2,3}\s+prior to (?:Fall|Spring|Summer)\s+\d{4}", "retired-option", body)
    # "concurrent enrollment in MUSIC 172" -> co-requisite leaf for that course
    body = re.sub(r"(?:or\s+)?(?:concurrent|concurrently)\s+(?:enrollment|enrolled)\s+in\s+", " COREQ ", body, flags=re.I)
    if re.search(r"concurrent", body, re.I):
        # "... or concurrent enrollment" applies to the whole statement
        result["concurrent"] = True
        body = re.sub(r"\(?\s*(?:or\s+)?concurrent(?: enrollment)?\s*\)?", " ", body, flags=re.I)
    if not body:
        return result
    tree = _parse_items(_group(_tokenize(body, codes)))
    result["tree"] = _simplify(tree)
    return result


def _simplify(node: dict | None) -> dict | None:
    if not node or "op" not in node:
        return node
    args = []
    for child in node["args"]:
        child = _simplify(child)
        if child is None:
            continue
        if child.get("op") == node["op"]:
            args.extend(child["args"])
        else:
            args.append(child)
    unique = []
    for arg in args:
        if arg not in unique:
            unique.append(arg)
    if not unique:
        return None
    if len(unique) == 1:
        return unique[0]
    return {"op": node["op"], "args": unique}


def coreqs_in(node: dict | None) -> set[str]:
    """Courses that may (must) be taken in the same term."""

    if not node:
        return set()
    if "op" in node:
        found: set[str] = set()
        for arg in node["args"]:
            found |= coreqs_in(arg)
        return found
    return {node["course"]} if node.get("coreq") else set()


def courses_in(node: dict | None) -> set[str]:
    if not node:
        return set()
    if "op" in node:
        found: set[str] = set()
        for arg in node["args"]:
            found |= courses_in(arg)
        return found
    if node.get("course"):
        return {node["course"]}
    return set()


def evaluate(
    node: dict | None,
    has_course: Callable[[str], bool],
    *,
    credits_earned: float = 0,
    assume_placement: bool | Callable[[str | None], bool] = True,
    coreq_ok: Callable[[str], bool] | None = None,
) -> bool | None:
    """Three-valued evaluation.

    ``assume_placement`` is either a bool or a callable deciding whether the
    student placed into the course named by a placement leaf (e.g. math
    placement into MATH 221).
    """

    if node is None:
        return True
    if "op" in node:
        values = [
            evaluate(arg, has_course, credits_earned=credits_earned, assume_placement=assume_placement, coreq_ok=coreq_ok)
            for arg in node["args"]
        ]
        known = [value for value in values if value is not None]
        if not known:
            return None
        return all(known) if node["op"] == "and" else any(known)
    if "course" in node:
        if node.get("coreq") and coreq_ok is not None and coreq_ok(node["course"]):
            return True
        return has_course(node["course"])
    if "placement" in node:
        if node.get("placement") and has_course(node["placement"]):
            return True
        placed = assume_placement(node.get("placement")) if callable(assume_placement) else assume_placement
        return True if placed else False
    if "standing" in node:
        return credits_earned >= STANDING_CREDITS.get(node["standing"], 0)
    # Graduate standing, instructor consent, program declaration, etc. are
    # alternative routes a planner cannot verify: never block on them.
    return None


def missing_for(node: dict | None, has_course: Callable[[str], bool], **kwargs) -> list[str]:
    """Human-readable description of what is still missing."""

    if evaluate(node, has_course, **kwargs) in (True, None):
        return []
    return [describe(node)]


def describe(node: dict | None) -> str:
    if not node:
        return ""
    if "op" in node:
        joiner = " and " if node["op"] == "and" else " or "
        inner = [describe(arg) for arg in node["args"]]
        inner = [f"({text})" if " and " in text or " or " in text else text for text in inner]
        return joiner.join(text for text in inner if text)
    if "course" in node:
        return f"{node['course']} (same term OK)" if node.get("coreq") else node["course"]
    if "placement" in node:
        return f"placement into {node['placement']}" if node.get("placement") else "placement exam"
    if "standing" in node:
        return f"{node['standing']} standing"
    text = node.get("text", "")
    return "" if text == "retired-option" else text


def cheapest_path(
    node: dict | None,
    cost: Callable[[str], float],
    has_course: Callable[[str], bool],
    placement_ok: Callable[[str | None], bool] | None = None,
) -> tuple[float, list[str]]:
    """Pick the lowest-cost set of courses that satisfies ``node``.

    Used to expand prerequisite chains: for OR nodes choose the branch that is
    already satisfied or cheapest to complete.
    """

    if node is None:
        return 0.0, []
    if "op" in node:
        results = [cheapest_path(arg, cost, has_course, placement_ok) for arg in node["args"]]
        if node["op"] == "and":
            total, courses = 0.0, []
            for arg, (value, chosen) in zip(node["args"], results):
                if value == float("inf"):
                    if _has_course_route(arg):
                        return float("inf"), []  # a required course that cannot be taken
                    continue
                total += value
                courses.extend(code for code in chosen if code not in courses)
            return total, courses
        routes = [
            result for arg, result in zip(node["args"], results)
            if result[0] != float("inf") and _has_course_route(arg)
        ]
        if not routes:
            return 0.0, []
        return min(routes, key=lambda result: (result[0], len(result[1])))
    if "course" in node:
        code = node["course"]
        if has_course(code):
            return 0.0, []
        return cost(code), [code]
    if "placement" in node:
        if placement_ok is None or placement_ok(node.get("placement")):
            return 0.0, []
        return float("inf"), []
    # Unverifiable conditions (consent, declared, "Satisfied QR-A" ...) cost
    # nothing inside AND; inside OR they are skipped as routes (see above).
    return 0.0, []


def _has_course_route(node: dict | None) -> bool:
    if not node:
        return False
    if "op" in node:
        return any(_has_course_route(arg) for arg in node["args"])
    return "course" in node or "placement" in node


def all_codes(nodes: Iterable[dict | None]) -> set[str]:
    found: set[str] = set()
    for node in nodes:
        found |= courses_in(node)
    return found
