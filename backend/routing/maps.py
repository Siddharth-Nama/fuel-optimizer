import json
import time
import urllib.error
import urllib.parse
import urllib.request

from routing.geo import InvalidLocation, require_usa

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
METERS_PER_MILE = 1609.344
USER_AGENT = "fuel-optimizer-assessment/1.0"
TIMEOUT_SECONDS = 10

_place_cache = {}
_route_cache = {}  # (start, finish) rounded -> (saved_at, route)
ROUTE_CACHE_SECONDS = 10 * 60
ROUTE_CACHE_SIZE = 256


class MapServiceError(Exception):
    """The free map service is down, slow or returned something unusable."""


def _get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            return json.load(exc)
        except ValueError:
            raise MapServiceError(str(exc)) from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise MapServiceError(str(exc)) from exc


def _cache_key(name):
    return " ".join(name.lower().split())


def geocode(name, field, calls=None):
    key = _cache_key(name)
    if key not in _place_cache:
        query = urllib.parse.urlencode(
            {"q": name, "format": "json", "countrycodes": "us", "limit": 1}
        )
        rows = _get_json(f"{NOMINATIM_URL}?{query}")
        if calls is not None:
            calls["nominatim"] += 1
        _place_cache[key] = (
            {"lat": float(rows[0]["lat"]), "lng": float(rows[0]["lon"])} if rows else None
        )

    point = _place_cache[key]
    if point is None:
        raise InvalidLocation(f"{field} '{name}' was not found in the United States.")
    return require_usa({"name": name, **point}, field)


def _route_key(start, finish):
    return tuple(round(value, 4) for value in (start["lat"], start["lng"], finish["lat"], finish["lng"]))


def route(start, finish, calls=None):
    key = _route_key(start, finish)
    cached = _route_cache.get(key)
    if cached and time.monotonic() - cached[0] < ROUTE_CACHE_SECONDS:
        return cached[1]

    coords = f"{start['lng']},{start['lat']};{finish['lng']},{finish['lat']}"
    query = urllib.parse.urlencode({"overview": "simplified", "geometries": "geojson"})
    data = _get_json(f"{OSRM_URL}/{coords}?{query}")
    if calls is not None:
        calls["osrm"] += 1

    code = data.get("code") if isinstance(data, dict) else None
    if code in ("NoRoute", "NoSegment"):
        raise InvalidLocation("No driving route connects start and finish.")
    if code != "Ok" or not data.get("routes"):
        raise MapServiceError(f"OSRM returned {code or 'an unexpected response'}.")

    best = data["routes"][0]
    result = {
        "miles": best["distance"] / METERS_PER_MILE,
        "minutes": best["duration"] / 60,
        "coordinates": best["geometry"]["coordinates"],
    }
    if len(_route_cache) >= ROUTE_CACHE_SIZE:
        _route_cache.pop(next(iter(_route_cache)))  # oldest first
    _route_cache[key] = (time.monotonic(), result)
    return result
