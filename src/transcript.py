"""Privacy-conscious transcript text extraction and catalog matching.

The parser is deliberately conservative: it only returns courses that resolve
to a code or alias in the local catalog.  A student reviews the matches before
the browser adds anything to their prior-credit list.
"""

from __future__ import annotations

import re
import unicodedata


_NUMBER = re.compile(r"\b\d{3}[A-Z]?\b")
_TOKEN = re.compile(r"[A-Z][A-Z&-]*|\d{3}[A-Z]?")
_PASSING_GRADE = re.compile(r"\b(A|AB|B|BC|C|D|S|CR|P|T)\b")
_NON_CREDIT = re.compile(r"\b(F|U|W|WD|I|IN|NR|AUDIT)\b")


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).upper().replace("\u00a0", " ")
    return re.sub(r"[^A-Z0-9]", "", value)


def parse_transcript(text: str, courses: dict[str, dict], aliases: dict[str, str]) -> dict:
    """Match transcript-like text to the local catalog.

    Credits come from the catalog, not from an inferred transcript column. This
    avoids silently treating grade points or attempted credits as earned credit.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("No transcript text was found.")
    if len(text) > 2_000_000:
        raise ValueError("Transcript text is too large (2 MB maximum).")

    lookup: dict[str, str] = {}
    for code in courses:
        lookup[_plain(code)] = code
    for alias, code in aliases.items():
        lookup[_plain(alias)] = code

    matched: dict[str, dict] = {}
    review_lines: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line or not _NUMBER.search(line.upper()):
            continue
        upper = unicodedata.normalize("NFKC", line).upper()
        tokens = _TOKEN.findall(upper)
        line_match = False
        for index, token in enumerate(tokens):
            if not _NUMBER.fullmatch(token):
                continue
            canonical = None
            for width in range(min(4, index), 0, -1):
                key = _plain(" ".join(tokens[index - width:index + 1]))
                if key in lookup:
                    canonical = lookup[key]
                    break
            if not canonical:
                continue
            line_match = True
            info = courses[canonical]
            failing = bool(_NON_CREDIT.search(upper)) and not bool(_PASSING_GRADE.search(upper))
            transfer = bool(re.search(r"\b(TRANSFER|AP|IB|ADVANCED PLACEMENT)\b", upper))
            credits = info.get("credits", [None, None])[0] or info.get("credits", [None, None])[1] or 3
            row = {
                "code": canonical,
                "title": info.get("title", ""),
                "credits": credits,
                "status": "transfer" if transfer else "completed",
                "include": not failing,
                "confidence": "matched" if (_PASSING_GRADE.search(upper) or transfer) else "review",
                "evidence": line[:240],
                "note": "Non-credit grade/status detected" if failing else "Credits use the UW catalog value",
            }
            previous = matched.get(canonical)
            if previous is None or (previous["confidence"] == "review" and row["confidence"] == "matched"):
                matched[canonical] = row
        if not line_match and len(review_lines) < 20:
            review_lines.append(line[:240])

    rows = sorted(matched.values(), key=lambda row: row["code"])
    return {
        "matches": rows,
        "review_lines": review_lines,
        "summary": {
            "matched": len(rows),
            "ready": sum(1 for row in rows if row["include"]),
            "needs_review": sum(1 for row in rows if row["confidence"] == "review"),
        },
        "disclaimer": "Catalog matches are planning aids. Verify awarded credits and equivalencies in DARS or with an advisor.",
    }
