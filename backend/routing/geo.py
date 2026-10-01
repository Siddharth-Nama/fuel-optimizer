class InvalidLocation(ValueError):
    pass


def _coordinate(value, field, axis):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise InvalidLocation(f"{field}.{axis} must be a number.")
    try:
        return float(value)
    except ValueError:
        raise InvalidLocation(f"{field}.{axis} must be a number.") from None


def parse_location(value, field):
    """Return {"name": ...} for a place or {"lat": ..., "lng": ...} for a point."""
    if value is None:
        raise InvalidLocation(f"{field} is required.")
    if isinstance(value, str):
        name = value.strip()
        if not name:
            raise InvalidLocation(f"{field} must not be empty.")
        return {"name": name}
    if isinstance(value, dict):
        if value.get("lat") in (None, "") or value.get("lng") in (None, ""):
            raise InvalidLocation(f"{field} needs both lat and lng.")
        return {
            "lat": _coordinate(value["lat"], field, "lat"),
            "lng": _coordinate(value["lng"], field, "lng"),
        }
    raise InvalidLocation(f"{field} must be a place name or an object with lat and lng.")


# Lower 48 states. A box is coarse: it also admits bits of Canada and Mexico, and named places are checked against the country Nominatim returns.
USA_BOUNDS = {"south": 24.4, "north": 49.4, "west": -124.8, "east": -66.9}


def in_usa(lat, lng):
    return (
        USA_BOUNDS["south"] <= lat <= USA_BOUNDS["north"]
        and USA_BOUNDS["west"] <= lng <= USA_BOUNDS["east"]
    )


def require_usa(point, field):
    if not in_usa(point["lat"], point["lng"]):
        raise InvalidLocation(f"{field} must be in the contiguous United States.")
    return point
