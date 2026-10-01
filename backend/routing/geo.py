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
