"""Build data/stations_geocoded.json once. The API never calls this.

City and state come from the US Census place list. When the CSV gives an
exit number, the nearest motorway junction in that town replaces the city
center. Every US junction comes from one Overpass download, cached in
data/motorway_junctions.json, so matching runs offline. Canadian rows are skipped.
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
JUNCTIONS = ROOT / "data" / "motorway_junctions.json"
JUNCTIONS_QUERY = (
    "[out:json][timeout:900][maxsize:1073741824];"
    'area["ISO3166-1"="US"][admin_level=2]->.us;'
    'node["highway"="motorway_junction"]["ref"](area.us);'
    "out body qt;"
)

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
STARTED = time.monotonic()


def log(message):
    elapsed = int(time.monotonic() - STARTED)
    print(f"[{time.strftime('%H:%M:%S')} +{elapsed // 60}m{elapsed % 60:02d}s] {message}", flush=True)


def _reason(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code} {exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        return f"network error: {exc.reason}"
    return f"{type(exc).__name__}: {exc}"


def _service(url):
    return urllib.parse.urlparse(url).netloc


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


def _get_json(url, data=None, timeout=60):
    last_error = None
    for attempt in range(3):
        req = urllib.request.Request(
            url,
            data=data,
            headers={"User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in (429, 502, 503, 504) or attempt == 2:
                raise
            wait = 3 * (attempt + 1)
            log(f"  {_service(url)} said {_reason(exc)}; retry {attempt + 1} of 2 in {wait}s")
            time.sleep(wait)
    raise last_error


def load_places():
    log("Downloading the Census place list (US towns with coordinates)...")
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
    log(f"Census place list ready: {len(places)} town names.")
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
    log(
        f"  {city}, {state} is not in the Census list; Nominatim "
        + (f"found it at {point[0]:.4f}, {point[1]:.4f}" if point else "did not find it either")
    )
    cache[key] = point
    return point


def _bbox(lat, lng):
    return (lat - 0.35, lng - 0.45, lat + 0.35, lng + 0.45)


def load_junctions(path=JUNCTIONS):
    """Every US motorway junction as {exit ref: [(lat, lng), ...]}, downloaded once."""
    if path.exists():
        log(f"Using cached highway exits from {path.name}.")
        nodes = json.loads(path.read_text(encoding="utf-8"))
    else:
        log("Downloading every US highway exit from Overpass in one request (can take a few minutes)...")
        query = urllib.parse.urlencode({"data": JUNCTIONS_QUERY}).encode()
        data = _get_json(OVERPASS_URL, data=query, timeout=1000)
        # Overpass reports a server-side timeout or memory limit as a 200 with a remark.
        if data.get("remark"):
            raise RuntimeError(f"Overpass said: {data['remark']}")
        nodes = [
            [node["lat"], node["lon"], node["tags"]["ref"]]
            for node in data.get("elements", [])
            if (node.get("tags") or {}).get("ref")
        ]
        if not nodes:
            raise RuntimeError("Overpass returned no highway exits")
        path.write_text(json.dumps(nodes), encoding="utf-8")
        log(f"Saved {len(nodes)} highway exits to {path.name}; later runs reuse it.")

    by_ref = {}
    for lat, lng, ref in nodes:
        # One node can carry several exit numbers, e.g. "283;283A".
        for part in ref.upper().split(";"):
            by_ref.setdefault(part.strip(), []).append((lat, lng))
    log(f"Highway exits ready: {len(nodes)} junctions, {len(by_ref)} distinct exit numbers.")
    return by_ref


def _nearest_junction(lat, lng, candidates):
    south, west, north, east = _bbox(lat, lng)
    best = None
    best_miles = 15.0
    for nlat, nlng in candidates:
        if not (south <= nlat <= north and west <= nlng <= east):
            continue
        dist = _miles(lat, lng, nlat, nlng)
        if dist < best_miles:
            best = (nlat, nlng)
            best_miles = dist
    return best


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
    stations = load_stations()
    canadian = sum(1 for row in stations if row["state"] in CANADA)
    pending = [
        row
        for row in stations
        if row["state"] not in CANADA and row["opis_id"] not in done
    ]
    if limit is not None:
        pending = pending[:limit]
    log(
        f"CSV has {len(stations)} stations: {canadian} Canadian (ignored), "
        f"{len(done)} already in {output.name}, {len(pending)} to locate now."
    )

    log("Step 1 of 2: finding each stop's town.")
    located = []
    for row in pending:
        point = city_point(row["city"], row["state"], places, name_cache)
        if point is None:
            log(
                f"  SKIPPED stop {row['opis_id']} ({row['name']}, {row['city']}, {row['state']}): "
                "town not found. Not saved."
            )
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
    log(
        f"Step 1 done: {len(located)} towns found. Saved {len(plain)} stops with no exit "
        f"number at their town. File now has {len(done)} stops."
    )

    if not exits:
        log(f"Finished. {output} has {len(done)} stops. No stops needed an exit lookup.")
        return

    log(f"Step 2 of 2: snapping {len(exits)} stops to their highway exit.")
    try:
        junctions = load_junctions()
    except Exception as exc:
        log(
            f"Could not download highway exits: {_reason(exc)}. The {len(exits)} stops with an "
            "exit number were not saved. Run the script again to retry."
        )
        sys.exit(1)

    snapped = 0
    at_town = 0
    for row, lat, lng, ref in exits:
        junction = _nearest_junction(lat, lng, junctions.get(ref, ()))
        if junction is None:
            at_town += 1
        else:
            lat, lng = junction
            snapped += 1
        _record(done, row, lat, lng)
    _save(output, done)

    log(
        f"Finished. {output} has {len(done)} stops. This run: {snapped} snapped to their exit, "
        f"{at_town} at town centre (exit not found within 15 miles of the town)."
    )


def main():
    parser = argparse.ArgumentParser(description="Geocode Spotter truck stops once.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(limit=args.limit, output=args.output)


if __name__ == "__main__":
    main()
