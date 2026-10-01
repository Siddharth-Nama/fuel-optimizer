import json
import urllib.error
import urllib.parse
import urllib.request

from routing.geo import InvalidLocation, require_usa

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "fuel-optimizer-assessment/1.0"
TIMEOUT_SECONDS = 10

_place_cache = {}


class MapServiceError(Exception):
    """The free map service is down, slow or returned something unusable."""


def _get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise MapServiceError(str(exc)) from exc


def _cache_key(name):
    return " ".join(name.lower().split())


def geocode(name, field):
    key = _cache_key(name)
    if key not in _place_cache:
        query = urllib.parse.urlencode(
            {"q": name, "format": "json", "countrycodes": "us", "limit": 1}
        )
        rows = _get_json(f"{NOMINATIM_URL}?{query}")
        _place_cache[key] = (
            {"lat": float(rows[0]["lat"]), "lng": float(rows[0]["lon"])} if rows else None
        )

    point = _place_cache[key]
    if point is None:
        raise InvalidLocation(f"{field} '{name}' was not found in the United States.")
    return require_usa({"name": name, **point}, field)
