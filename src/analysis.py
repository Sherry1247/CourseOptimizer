"""Cross-program analysis: which second majors overlap most with a first major."""

from __future__ import annotations

from audit import active_blocks


def _block_codes(block: dict) -> set[str]:
    codes: set[str] = set()
    for slot in block.get("slots", []):
        for bundle in slot["options"]:
            codes.update(bundle)
    return codes


def _required_estimate(block: dict, credits_of) -> list[tuple[set[str], float, int]]:
    """(candidate codes, credits needed, courses needed) for each block."""

    rule = block["rule"]
    codes = _block_codes(block)
    if rule == "all":
        return [({code for code in bundle}, sum(credits_of(c) for c in bundle), len(bundle))
                for slot in block["slots"] for bundle in slot["options"][:1]]
    if rule == "choose":
        n = block.get("count") or 1
        return [(codes, 3.0 * n, n)]
    if rule == "credits":
        return [(codes, float(block.get("credits") or 3), max(1, int((block.get("credits") or 3) // 3)))]
    return []


def overlap_between(a: dict, b: dict, credits_of) -> dict:
    """Estimate how much of program B can be covered by courses that also count for A."""

    a_codes: set[str] = set()
    for block in active_blocks(a, None, include_college=True):
        a_codes |= _block_codes(block)
    shared: set[str] = set()
    shared_credits = 0.0
    b_total = 0.0
    for block in active_blocks(b, None, include_college=False):
        for codes, credits, count in _required_estimate(block, credits_of):
            b_total += credits
            common = codes & a_codes
            if not common:
                continue
            if block["rule"] == "all":
                shared |= common
                shared_credits += credits
            else:
                take = sorted(common, key=lambda c: -credits_of(c))[:count]
                shared |= set(take)
                shared_credits += min(credits, sum(credits_of(c) for c in take))
    return {
        "shared_courses": sorted(shared),
        "shared_credits": round(shared_credits, 1),
        "second_major_credits": round(b_total, 1),
        "additional_credits": round(max(0, b_total - shared_credits), 1),
        "percent": round(100 * shared_credits / b_total) if b_total else 0,
    }


def compare_programs(primary: dict, secondary: dict, credits_of) -> dict:
    result = overlap_between(primary, secondary, credits_of)
    shared = set(result["shared_courses"])
    unique = []
    manual = []
    for block in active_blocks(secondary, None, include_college=False):
        codes = _block_codes(block)
        entry = {
            "id": block.get("id"), "name": block["name"], "rule": block["rule"],
            "credits": block.get("credits"), "count": block.get("count"),
            "confidence": block.get("confidence"), "shared_courses": sorted(codes & shared),
            "candidate_courses": sorted(codes - shared)[:24],
        }
        if block["rule"] == "text" or block.get("confidence") == "low":
            manual.append(entry)
        elif not codes or codes - shared:
            unique.append(entry)
    return {
        "primary": {key: primary.get(key) for key in ("id", "name", "degree", "college", "confidence")},
        "secondary": {key: secondary.get(key) for key in ("id", "name", "degree", "college", "confidence")},
        **result,
        "unique_requirements": unique,
        "manual_requirements": manual,
        "estimate_note": "Overlap is estimated from parsed Guide requirement choices; school/college double-counting limits may apply.",
    }


def _base_name(name: str) -> str:
    return name.rsplit(",", 1)[0].split(":")[0].strip().lower()


def rank_second_majors(primary: dict, programs: list[dict], credits_of, limit: int = 40) -> list[dict]:
    rows = []
    for program in programs:
        if program["id"] == primary["id"] or not program["blocks"]:
            continue
        if _base_name(program["name"]) == _base_name(primary["name"]):
            continue  # same major under another degree / named option
        if program.get("parent_id") == primary["id"] or primary.get("parent_id") == program["id"]:
            continue
        result = overlap_between(primary, program, credits_of)
        if not result["shared_courses"]:
            continue
        rows.append({
            "id": program["id"], "name": program["name"], "degree": program["degree"],
            "college": program["college"], "confidence": program.get("confidence"), **result,
        })
    rows.sort(key=lambda r: (-r["shared_credits"], -r["percent"], r["name"]))
    return rows[:limit]
