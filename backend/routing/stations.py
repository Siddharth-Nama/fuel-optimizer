import csv
import json
from math import cos, floor, radians
from pathlib import Path

from routing.route import project

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "fuel-prices-for-be-assessment.csv"
GEOCODED_PATH = Path(__file__).resolve().parents[2] / "data" / "stations_geocoded.json"
_LOADED = None
_GRID = None

CORRIDOR_MILES = 10
GRID_DEGREES = 0.5


def load_stations(path=DATA_PATH):
    stations = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            opis_id = (row.get("OPIS Truckstop ID") or "").strip()
            raw_price = (row.get("Retail Price") or "").strip()
            if not opis_id or not raw_price:
                continue
            try:
                price = float(raw_price)
            except ValueError:
                continue
            # One station can be listed more than once; the driver pays the lowest price.
            if opis_id in stations and stations[opis_id]["price"] <= price:
                continue
            stations[opis_id] = {
                "opis_id": opis_id,
                "name": (row.get("Truckstop Name") or "").strip(),
                "address": (row.get("Address") or "").strip(),
                "city": (row.get("City") or "").strip(),
                "state": (row.get("State") or "").strip(),
                "price": price,
            }
    return list(stations.values())


def load_geocoded_stations(path=GEOCODED_PATH):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def get_stations():
    global _LOADED
    if _LOADED is None:
        _LOADED = load_geocoded_stations()
    return _LOADED


def _cell(lat, lng):
    return floor(lat / GRID_DEGREES), floor(lng / GRID_DEGREES)


def build_grid(stations):
    grid = {}
    for station in stations:
        grid.setdefault(_cell(station["lat"], station["lng"]), []).append(station)
    return grid


def get_grid():
    global _GRID
    if _GRID is None:
        _GRID = build_grid(get_stations())
    return _GRID


def _nearby(grid, a, b, corridor_miles):
    lat_pad = corridor_miles / 69.0
    lng_pad = corridor_miles / (69.0 * cos(radians(max(abs(a["lat"]), abs(b["lat"])) + lat_pad)))
    south, west = _cell(min(a["lat"], b["lat"]) - lat_pad, min(a["lng"], b["lng"]) - lng_pad)
    north, east = _cell(max(a["lat"], b["lat"]) + lat_pad, max(a["lng"], b["lng"]) + lng_pad)
    for row in range(south, north + 1):
        for col in range(west, east + 1):
            yield from grid.get((row, col), ())


def stations_along_route(points, corridor_miles=CORRIDOR_MILES, grid=None):
    grid = get_grid() if grid is None else grid
    best = {}
    last = len(points) - 2
    for index in range(len(points) - 1):
        a, b = points[index], points[index + 1]
        for station in _nearby(grid, a, b, corridor_miles):
            off_route, t = project(a, b, station["lat"], station["lng"])
            if off_route > corridor_miles:
                continue
            # Behind the start or past the finish: the truck never drives by it.
            if (index == 0 and t < 0) or (index == last and t > 1):
                continue
            seen = best.get(station["opis_id"])
            if seen is None or off_route < seen["miles_off_route"]:
                t = min(1.0, max(0.0, t))
                best[station["opis_id"]] = {
                    **station,
                    "route_mile": a["mile"] + t * (b["mile"] - a["mile"]),
                    "miles_off_route": off_route,
                }
    return sorted(best.values(), key=lambda stop: stop["route_mile"])
