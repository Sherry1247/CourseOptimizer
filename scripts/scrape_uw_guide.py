"""Scrape the UW–Madison Guide into the raw JSON consumed by build_snapshot.py.

    python scripts/scrape_uw_guide.py --out data/raw/guide

Writes
  courses_raw.json          every course block on guide.wisc.edu/courses/<subject>/
  programs_raw.json         requirements + four-year plan of every bachelor's program
  named_options_raw.json    named-option pages linked from those programs

Run it once per catalog year (the Guide updates each spring).  It is polite by
default: one worker per request type and a short delay between requests.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import time

import requests
from bs4 import BeautifulSoup, Tag

BASE = "https://guide.wisc.edu"
HEADERS = {"User-Agent": "BadgerPlan catalog sync (student project; contact via GitHub)"}
DEGREE_LINK = re.compile(r",\s*(B[A-Z]+|BS AMEP)\b")


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("​", "").replace(" ", " ")).strip()


def fetch(session: requests.Session, path: str, delay: float) -> str:
    for attempt in range(4):
        try:
            response = session.get(BASE + path, headers=HEADERS, timeout=30)
            response.raise_for_status()
            time.sleep(delay)
            return response.text
        except requests.RequestException:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not fetch {path}")


# ----------------------------------------------------------------------------- programs

def program_links(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = clean(a.get_text("\n").strip().split("\n")[0])
        if href.startswith("/undergraduate/") and DEGREE_LINK.search(text):
            links.setdefault(href, text)
    return list(links.items())


def _inside(el: Tag, names: set[str], stop: Tag | None = None) -> bool:
    parent = el.parent
    while parent is not None and parent is not stop:
        if parent.name in names:
            return True
        parent = parent.parent
    return False


def _has_class_ancestor(el: Tag, cls: str) -> bool:
    parent = el.parent
    while parent is not None:
        if cls in (parent.get("class") or []):
            return True
        parent = parent.parent
    return False


def _course_rows(table: Tag) -> list[list]:
    rows = []
    for tr in table.find_all("tr"):
        if tr.find_parent("thead"):
            continue
        code = tr.find("td", class_="codecol")
        comment = tr.find(class_="courselistcomment")
        codes = []
        if code:
            for a in code.find_all("a", class_=re.compile(r"bubblelink|code")):
                codes.append(clean(a.get("title") or a.get_text()))
        hours = clean(tr.find("td", class_="hourscol").get_text()) if tr.find("td", class_="hourscol") else ""
        cells = tr.find_all("td", recursive=False)
        classes = " ".join(c for c in (tr.get("class") or []) if c not in {"even", "odd", "firstrow", "lastrow"})
        title = ""
        if not comment and len(cells) > 1 and cells[1] is not code:
            title = clean(cells[1].get_text())[:90]
        rows.append([
            classes,
            clean(comment.get_text()) if comment else clean(code.get_text() if code else ""),
            codes,
            title,
            hours,
            1 if comment else 0,
            1 if comment is not None and "areaheader" in (comment.get("class") or []) else 0,
            1 if tr.find(class_="blockindent") else 0,
        ])
    return rows


def extract_program(html: str, href: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = clean(soup.select_one("h1.page-title").get_text()) if soup.select_one("h1.page-title") else ""
    crumbs = [clean(a.get_text()) for a in soup.select("#breadcrumb a, nav#breadcrumb a, .breadcrumb a")]
    out = {"href": href, "title": title, "crumbs": crumbs, "items": [], "plan": []}
    container = soup.select_one("#requirementstextcontainer")
    if container:
        for el in container.find_all(["h2", "h3", "h4", "h5", "p", "ul", "ol", "table"]):
            if el.name != "table" and _inside(el, {"table"}, container):
                continue
            if _has_class_ancestor(el, "onthispage"):
                continue
            if el.name in {"h2", "h3", "h4", "h5"}:
                out["items"].append(["h", int(el.name[1]), clean(el.get_text())])
            elif el.name in {"p", "ul", "ol"}:
                if _inside(el, {"ul", "ol"}, container):
                    continue
                text = clean(el.get_text())
                if text:
                    out["items"].append(["t", text[:900]])
            else:
                classes = el.get("class") or []
                if "sc_courselist" in classes:
                    out["items"].append(["c", _course_rows(el)])
                elif any(c.startswith("tbl_") for c in classes):
                    rows = [[clean(td.get_text())[:400] for td in tr.find_all(["td", "th"])] for tr in el.find_all("tr")]
                    out["items"].append(["g", " ".join(c for c in classes if c != "sc_sctable"), rows])
    plan = soup.select_one("#fouryearplantextcontainer")
    if plan:
        for table in plan.select("table.sc_plangrid"):
            out["plan"].append([[clean(td.get_text())[:120] for td in tr.find_all(["td", "th"])] for tr in table.find_all("tr")])
    return out


def named_option_links(html: str, href: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for a in soup.select("#requirementstextcontainer a[href], #textcontainer a[href]"):
        target = a["href"]
        if target.startswith(href) and len(target) > len(href) + 3 and "#" not in target:
            found.setdefault(target, clean(a.get_text()))
    return list(found.items())


# ----------------------------------------------------------------------------- courses

def subject_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return sorted({a["href"] for a in soup.find_all("a", href=True) if re.fullmatch(r"/courses/[a-z_0-9]+/", a["href"])})


def extract_courses(html: str, subject_href: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    courses = []
    for block in soup.select(".courseblock"):
        code = clean(block.select_one(".courseblockcode").get_text()) if block.select_one(".courseblockcode") else ""
        heading = clean(block.select_one(".courseblocktitle").get_text()) if block.select_one(".courseblocktitle") else ""
        extras: dict = {}
        for p in block.select("p.courseblockextra"):
            label_el, data_el = p.select_one(".cbextra-label"), p.select_one(".cbextra-data")
            if not label_el or not data_el:
                continue
            label = clean(label_el.get_text()).rstrip(":")
            if not label or label == "Learning Outcomes":
                continue
            if label == "Course Designation":
                parts = re.split(r"<br\s*/?>", data_el.decode_contents())
                extras[label] = [clean(BeautifulSoup(part, "html.parser").get_text()) for part in parts if clean(BeautifulSoup(part, "html.parser").get_text())]
            else:
                extras[label] = clean(data_el.get_text())
            if label == "Requisites":
                extras["reqCodes"] = [clean(a.get("title") or a.get_text()) for a in data_el.select("a.bubblelink")]
        courses.append({
            "code": code,
            "title": " — ".join(heading.split(" — ")[1:]),
            "credits": clean(block.select_one(".courseblockcredits").get_text()) if block.select_one(".courseblockcredits") else "",
            "desc": clean(block.select_one(".courseblockdesc").get_text())[:600] if block.select_one(".courseblockdesc") else "",
            "x": extras,
            "subj": subject_href,
        })
    return courses


# ----------------------------------------------------------------------------- main

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "raw" / "guide")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.2)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    links = program_links(fetch(session, "/undergraduate/", args.delay))
    print(f"{len(links)} bachelor's programs")

    def load_program(item):
        href, name = item
        html = fetch(session, href, args.delay)
        return {**extract_program(html, href), "name": name}, named_option_links(html, href)

    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(load_program, links))
    programs = [program for program, _ in results]
    option_links = {}
    for (program, options) in results:
        for target, name in options:
            option_links.setdefault(target, (name, program["href"]))

    def load_option(item):
        target, (name, parent) = item
        return {**extract_program(fetch(session, target, args.delay), target), "name": name, "parent": parent}

    with ThreadPoolExecutor(args.workers) as pool:
        options = list(pool.map(load_option, option_links.items()))
    print(f"{len(options)} named options")

    subjects = subject_links(fetch(session, "/courses/", args.delay))
    with ThreadPoolExecutor(args.workers) as pool:
        pages = list(pool.map(lambda href: extract_courses(fetch(session, href, args.delay), href), subjects))
    courses: dict[str, dict] = {}
    for page in pages:
        for course in page:
            courses.setdefault(course["code"], course)
    print(f"{len(courses)} course blocks from {len(subjects)} subjects")

    (args.out / "programs_raw.json").write_text(json.dumps(programs, ensure_ascii=False), encoding="utf-8")
    (args.out / "named_options_raw.json").write_text(json.dumps(options, ensure_ascii=False), encoding="utf-8")
    (args.out / "courses_raw.json").write_text(json.dumps(list(courses.values()), ensure_ascii=False), encoding="utf-8")
    print(f"Wrote raw Guide data to {args.out}")


if __name__ == "__main__":
    main()
