"""Map UW Guide 'Course Designation' strings to compact tags used by the audit."""

from __future__ import annotations

import re

GENED = {
    "communication & literacy": "ge_cl",
    "mathematics & quantitative reasoning": "ge_mqr",
    "natural science & wellness + lab": "ge_nswl",
    "natural science & wellness": "ge_nsw",
    "social & behavioral science": "ge_sbs",
    "humanities & arts": "ge_ha",
    "civics & perspectives": "ge_cp",
}
BREADTH = {
    "humanities": "hum",
    "literature": "lit",
    "social science": "ss",
    "biological science": "bio",
    "physical science": "phys",
    "natural science": "nat",
}
COMM_QR = {
    "communication a": "comm_a",
    "communication b": "comm_b",
    "quantitative reasoning a": "qr_a",
    "quantitative reasoning b": "qr_b",
}
LEVEL = {"elementary": "level_e", "intermediate": "level_i", "advanced": "level_a"}

TAG_LABELS = {
    "comm_a": "Comm A", "comm_b": "Comm B", "qr_a": "QR-A", "qr_b": "QR-B",
    "ethnic": "Ethnic Studies", "hum": "Humanities", "lit": "Literature", "ss": "Social Science",
    "bio": "Biological Sci", "phys": "Physical Sci", "nat": "Natural Sci", "lang": "Language",
    "las": "L&S credit", "level_e": "Elementary", "level_i": "Intermediate", "level_a": "Advanced",
    "ge_cl": "GenEd Comm & Literacy", "ge_mqr": "GenEd Math & QR", "ge_nsw": "GenEd Nat Sci & Wellness",
    "ge_nswl": "GenEd Nat Sci + Lab", "ge_sbs": "GenEd Social & Behavioral", "ge_ha": "GenEd Humanities & Arts",
    "ge_cp": "GenEd Civics & Perspectives", "honors": "Honors", "workplace": "Workplace",
}


def parse_designations(items: list[str]) -> dict:
    tags: list[str] = []
    breadth_choice: list[str] = []
    language_level: int | None = None
    for raw in items or []:
        if " - " not in raw:
            continue
        kind, value = raw.split(" - ", 1)
        kind, value = kind.strip().lower(), value.strip().lower()
        if kind == "core gened":
            tag = GENED.get(value)
            if tag:
                tags.append(tag)
                if tag == "ge_nswl":
                    tags.append("ge_nsw")
        elif kind == "breadth":
            options = [BREADTH[part.strip()] for part in re.split(r"\s+or\s+", value) if part.strip() in BREADTH]
            if len(options) > 1:
                breadth_choice = options
            tags.extend(options)
        elif kind == "comm qr":
            tag = COMM_QR.get(value)
            if tag:
                tags.append(tag)
        elif kind == "ethnic st":
            tags.append("ethnic")
        elif kind == "level":
            tag = LEVEL.get(value)
            if tag:
                tags.append(tag)
        elif kind == "l&s credit":
            if "liberal arts" in value:
                tags.append("las")
        elif kind == "frgn lang":
            tags.append("lang")
            match = re.search(r"(\d)", value)
            if match:
                language_level = int(match.group(1))
        elif kind == "honors":
            tags.append("honors")
        elif kind == "workplace":
            tags.append("workplace")
    unique: list[str] = []
    for tag in tags:
        if tag not in unique:
            unique.append(tag)
    return {"tags": unique, "breadth_choice": breadth_choice, "language_level": language_level}
