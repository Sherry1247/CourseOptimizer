"""Course-code normalization shared by every importer.

UW publishes cross-listed courses under several subjects ("COMP SCI/MATH 240",
"MATH 240", "COMPSCI_MATH_240").  BadgerPlan stores one canonical code per
course -- the exact string the UW Guide prints -- and an alias for every
subject/number pair so requirements and requisites always resolve to the same
record.
"""

from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")
_CODE = re.compile(r"^(?P<subjects>[A-Z&][A-Z &/]*?)\s*(?P<number>\d{1,3}[A-Z]?)$")


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("​", "").replace(" ", " ")
    return _SPACE.sub(" ", text).strip()


def compact_subject(subject: str) -> str:
    """'COMP SCI' -> 'COMPSCI', 'E C E' -> 'ECE' (the uwcourses/enroll form)."""

    return re.sub(r"[^A-Z&]", "", subject.upper())


def split_code(code: str) -> tuple[list[str], str] | None:
    """Split 'COMP SCI/MATH 240' into (['COMP SCI', 'MATH'], '240')."""

    code = clean(code).upper()
    match = _CODE.match(code)
    if not match:
        return None
    subjects = [clean(part) for part in match.group("subjects").split("/") if clean(part)]
    return subjects, match.group("number")


def alias_keys(code: str) -> list[str]:
    """Every lookup key under which a course should be findable."""

    parts = split_code(code)
    if not parts:
        return [clean(code).upper()]
    subjects, number = parts
    keys = [f"{compact_subject(subject)} {number}" for subject in subjects]
    keys.append(f"{'/'.join(compact_subject(s) for s in subjects)} {number}")
    return keys


def lookup_key(code: str) -> str:
    """Key for a single-subject reference such as 'COMP SCI 300' or 'COMPSCI 300'."""

    parts = split_code(code)
    if not parts:
        return clean(code).upper()
    subjects, number = parts
    if len(subjects) == 1:
        return f"{compact_subject(subjects[0])} {number}"
    return f"{'/'.join(compact_subject(s) for s in subjects)} {number}"


class CodeIndex:
    """Resolve any spelling of a course code to the canonical Guide code."""

    def __init__(self, canonical_codes: list[str] | None = None) -> None:
        self._aliases: dict[str, str] = {}
        self._subjects: set[str] = set()
        for code in canonical_codes or []:
            self.add(code)

    def add(self, canonical: str) -> None:
        canonical = clean(canonical).upper()
        parts = split_code(canonical)
        if parts:
            self._subjects.update(compact_subject(subject) for subject in parts[0])
        for key in alias_keys(canonical):
            # First writer wins; exact canonical strings always map to themselves.
            self._aliases.setdefault(key, canonical)

    def is_subject(self, subject: str) -> bool:
        pieces = [p for p in clean(subject).upper().split("/") if p]
        return bool(pieces) and all(compact_subject(p) in self._subjects for p in pieces)

    def resolve(self, code: str) -> str | None:
        if not code:
            return None
        key = lookup_key(code)
        if key in self._aliases:
            return self._aliases[key]
        parts = split_code(code)
        if parts and len(parts[0]) > 1:
            for subject in parts[0]:
                hit = self._aliases.get(f"{compact_subject(subject)} {parts[1]}")
                if hit:
                    return hit
        return None

    def resolve_ref(self, subjects: list[str], number: int | str) -> str | None:
        for subject in subjects:
            hit = self._aliases.get(f"{compact_subject(subject)} {number}")
            if hit:
                return hit
        return None

    def items(self):
        return self._aliases.items()


def term_code_to_label(term_code: str | int) -> tuple[str, int]:
    """UW term code 1262 -> ('Fall', 2025); 1264 -> ('Spring', 2026)."""

    code = str(term_code)
    century = 1900 + 100 * int(code[0])
    academic_end_year = century + int(code[1:3])
    season_digit = code[3]
    if season_digit == "2":
        return "Fall", academic_end_year - 1
    if season_digit == "4":
        return "Spring", academic_end_year
    if season_digit == "6":
        return "Summer", academic_end_year
    return "Winter", academic_end_year - 1


def parse_credit_range(text: str) -> tuple[float, float]:
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", text or "")]
    if not numbers:
        return 0.0, 0.0
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return min(numbers[:2]), max(numbers[:2])
