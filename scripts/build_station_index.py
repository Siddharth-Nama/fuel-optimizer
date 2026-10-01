"""Build data/stations_geocoded.json once. The API never calls this.

City and state come from the US Census place list. When the CSV gives an
exit number, the nearest motorway junction in that town replaces the city
center. Canadian rows are skipped.
"""

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from math import cos, radians
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from routing.stations import load_stations  # noqa: E402

GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2025_Gazetteer/2025_Gaz_place_national.zip"
)
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "fuel-optimizer-assessment/1.0"
OUTPUT = ROOT / "data" / "stations_geocoded.json"

CANADA = {
    "AB",
    "BC",
    "MB",
    "NB",
    "NL",
    "NS",
    "NT",
    "NU",
    "ON",
    "PE",
    "QC",
    "SK",
    "YT",
}
EXIT_RE = re.compile(r"\bEXIT\s+([0-9]+[A-Z]?)\b", re.I)
PLACE_SUFFIX = re.compile(r"\s+(CITY|TOWN|VILLAGE|CDP|BOROUGH|MUNICIPALITY)$")


def _norm(name):
    name = name.upper().replace(".", " ")
    name = name.replace("SAINT ", "ST ")
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\bMC\s+", "MC", name)
    return name


def _place_keys(census_name):
    name = _norm(census_name)
    name = re.sub(r"^TOWN OF ", "", name)
    name = name.split("(")[0].strip()
    keys = {name}
    if "-" in name:
        keys.add(name.split("-")[0].strip())
    trimmed = name
    while True:
        nxt = PLACE_SUFFIX.sub("", trimmed)
        if nxt == trimmed:
            break
        trimmed = nxt
        keys.add(trimmed)
    return {key for key in keys if key}


def _get_json(url, data=None):
    last_error = None
    for attempt in range(3):
        req = urllib.request.Request(
            url,
            data=data,
            headers={"User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in (429, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    raise last_error


def load_places():
    req = urllib.request.Request(GAZETTEER_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as response:
        blob = response.read()
    archive = zipfile.ZipFile(io.BytesIO(blob))
    text = archive.read(archive.namelist()[0]).decode("latin-1")
    places = {}
    for row in csv.DictReader(io.StringIO(text), delimiter="|"):
        point = (float(row["INTPTLAT"]), float(row["INTPTLONG"]))
        for key in _place_keys(row["NAME"]):
            places.setdefault((key, row["USPS"]), point)
    return places


def _miles(lat1, lng1, lat2, lng2):
    dlat = (lat2 - lat1) * 69.0
    dlng = (lng2 - lng1) * 69.0 * cos(radians((lat1 + lat2) / 2))
    return (dlat * dlat + dlng * dlng) ** 0.5


def city_point(city, state, places, cache):
    key = (_norm(city), state)
    if key in places:
        return places[key]
    if key in cache:
        return cache[key]
    query = urllib.parse.urlencode(
        {"q": f"{city}, {state}, USA", "format": "json", "countrycodes": "us", "limit": 1}
    )
    time.sleep(1.1)
    rows = _get_json(f"{NOMINATIM_URL}?{query}")
    point = None
    if rows:
        point = (float(rows[0]["lat"]), float(rows[0]["lon"]))
    cache[key] = point
    return point


def _bbox(lat, lng):
    return (lat - 0.35, lng - 0.45, lat + 0.35, lng + 0.45)


def _nearest_junction(lat, lng, ref, nodes):
    south, west, north, east = _bbox(lat, lng)
    best = None
    best_miles = 15.0
    for node in nodes:
        if (node.get("tags") or {}).get("ref", "").upper() != ref:
            continue
        nlat, nlng = node["lat"], node["lon"]
        if not (south <= nlat <= north and west <= nlng <= east):
            continue
        dist = _miles(lat, lng, nlat, nlng)
        if dist < best_miles:
            best = (nlat, nlng)
            best_miles = dist
    return best


def exit_points(items):
    """Look up several exits in one Overpass call.

    items are (lat, lng, ref). Same town and exit number share one result.
    """
    found = {}
    pending = []
    for lat, lng, ref in items:
        key = (round(lat, 2), round(lng, 2), ref)
        if key in found or any(item[0] == key for item in pending):
            continue
        pending.append((key, lat, lng, ref))

    for start in range(0, len(pending), 8):
        chunk = pending[start : start + 8]
        parts = []
        for key, lat, lng, ref in chunk:
            south, west, north, east = _bbox(lat, lng)
            parts.append(
                f'node["highway"="motorway_junction"]["ref"="{ref}"]'
                f"({south},{west},{north},{east});"
            )
        query = "[out:json][timeout:40];(" + "".join(parts) + ");out body;"
        time.sleep(1.0)
        data = _get_json(OVERPASS_URL, data=query.encode())
        nodes = data.get("elements", [])
        for key, lat, lng, ref in chunk:
            found[key] = _nearest_junction(lat, lng, ref, nodes)
    return found


def _load_done(path):
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {row["opis_id"]: row for row in rows}


def _save(path, done):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(list(done.values())), encoding="utf-8")
    tmp.replace(path)


def _record(done, row, lat, lng):
    done[row["opis_id"]] = {
        "opis_id": row["opis_id"],
        "name": row["name"],
        "address": row["address"],
        "city": row["city"],
        "state": row["state"],
        "price": row["price"],
        "lat": round(lat, 6),
        "lng": round(lng, 6),
    }


def build(limit=None, output=OUTPUT):
    places = load_places()
    done = _load_done(output)
    name_cache = {}
    pending = [
        row
        for row in load_stations()
        if row["state"] not in CANADA and row["opis_id"] not in done
    ]
    if limit is not None:
        pending = pending[:limit]

    located = []
    for row in pending:
        point = city_point(row["city"], row["state"], places, name_cache)
        if point is None:
            print(f"skip {row['opis_id']}, unknown place {row['city']}, {row['state']}")
            continue
        located.append((row, point[0], point[1]))

    exits = []
    plain = []
    for row, lat, lng in located:
        match = EXIT_RE.search(row["address"] or "")
        if match:
            exits.append((row, lat, lng, match.group(1).upper()))
        else:
            plain.append((row, lat, lng))

    for row, lat, lng in plain:
        _record(done, row, lat, lng)
    _save(output, done)
    print(f"saved {len(done)} stops before exit lookups")

    snapped = 0
    for start in range(0, len(exits), 80):
        chunk = exits[start : start + 80]
        try:
            found = exit_points((lat, lng, ref) for row, lat, lng, ref in chunk)
        except Exception as exc:
            print(f"exit batch failed ({exc}); retrying one by one")
            found = {}
            for row, lat, lng, ref in chunk:
                key = (round(lat, 2), round(lng, 2), ref)
                if key in found:
                    continue
                try:
                    found.update(exit_points([(lat, lng, ref)]))
                except Exception:
                    print(f"skip {row['opis_id']}, exit lookup failed")
        for row, lat, lng, ref in chunk:
            key = (round(lat, 2), round(lng, 2), ref)
            if key not in found:
                continue
            junction = found[key]
            if junction is not None:
                lat, lng = junction
                snapped += 1
            _record(done, row, lat, lng)
        _save(output, done)
        print(f"saved {len(done)} stops, {snapped} snapped to an exit")

    print(f"wrote {len(done)} stops, {snapped} snapped to an exit, file {output}")


def main():
    parser = argparse.ArgumentParser(description="Geocode Spotter truck stops once.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(limit=args.limit, output=args.output)


if __name__ == "__main__":
    main()
