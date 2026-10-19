"""Build the static campus map used on the homepage.

Source: uw-coursemap-data (MIT, https://github.com/twangodev/uw-coursemap-data),
which publishes Spring 2026 class meetings and OpenStreetMap building outlines.

The script takes one representative teaching week, projects building outlines
to SVG paths and aggregates per-building statistics:

* class meetings in the week and distinct courses
* top departments, the largest courses and every course meeting there
* students in class by weekday and hour (for the time slider)

Output: web/static/campus-map.json (about 100 KB, no map tiles or API keys).

    python scripts/build_campus_map.py              # default week 2026-02-09..13
    python scripts/build_campus_map.py --week 03-02-26
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import math
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RAW_BASE = "https://raw.githubusercontent.com/twangodev/uw-coursemap-data/main/"
CACHE = ROOT / "data" / "raw" / "campus"
OUT = ROOT / "web" / "static" / "campus-map.json"
DB = ROOT / "data" / "badgerplan.db"
TZ = ZoneInfo("America/Chicago")
HOURS = list(range(8, 21))  # 8:00 .. 20:00 slots
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
WIDTH = 1000


def fetch(path: str) -> bytes | None:
    target = CACHE / path
    if target.exists():
        return target.read_bytes()
    url = RAW_BASE + urllib.parse.quote(path)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return data
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            time.sleep(1 + attempt)
        except OSError:
            time.sleep(1 + attempt)
    raise RuntimeError(f"could not fetch {url}")


def fetch_json(path: str):
    data = fetch(path)
    return json.loads(data) if data else None


def week_dates(start: str) -> list[str]:
    first = dt.datetime.strptime(start, "%m-%d-%y").date()
    if first.weekday() != 0:
        first -= dt.timedelta(days=first.weekday())
    return [(first + dt.timedelta(days=i)).strftime("%m-%d-%y") for i in range(5)]


def course_lookup() -> dict[str, str]:
    """Map 'COMPSCI 400' (coursemap style) to 'COMP SCI 400' (catalog code)."""
    if not DB.exists():
        return {}
    lookup = {}
    with sqlite3.connect(DB) as connection:
        for code, subjects, number in connection.execute("SELECT code, subjects, number FROM courses"):
            for subject in json.loads(subjects or "[]"):  # cross-listed codes share one entry
                lookup.setdefault(f"{subject.replace(' ', '')} {number}", code)
    return lookup


def ring_area(ring):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1])) / 2


def contains(geometry, lon, lat) -> bool:
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    for polygon in polygons:
        ring, inside = polygon[0], False
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
        if inside:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week", default="02-09-26", help="any date in the week, MM-DD-YY")
    args = parser.parse_args()

    dates = week_dates(args.week)
    lookup = course_lookup()
    catalog = set(lookup.values())
    meetings_by_day = {}
    for date in dates:
        rows = fetch_json(f"meetings/{date}.json")
        if rows is None:
            print(f"no meetings for {date}", file=sys.stderr)
            rows = []
        meetings_by_day[date] = rows
    names = sorted({m["location"]["building"] for rows in meetings_by_day.values() for m in rows
                    if (m.get("location") or {}).get("building")})
    print(f"{sum(map(len, meetings_by_day.values()))} meetings in {len(names)} buildings")

    # Outlines: one file per building; any date that building had classes works.
    # Fallback: the daily collection, matched by the point where classes meet.
    daily = [f for date in dates for f in (fetch_json(f"meetings/{date}.geojson") or {}).get("features", [])]
    points_by_name = {}
    for rows in meetings_by_day.values():
        for m in rows:
            location = m.get("location") or {}
            if location.get("building") and None not in (location.get("coordinates") or [None]):
                points_by_name.setdefault(location["building"], location["coordinates"])
    outlines = {}
    for name in names:
        if name.upper() in ("ONLINE", "OFF CAMPUS"):
            continue
        folder = "buildings/" + re.sub(r"\s+", "_", name.strip())
        feature = None
        for date in dates:
            collection = fetch_json(f"{folder}/{date}.geojson")
            if collection and collection.get("features"):
                feature = collection["features"][0]
                break
        if not feature and name in points_by_name:
            lat, lon = points_by_name[name]
            feature = next((f for f in daily if contains(f["geometry"], lon, lat)), None)
        if not feature or feature["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
            print(f"  no outline for {name}", file=sys.stderr)
            continue
        polygons = feature["geometry"]["coordinates"]
        if feature["geometry"]["type"] == "Polygon":
            polygons = [polygons]
        outlines[name] = {"polygons": polygons, "properties": feature.get("properties", {})}

    # Projection: equirectangular scaled by cos(latitude), north up.
    points = [pt for o in outlines.values() for poly in o["polygons"] for ring in poly for pt in ring]
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    lat0 = math.radians(sum(lats) / len(lats))
    min_x, max_x = min(lons) * math.cos(lat0), max(lons) * math.cos(lat0)
    min_y, max_y = min(lats), max(lats)
    pad = 0.035 * (max_x - min_x)
    scale = WIDTH / (max_x - min_x + 2 * pad)
    height = round((max_y - min_y + 2 * pad) * scale)

    def project(lon, lat):
        return ((lon * math.cos(lat0) - min_x + pad) * scale, (max_y - lat + pad) * scale)

    buildings = []
    for name, outline in outlines.items():
        path_parts, best = [], (0, 0, 0)
        for polygon in outline["polygons"]:
            for index, ring in enumerate(polygon):
                xy = [project(*pt) for pt in ring]
                path_parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in xy) + "Z")
                area = abs(ring_area(xy))
                if index == 0 and area > best[0]:
                    cx = sum(x for x, _ in xy) / len(xy)
                    cy = sum(y for _, y in xy) / len(xy)
                    best = (area, cx, cy)

        meetings = 0
        courses = collections.Counter()
        course_size = {}
        departments = collections.Counter()
        occupancy = [[0] * len(HOURS) for _ in DAYS]
        rooms = set()
        for day_index, date in enumerate(dates):
            for m in meetings_by_day[date]:
                location = m.get("location") or {}
                if location.get("building") != name:
                    continue
                meetings += 1
                rooms.add(location.get("room"))
                ref = m["course_reference"]
                subject = ref["subjects"][0]
                key = f"{subject} {ref['course_number']}"
                code = lookup.get(key, key)
                courses[code] += 1
                course_size[code] = max(course_size.get(code, 0), m.get("current_enrollment") or 0)
                departments[subject] += 1
                start = dt.datetime.fromtimestamp(m["start_time"] / 1000, TZ)
                end = dt.datetime.fromtimestamp(m["end_time"] / 1000, TZ)
                for slot, hour in enumerate(HOURS):
                    probe = start.replace(hour=hour, minute=30, second=0)
                    if start <= probe < end:
                        occupancy[day_index][slot] += m.get("current_enrollment") or 0
        top_courses = sorted(course_size, key=lambda c: (-course_size[c], c))[:5]
        props = outline["properties"]
        address = " ".join(filter(None, [props.get("addr:housenumber"), props.get("addr:street")]))
        buildings.append({
            "name": name,
            "path": "".join(path_parts),
            "label": [round(best[1], 1), round(best[2], 1)],
            "area": round(best[0]),
            "address": address,
            "meetings": meetings,
            "courses": len(courses),
            "rooms": len([r for r in rooms if r]),
            "departments": [d for d, _ in departments.most_common(4)],
            "top": [{"code": c, "catalog": c in catalog, "size": course_size[c]} for c in top_courses],
            # every course meeting here: [code, largest section, in catalog]
            "all": [[c, course_size[c], int(c in catalog)] for c in sorted(course_size, key=lambda c: (-course_size[c], c))],
            "occupancy": occupancy,
        })

    buildings.sort(key=lambda b: -b["area"])
    first = dt.datetime.strptime(dates[0], "%m-%d-%y").date()
    last = dt.datetime.strptime(dates[-1], "%m-%d-%y").date()
    output = {
        "term": "Spring 2026",
        "week": f"{first:%b} {first.day}–{last.day}, {last.year}" if first.month == last.month
                else f"{first:%b} {first.day} – {last:%b} {last.day}, {last.year}",
        "width": WIDTH,
        "height": height,
        "hours": HOURS,
        "days": DAYS,
        "buildings": buildings,
        "source": {
            "name": "uw-coursemap-data",
            "url": "https://github.com/twangodev/uw-coursemap-data",
            "license": "MIT",
            "outlines": "© OpenStreetMap contributors (ODbL)",
        },
    }
    OUT.write_text(json.dumps(output, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(buildings)} buildings, {OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
